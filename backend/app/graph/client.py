import logging
import json
import hashlib
from datetime import datetime, timezone
from enum import Enum
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
    Used for local development and isolated unit testing.
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
                if edge_type in ["DEPENDS_ON", "TRIGGERED"]:
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
        self.store_degraded = False
        self.degraded_reason: Optional[str] = None
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
            # HydraDB's row executor requires a MATCH query for Bolt reads.
            with self.bolt_driver.session() as session:
                session.run(
                    "MATCH (n:EchoTraceNode) RETURN count(*) AS node_count"
                ).consume()
            self.connected_to_hydradb = True
            self.store_degraded = False
            self.degraded_reason = None
            logger.info("Successfully connected to HydraDB via Bolt")
        except Exception as exc:
            self.connected_to_hydradb = False
            if self.bolt_driver:
                self.bolt_driver.close()
                self.bolt_driver = None
            if not settings.use_in_memory_fallback:
                raise RuntimeError(
                    f"HydraDB is unavailable at {settings.hydradb_bolt_uri} and "
                    "USE_IN_MEMORY_FALLBACK is disabled."
                ) from exc
            logger.warning(
                f"HydraDB not reachable at {settings.hydradb_bolt_uri}. "
                f"Using internal high-performance graph engine. (Reason: {exc})"
            )

    def reconnect(self) -> bool:
        if self.bolt_driver:
            try:
                self.bolt_driver.close()
            except Exception:
                pass
        self.bolt_driver = None
        self.connected_to_hydradb = False
        self._init_connection()
        return self.connected_to_hydradb

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
                # Bolt connections can become stale after HydraDB restarts or a
                # long idle period. Reconnect once so the first demo click does
                # not fail while the graph itself remains healthy.
                logger.warning("HydraDB query failed; reconnecting once: %s", exc)
                try:
                    self.bolt_driver.close()
                except Exception:
                    pass
                self.bolt_driver = None
                self.connected_to_hydradb = False
                self._init_connection()
                if not self.connected_to_hydradb or not self.bolt_driver:
                    raise exc
                with self.bolt_driver.session() as session:
                    result = session.run(query, parameters or {})
                    return [record.data() for record in result]
        return []

    @staticmethod
    def _serialize_properties(data: Dict[str, Any]) -> Dict[str, Any]:
        serialized: Dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, datetime):
                serialized[key] = value.isoformat()
            elif isinstance(value, Enum):
                serialized[key] = value.value
            elif isinstance(value, (dict, list)):
                serialized[key] = json.dumps(value)
            else:
                serialized[key] = value
        return serialized

    @staticmethod
    def _deserialize_properties(data: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(data)
        for key in ("metadata", "parameters"):
            value = result.get(key)
            if isinstance(value, str):
                try:
                    result[key] = json.loads(value)
                except json.JSONDecodeError:
                    pass
        return result

    def _node_parameters(self, node_dict: Dict[str, Any]) -> Dict[str, Any]:
        serialized = self._serialize_properties(node_dict)
        return {
            "id": str(serialized["id"]),
            "native_id": self._native_id(str(serialized["id"])),
            "session_id": str(serialized.get("session_id", "default")),
            "session_native_id": self._native_id(
                f"session:{serialized.get('session_id', 'default')}"
            ),
            "kind": str(serialized.get("kind", "")),
            "valid_from": str(serialized.get("valid_from", "")),
            "valid_to": serialized.get("valid_to") or "",
            "status": str(serialized.get("status", "")),
            "is_stale": bool(serialized.get("is_stale", False)),
            "payload": json.dumps(serialized),
        }

    @staticmethod
    def _native_id(value: str) -> int:
        digest = hashlib.sha256(value.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)

    @staticmethod
    def _node_from_record(record: Dict[str, Any]) -> Dict[str, Any]:
        payload = record.get("payload") or "{}"
        node = json.loads(payload)
        node.update({
            "id": record.get("id", node.get("id")),
            "session_id": record.get("session_id", node.get("session_id")),
            "kind": record.get("kind", node.get("kind")),
            "valid_from": record.get("valid_from", node.get("valid_from")),
            "valid_to": record.get("valid_to") or None,
            "status": record.get("status", node.get("status")),
            "is_stale": record.get("is_stale", node.get("is_stale", False)),
        })
        return HydraDBClient._deserialize_properties(node)

    @staticmethod
    def _node_projection(alias: str = "n") -> str:
        fields = ("session_id", "kind", "valid_from", "valid_to", "status", "is_stale", "payload")
        projected = [f"{alias}.echotrace_id AS id"]
        projected.extend(f"{alias}.{field} AS {field}" for field in fields)
        return ", ".join(projected)

    def add_node(self, node: BaseGraphNode) -> Dict[str, Any]:
        node_dict = node.model_dump() if hasattr(node, "model_dump") else dict(node)
        if not self.connected_to_hydradb:
            return self.in_memory.add_node(node_dict)

        parameters = self._node_parameters(node_dict)
        if self.get_node(parameters["id"]):
            return self.update_node(parameters["id"], node_dict) or node_dict
        node_pattern = (
            "(n:EchoTraceNode {id: $native_id, echotrace_id: $id, session_id: $session_id, kind: $kind, "
            "valid_from: $valid_from, valid_to: $valid_to, status: $status, "
            "is_stale: $is_stale, payload: $payload})"
        )
        query = (
            "CREATE (:EchoTraceSession {id: $session_native_id, session_key: $session_id})"
            f"-[:CONTAINS]->{node_pattern}"
        )
        self.execute_cypher(query, parameters)
        return self._node_from_record(parameters)

    def add_edge(self, edge: GraphEdge) -> GraphEdge:
        if not self.connected_to_hydradb:
            return self.in_memory.add_edge(edge)

        edge_data = self._serialize_properties(edge.model_dump())
        self.execute_cypher(
            "MERGE (source:EchoTraceNode {id: $source_native_id})"
            "-[:ECHOTRACE_EDGE {echotrace_edge_id: $id, source_id: $source_id, "
            "target_id: $target_id, edge_type: $edge_type, created_at: $created_at, "
            "payload: $payload}]->(target:EchoTraceNode {id: $target_native_id})",
            {
                "id": edge.id,
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "source_native_id": self._native_id(edge.source_id),
                "target_native_id": self._native_id(edge.target_id),
                "edge_type": edge.edge_type.value if hasattr(edge.edge_type, "value") else str(edge.edge_type),
                "created_at": str(edge_data["created_at"]),
                "payload": json.dumps(edge_data),
            },
        )
        return edge

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        if not self.connected_to_hydradb:
            return self.in_memory.get_node(node_id)
        records = self.execute_cypher(
            f"MATCH (n:EchoTraceNode {{id: $native_id}}) RETURN {self._node_projection()}",
            {"native_id": self._native_id(str(node_id))},
        )
        if not records:
            return None
        return self._node_from_record(records[0])

    def update_node(self, node_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.connected_to_hydradb:
            return self.in_memory.update_node(node_id, updates)
        current = self.get_node(node_id)
        if not current:
            return None
        current.update(updates)
        parameters = self._node_parameters(current)
        self.execute_cypher(
            "MATCH (n:EchoTraceNode {id: $native_id}) "
            "SET n.session_id = $session_id, n.kind = $kind, "
            "n.valid_from = $valid_from, n.valid_to = $valid_to, "
            "n.status = $status, n.is_stale = $is_stale, n.payload = $payload",
            parameters,
        )
        return self._node_from_record(parameters)

    def get_session_graph(
        self, session_id: str, snapshot_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        if not self.connected_to_hydradb:
            return self.in_memory.get_session_graph(session_id, snapshot_time)

        records = self.execute_cypher(
            "MATCH (n:EchoTraceNode {session_id: $session_id})"
            + f" RETURN {self._node_projection()}",
            {"session_id": session_id},
        )
        nodes = [self._node_from_record(record) for record in records]
        if snapshot_time:
            if snapshot_time.tzinfo is None:
                snapshot_time = snapshot_time.replace(tzinfo=timezone.utc)
            nodes = [
                node
                for node in nodes
                if datetime.fromisoformat(str(node["valid_from"])) <= snapshot_time
                and (
                    not node.get("valid_to")
                    or datetime.fromisoformat(str(node["valid_to"])) > snapshot_time
                )
            ]
        node_ids = [node["id"] for node in nodes]
        if not node_ids:
            return {"nodes": [], "edges": []}
        edge_records = self.execute_cypher(
            "MATCH (s:EchoTraceNode)-[r:ECHOTRACE_EDGE]->(t:EchoTraceNode) "
            "WHERE s.session_id = $session_id AND t.session_id = $session_id "
            "RETURN r.echotrace_edge_id AS id, r.source_id AS source_id, r.target_id AS target_id, "
            "r.edge_type AS edge_type, r.created_at AS created_at, r.payload AS payload",
            {"session_id": session_id},
        )
        edges = []
        for record in edge_records:
            edge = json.loads(record.get("payload") or "{}")
            edge.update({key: record.get(key, edge.get(key)) for key in ("id", "source_id", "target_id", "edge_type", "created_at")})
            if edge.get("source_id") in node_ids and edge.get("target_id") in node_ids:
                edges.append(edge)
        return {"nodes": nodes, "edges": edges}

    def get_downstream_dependencies(self, fact_id: str, session_id: str) -> List[str]:
        if not self.connected_to_hydradb:
            return self.in_memory.get_downstream_nodes(fact_id, session_id)
        downstream: List[str] = []
        queue = [fact_id]
        visited = {fact_id}
        while queue:
            current = queue.pop(0)
            current_native_id = self._native_id(current)
            records = self.execute_cypher(
                "MATCH (dependent:EchoTraceNode)-[r:ECHOTRACE_EDGE]->"
                f"(source:EchoTraceNode {{id: {current_native_id}}}) "
                "WHERE dependent.session_id = $session_id AND "
                "(r.edge_type = 'DEPENDS_ON' OR r.edge_type = 'TRIGGERED') "
                "RETURN dependent.echotrace_id AS id",
                {"session_id": session_id},
            )
            for record in records:
                dependent_id = record["id"]
                if dependent_id not in visited:
                    visited.add(dependent_id)
                    downstream.append(dependent_id)
                    queue.append(dependent_id)
        return downstream

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
        if not self.connected_to_hydradb:
            self.in_memory.clear_session(session_id)
            return
        logger.warning(
            "Skipping HydraDB clear for %s: DETACH DELETE degrades on a growing "
            "local WAL. Use a fresh scope or scripts/reset_store instead.",
            session_id,
        )


# Global singleton graph client instance
graph_client = HydraDBClient()
