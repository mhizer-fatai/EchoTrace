from datetime import datetime, timezone
import logging
from typing import Dict, Any, Optional
import uuid

from backend.app.engine.blast_radius import calculate_blast_radius
from backend.app.graph.client import graph_client
from backend.app.models.schemas import (
    BlastRadiusReport,
    EdgeType,
    FactNode,
    FactStatus,
    GraphEdge,
    InvalidateFactRequest,
    NodeKind,
)

logger = logging.getLogger("echotrace.engine.invalidator")


def invalidate_fact(
    request: InvalidateFactRequest, session_id: str = "default"
) -> Dict[str, Any]:
    """
    Executes a formal invalidation of a fact node in HydraDB:
    1. Identifies the blast radius of contaminated decisions and artifacts.
    2. Marks the fact node as INVALIDATED with valid_to set to current timestamp.
    3. If replacement_value is provided, creates a new superseding fact node and links it with SUPERSEDED_BY.
    4. Marks all downstream dependent nodes as stale.
    5. Returns the blast radius report and remediation data.
    """
    now = datetime.now(timezone.utc)
    old_fact = graph_client.get_node(request.fact_id)
    if not old_fact:
        raise ValueError(f"Fact with ID '{request.fact_id}' not found.")

    # 1. Calculate downstream blast radius before mutating
    blast_report: BlastRadiusReport = calculate_blast_radius(request.fact_id, session_id)

    # 2. Mark old fact as INVALIDATED
    graph_client.invalidate_fact_node(request.fact_id, now)

    new_fact_id: Optional[str] = None

    # 3. Create superseding fact if replacement value is provided
    if request.replacement_value:
        new_fact_id = f"fact_{uuid.uuid4().hex[:8]}"
        new_fact = FactNode(
            id=new_fact_id,
            label=f"{old_fact.get('entity')}: {old_fact.get('property_name')}",
            entity=old_fact.get("entity", "Unknown"),
            property_name=old_fact.get("property_name", "attribute"),
            property_value=request.replacement_value,
            status=FactStatus.VALID,
            confidence=1.0,
            source_agent_id=old_fact.get("source_agent_id"),
            session_id=session_id,
            created_at=now,
            valid_from=now,
            valid_to=None,
            metadata={"superseded_from": request.fact_id, "invalidation_reason": request.reason},
        )
        graph_client.add_node(new_fact)

        # Create SUPERSEDED_BY edge: old_fact -> new_fact
        graph_client.supersede_fact_nodes(request.fact_id, new_fact_id, now)

        # If evidence was provided, link evidence
        if request.evidence_uri:
            ev_id = f"ev_{uuid.uuid4().hex[:8]}"
            graph_client.add_node(
                {
                    "id": ev_id,
                    "kind": NodeKind.EVIDENCE.value,
                    "label": f"Evidence: {request.evidence_uri}",
                    "source_uri": request.evidence_uri,
                    "content_snippet": f"Updated statement: {request.replacement_value}",
                    "verified": True,
                    "session_id": session_id,
                    "created_at": now.isoformat(),
                    "valid_from": now.isoformat(),
                }
            )
            graph_client.add_edge(
                GraphEdge(
                    id=f"edge_ev_{new_fact_id}_{ev_id}",
                    source_id=new_fact_id,
                    target_id=ev_id,
                    edge_type=EdgeType.SUPPORTED_BY,
                    created_at=now,
                )
            )

    # 4. Mark all affected downstream decisions and artifacts as stale
    for affected_node in blast_report.affected_nodes:
        nid = affected_node["id"]
        graph_client.mark_node_stale(nid, is_stale=True)

    return {
        "status": "success",
        "invalidated_fact_id": request.fact_id,
        "new_fact_id": new_fact_id,
        "blast_radius": blast_report.model_dump(),
        "invalidated_at": now.isoformat(),
        "reason": request.reason,
    }
