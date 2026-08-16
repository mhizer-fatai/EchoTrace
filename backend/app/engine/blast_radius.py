import logging
from typing import Any, Dict, List
import networkx as nx

from backend.app.graph.client import graph_client
from backend.app.models.schemas import BlastRadiusReport, NodeKind

logger = logging.getLogger("echotrace.engine.blast_radius")


def calculate_blast_radius(fact_id: str, session_id: str = "default") -> BlastRadiusReport:
    """
    Computes the downstream blast radius when a fact is invalidated.
    Traverses all decisions, tool calls, and generated artifacts that directly
    or transitively depend on the invalidated fact.
    """
    fact_node = graph_client.get_node(fact_id)
    if not fact_node:
        raise ValueError(f"Fact with ID '{fact_id}' not found in graph.")

    fact_text = f"{fact_node.get('entity')}: {fact_node.get('property_name')} = {fact_node.get('property_value')}"

    # Query all downstream dependent node IDs
    downstream_ids = graph_client.get_downstream_dependencies(fact_id, session_id)

    affected_nodes: List[Dict[str, Any]] = []
    affected_decisions_count = 0
    affected_artifacts_count = 0

    for nid in downstream_ids:
        node = graph_client.get_node(nid)
        if node:
            affected_nodes.append(node)
            kind = node.get("kind")
            if kind == NodeKind.DECISION.value or kind == NodeKind.DECISION:
                affected_decisions_count += 1
            elif kind == NodeKind.ARTIFACT.value or kind == NodeKind.ARTIFACT:
                affected_artifacts_count += 1

    # Build a local projection of the authoritative session graph for path reporting
    contamination_paths: List[List[str]] = []
    session_graph = graph_client.get_session_graph(session_id)
    subgraph = nx.DiGraph()
    subgraph.add_nodes_from(node["id"] for node in session_graph.get("nodes", []))
    for edge in session_graph.get("edges", []):
        subgraph.add_edge(edge["source_id"], edge["target_id"])

    for target_id in downstream_ids:
        try:
            # Look for paths from target back to fact (since dependency edges go dependent -> fact)
            if nx.has_path(subgraph, target_id, fact_id):
                for path in nx.all_simple_paths(subgraph, source=target_id, target=fact_id, cutoff=10):
                    # Reverse path so it shows: fact -> decision -> artifact
                    contamination_paths.append(list(reversed(path)))
        except Exception as exc:
            logger.debug(f"Path search warning for {target_id}: {exc}")

    # Compute remediation order (topological sort of contaminated subgraph)
    remediation_order: List[str] = []
    if downstream_ids:
        sub_dag = nx.DiGraph()
        for nid in downstream_ids:
            sub_dag.add_node(nid)

        for u in downstream_ids:
            for v in downstream_ids:
                if subgraph.has_edge(u, v):
                    # Edge u -> v means u depends on v, so v must be re-run before u
                    sub_dag.add_edge(v, u)

        try:
            remediation_order = list(nx.topological_sort(sub_dag))
        except nx.NetworkXUnfeasible:
            # In case of cycles, fallback to basic list
            remediation_order = downstream_ids

    return BlastRadiusReport(
        invalidated_fact_id=fact_id,
        invalidated_fact_text=fact_text,
        affected_nodes_count=len(affected_nodes),
        affected_decisions_count=affected_decisions_count,
        affected_artifacts_count=affected_artifacts_count,
        affected_nodes=affected_nodes,
        contamination_paths=contamination_paths,
        remediation_order=remediation_order,
    )
