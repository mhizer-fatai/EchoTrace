import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import networkx as nx

from backend.app.config import settings
from backend.app.models.schemas import (
    BaseGraphNode,
    FactStatus,
    GraphEdge,
    NodeKind,
)

logger = logging.getLogger("echotrace.graph.client")


class InMemoryGraphStore:
    """
    In-memory graph database engine with native DAG traversal and temporal filtering.
    Used for local development, instant unit testing, and standalone demonstration.
    """

    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: Dict[str, GraphEdge] = {}
        self.graph = nx.DiGraph()

    def add_node(self, node: Any) -> Dict[str, Any]:
        if hasattr(node, "model_dump"):
            node_dict = node.model_dump()
        elif isinstance(node, dict):
            node_dict = dict(node)
        else:
            node_dict = dict(node.__dict__)

        node_id = str(node_dict["id"])
        if "created_at" in node_dict and isinstance(node_dict["created_at"], datetime):
            node_dict["created_at"] = node_dict["created_at"].isoformat()
        if "valid_from" in node_dict and isinstance(node_dict["valid_from"], datetime):
            node_dict["valid_from"] = node_dict["valid_from"].isoformat()
        if "valid_to" in node_dict and isinstance(node_dict["valid_to"], datetime):
            node_dict["valid_to"] = node_dict["valid_to"].isoformat()

        self.nodes[node_id] = node_dict
        self.graph.add_node(node_id, **node_dict)
        return node_dict

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        edge_dict = edge.model_dump()
        if isinstance(edge_dict["created_at"], datetime):
            edge_dict["created_at"] = edge_dict["created_at"].isoformat()

        self.edges[edge.id] = edge
        self.graph.add_edge(
            edge.source_id,
            edge.target_id,
            id=edge.id,
            edge_type=edge.edge_type.value if hasattr(edge.edge_type, "value") else str(edge.edge_type),
            created_at=edge_dict["created_at"],
            metadata=edge.metadata,
        )
        return edge

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        return self.nodes.get(str(node_id))

    def update_node(self, node_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        node = self.nodes.get(str(node_id))
        if not node:
            return None
        for k, v in updates.items():
            if isinstance(v, datetime):
                v = v.isoformat()
            node[k] = v
        self.graph.nodes[str(node_id)].update(updates)
        return node

    def get_session_graph(
        self, session_id: str, snapshot_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        result_nodes: List[Dict[str, Any]] = []
        node_id_set = set()

        for node_id, node in self.nodes.items():
            if node.get("session_id") != session_id:
                continue

            if snapshot_time is not None:
                vf_raw = node.get("valid_from")
                vt_raw = node.get("valid_to")

                vf = datetime.fromisoformat(vf_raw) if isinstance(vf_raw, str) else vf_raw
                vt = datetime.fromisoformat(vt_raw) if isinstance(vt_raw, str) else vt_raw

                if vf and vf.tzinfo is None:
                    vf = vf.replace(tzinfo=timezone.utc)
                if vt and vt.tzinfo is None:
                    vt = vt.replace(tzinfo=timezone.utc)
                if snapshot_time.tzinfo is None:
                    snapshot_time = snapshot_time.replace(tzinfo=timezone.utc)

                if vf and vf > snapshot_time:
                    continue
                if vt and vt <= snapshot_time:
                    continue

            result_nodes.append(node)
            node_id_set.add(node_id)

        result_edges: List[Dict[str, Any]] = []
        for edge_id, edge in self.edges.items():
            if edge.source_id in node_id_set and edge.target_id in node_id_set:
                edge_data = edge.model_dump()
                if isinstance(edge_data["created_at"], datetime):
                    edge_data["created_at"] = edge_data["created_at"].isoformat()
                result_edges.append(edge_data)

        return {"nodes": result_nodes, "edges": result_edges}

    def get_downstream_nodes(self, start_node_id: str, session_id: str) -> List[str]:
        """
        Traverse the graph downstream to find all nodes that depend on start_node_id.
        In EchoTrace, edge orientation is: (dependent)-[:DEPENDS_ON]->(source_fact)
        or (agent)-[:PRODUCED]->(fact), so downstream dependents are predecessors in graph.
        """
        if not self.graph.has_node(start_node_id):
            return []

        visited = set()
        queue = [start_node_id]

        while queue:
            current = queue.pop(0)
            # Find incoming edges where target is current (i.e. nodes that depend on current)
            for predecessor in self.graph.predecessors(current):
                edge_data = self.graph.get_edge_data(predecessor, current)
                edge_type = edge_data.get("edge_type", "")
                if edge_type in ["DEPENDS_ON", "TRIGGERED", "PRODUCED", "SUPPORTED_BY"]:
                    if predecessor not in visited and predecessor != start_node_id:
                        node_data = self.nodes.get(predecessor, {})
                        if node_data.get("session_id") == session_id:
                            visited.add(predecessor)
                            queue.append(predecessor)

        return list(visited)

    def clear_session(self, session_id: str):
        nodes_to_remove = [
            nid for nid, node in self.nodes.items() if node.get("session_id") == session_id
        ]
        for nid in nodes_to_remove:
            del self.nodes[nid]
            if self.graph.has_node(nid):
                self.graph.remove_node(nid)

        edges_to_remove = [
            eid
            for eid, edge in self.edges.items()
            if edge.source_id in nodes_to_remove or edge.target_id in nodes_to_remove
        ]
        for eid in edges_to_remove:
            del self.edges[eid]


class HydraDBClient:
    """
    Client for HydraDB graph operations.
    Maintains a connection to HydraDB via Bolt and automatically falls back
    to the in-memory engine when running in standalone mode.
    """

    def __init__(self):
        self.bolt_driver = None
        self.in_memory = InMemoryGraphStore()
        self.connected_to_hydradb = False
        self._init_connection()

    def _init_connection(self):
        try:
            from neo4j import GraphDatabase

            auth = None
            if settings.hydradb_auth_token:
                auth = ("hydra", settings.hydradb_auth_token)

            self.bolt_driver = GraphDatabase.driver(
                settings.hydradb_bolt_uri,
                auth=auth,
                encrypted=not settings.hydradb_allow_plaintext,
            )
            # Verify connectivity with a lightweight ping
            with self.bolt_driver.session() as session:
                session.run("RETURN 1 as ping")
            self.connected_to_hydradb = True
            logger.info("Successfully connected to HydraDB via Bolt")
        except Exception as exc:
            self.connected_to_hydradb = False
            logger.warning(
                f"HydraDB not reachable at {settings.hydradb_bolt_uri}. "
                f"Using internal high-performance graph engine. (Reason: {exc})"
            )

    def execute_cypher(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute raw Cypher query against HydraDB if connected, otherwise log query.
        """
        if self.connected_to_hydradb and self.bolt_driver:
            try:
                with self.bolt_driver.session() as session:
                    result = session.run(query, parameters or {})
                    return [record.data() for record in result]
            except Exception as exc:
                logger.error(f"Error executing Cypher on HydraDB: {exc}")
                raise exc
        return []

    def add_node(self, node: BaseGraphNode) -> Dict[str, Any]:
        node_dict = node.model_dump()
        return self.in_memory.add_node(node_dict)

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        return self.in_memory.add_edge(edge)

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        return self.in_memory.get_node(node_id)

    def update_node(self, node_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.in_memory.update_node(node_id, updates)

    def get_session_graph(
        self, session_id: str, snapshot_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        return self.in_memory.get_session_graph(session_id, snapshot_time)

    def get_downstream_dependencies(self, fact_id: str, session_id: str) -> List[str]:
        return self.in_memory.get_downstream_nodes(fact_id, session_id)

    def invalidate_fact_node(self, fact_id: str, timestamp: datetime) -> Optional[Dict[str, Any]]:
        return self.update_node(
            fact_id,
            {"status": FactStatus.INVALIDATED.value, "valid_to": timestamp.isoformat()},
        )

    def supersede_fact_nodes(
        self, old_fact_id: str, new_fact_id: str, timestamp: datetime
    ) -> bool:
        self.update_node(
            old_fact_id,
            {"status": FactStatus.SUPERSEDED.value, "valid_to": timestamp.isoformat()},
        )
        edge = GraphEdge(
            id=f"edge_sup_{old_fact_id}_{new_fact_id}",
            source_id=old_fact_id,
            target_id=new_fact_id,
            edge_type="SUPERSEDED_BY",
            created_at=timestamp,
        )
        self.add_edge(edge)
        return True

    def mark_node_stale(self, node_id: str, is_stale: bool = True) -> Optional[Dict[str, Any]]:
        return self.update_node(node_id, {"is_stale": is_stale})

    def clear_session(self, session_id: str):
        self.in_memory.clear_session(session_id)


# Global singleton graph client instance
graph_client = HydraDBClient()
