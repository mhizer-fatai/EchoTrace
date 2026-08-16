from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
import networkx as nx

from backend.app.config import settings
from backend.app.graph.client import graph_client
from backend.app.models.schemas import AutoHealResponse, ExecutorResponse, NodeKind

logger = logging.getLogger("echotrace.engine.healer")


def _execute_node(
    node: Dict[str, Any],
    active_facts: List[Dict[str, Any]],
    completed_nodes: List[Dict[str, Any]],
) -> ExecutorResponse:
    executor_url = node.get("executor_url")
    if not executor_url:
        raise ValueError(f"Stale node '{node['id']}' has no executor_url.")

    parsed_url = urlparse(executor_url)
    allowed_hosts = {
        host.strip().lower()
        for host in settings.executor_allowed_hosts.split(",")
        if host.strip()
    }
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise ValueError(f"Executor URL for '{node['id']}' is invalid.")
    if parsed_url.hostname.lower() not in allowed_hosts:
        raise ValueError(
            f"Executor host '{parsed_url.hostname}' is not in EXECUTOR_ALLOWED_HOSTS."
        )

    headers = {"Content-Type": "application/json"}
    if settings.executor_bearer_token:
        headers["Authorization"] = f"Bearer {settings.executor_bearer_token}"

    response = requests.post(
        executor_url,
        json={
            "node": node,
            "active_facts": active_facts,
            "completed_dependencies": completed_nodes,
        },
        headers=headers,
        timeout=settings.executor_timeout_seconds,
    )
    response.raise_for_status()
    result = ExecutorResponse.model_validate(response.json())
    if not result.success:
        raise ValueError(f"Executor for node '{node['id']}' reported failure.")

    kind = node.get("kind")
    if kind == NodeKind.DECISION.value and not result.rationale:
        raise ValueError(f"Decision executor for '{node['id']}' returned no rationale.")
    if kind == NodeKind.ARTIFACT.value and result.content is None:
        raise ValueError(f"Artifact executor for '{node['id']}' returned no content.")
    return result


def heal_subgraph(
    session_id: str = "default", remediation_order: Optional[List[str]] = None
) -> AutoHealResponse:
    session_data = graph_client.get_session_graph(session_id)
    nodes = {node["id"]: node for node in session_data.get("nodes", [])}
    stale_nodes = [
        node_id for node_id, node in nodes.items() if node.get("is_stale", False)
    ]
    if remediation_order:
        order = remediation_order
    else:
        stale_set = set(stale_nodes)
        execution_graph = nx.DiGraph()
        execution_graph.add_nodes_from(stale_nodes)
        for edge in session_data.get("edges", []):
            source_id = edge["source_id"]
            target_id = edge["target_id"]
            if source_id in stale_set and target_id in stale_set:
                execution_graph.add_edge(target_id, source_id)
        try:
            order = list(nx.topological_sort(execution_graph))
        except nx.NetworkXUnfeasible:
            return AutoHealResponse(
                success=False,
                session_id=session_id,
                re_executed_nodes=[],
                updated_artifacts=[],
                message="Stale subgraph contains a dependency cycle.",
            )
    active_facts = [
        node
        for node in nodes.values()
        if node.get("kind") == NodeKind.FACT.value and node.get("status") == "VALID"
    ]

    re_executed_nodes: List[str] = []
    updated_artifacts: List[Dict[str, Any]] = []
    completed_nodes: List[Dict[str, Any]] = []

    for node_id in order:
        node = nodes.get(node_id)
        if not node or not node.get("is_stale", False):
            continue

        try:
            result = _execute_node(node, active_facts, completed_nodes)
        except Exception as exc:
            logger.error("Executor failed for node %s: %s", node_id, exc)
            return AutoHealResponse(
                success=False,
                session_id=session_id,
                re_executed_nodes=re_executed_nodes,
                updated_artifacts=updated_artifacts,
                message=f"Execution stopped at node '{node_id}': {exc}",
            )

        metadata = dict(node.get("metadata") or {})
        metadata.update(result.metadata)
        metadata["executed_at"] = datetime.now(timezone.utc).isoformat()
        updates: Dict[str, Any] = {"is_stale": False, "metadata": metadata}
        if node.get("kind") == NodeKind.DECISION.value:
            updates["rationale"] = result.rationale
        elif node.get("kind") == NodeKind.ARTIFACT.value:
            updates["content"] = result.content

        updated = graph_client.update_node(node_id, updates) or {**node, **updates}
        nodes[node_id] = updated
        completed_nodes.append(updated)
        re_executed_nodes.append(node_id)
        if node.get("kind") == NodeKind.ARTIFACT.value:
            updated_artifacts.append(
                {
                    "id": node_id,
                    "artifact_name": node.get("artifact_name", "artifact"),
                    "updated_content": result.content,
                }
            )

    return AutoHealResponse(
        success=True,
        session_id=session_id,
        re_executed_nodes=re_executed_nodes,
        updated_artifacts=updated_artifacts,
        message=f"Successfully re-executed {len(re_executed_nodes)} stale nodes.",
    )
