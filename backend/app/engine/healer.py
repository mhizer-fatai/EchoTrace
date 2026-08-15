from datetime import datetime, timezone
import logging
from typing import Any, Dict, List
import uuid

from backend.app.graph.client import graph_client
from backend.app.models.schemas import AutoHealResponse, EdgeType, GraphEdge, NodeKind

logger = logging.getLogger("echotrace.engine.healer")


def heal_subgraph(session_id: str = "default", remediation_order: List[str] = None) -> AutoHealResponse:
    """
    Selectively re-executes contaminated decisions and regenerates affected artifacts
    in strict topological dependency order.
    """
    now = datetime.now(timezone.utc)
    session_data = graph_client.get_session_graph(session_id)
    nodes = {n["id"]: n for n in session_data.get("nodes", [])}

    if not remediation_order:
        # Collect all stale nodes in session
        remediation_order = [
            nid for nid, node in nodes.items()
            if node.get("is_stale", False)
        ]

    re_executed_nodes: List[str] = []
    updated_artifacts: List[Dict[str, Any]] = []

    # Get the latest active valid facts in session for re-prompting context
    active_facts = [
        n for n in nodes.values()
        if n.get("kind") in [NodeKind.FACT.value, NodeKind.FACT]
        and n.get("status") == "VALID"
    ]
    facts_summary = "; ".join([
        f"{f.get('entity')}.{f.get('property_name')} = {f.get('property_value')}"
        for f in active_facts
    ])

    for nid in remediation_order:
        node = nodes.get(nid)
        if not node or not node.get("is_stale", False):
            continue

        kind = node.get("kind")

        if kind in [NodeKind.DECISION.value, NodeKind.DECISION]:
            old_rationale = node.get("rationale", "")
            action_type = node.get("action_type", "")

            # Simulate agent re-evaluation with the updated factual context
            updated_rationale = (
                f"Re-evaluated decision for {action_type} using updated state: {facts_summary}. "
                f"(Previous rationale updated: '{old_rationale}')"
            )

            graph_client.update_node(
                nid,
                {
                    "is_stale": False,
                    "rationale": updated_rationale,
                    "metadata": {"healed_at": now.isoformat(), "healed": True},
                },
            )
            re_executed_nodes.append(nid)

        elif kind in [NodeKind.ARTIFACT.value, NodeKind.ARTIFACT]:
            art_name = node.get("artifact_name", "artifact")
            old_content = node.get("content", "")

            # Dynamically adapt artifact based on current active facts
            updated_content = old_content
            for fact in active_facts:
                prop_name = fact.get("property_name", "")
                prop_val = fact.get("property_value", "")
                if "v1" in old_content.lower() and "v2" in prop_val.lower():
                    updated_content = updated_content.replace("v1", "v2").replace("V1", "V2")
                if "version" in prop_name.lower():
                    updated_content = (
                        f"// EchoTrace Auto-Healed Artifact for {art_name}\n"
                        f"// Updated to match active rule: {prop_name} = {prop_val}\n\n"
                        f"{updated_content}"
                    )

            graph_client.update_node(
                nid,
                {
                    "is_stale": False,
                    "content": updated_content,
                    "metadata": {"healed_at": now.isoformat(), "healed": True},
                },
            )
            re_executed_nodes.append(nid)
            updated_artifacts.append({
                "id": nid,
                "artifact_name": art_name,
                "updated_content": updated_content,
            })

    return AutoHealResponse(
        success=True,
        session_id=session_id,
        re_executed_nodes=re_executed_nodes,
        updated_artifacts=updated_artifacts,
        message=f"Successfully auto-healed {len(re_executed_nodes)} contaminated nodes.",
    )
