from datetime import datetime, timezone
import uuid
from typing import Any, Dict, Optional
from pydantic import BaseModel

from backend.app.graph.client import graph_client
from backend.app.models.schemas import (
    EdgeType,
    FactNode,
    FactStatus,
    GraphEdge,
    MessageNode,
)


class SourceAssertRequest(BaseModel):
    """A source records a claim about an entity's property.

    Unlike conversation ingestion, asserting a claim does NOT supersede an
    existing fact. Coexisting claims on the same property become a conflict
    that query-time detection surfaces as CONFLICT (abstention) until an
    explicit change supersedes all of them.
    """

    session_id: str = "memory:demo-user"
    entity: str = "demo-user"
    property_name: str = "trip"
    property_value: str = "July"
    source_session_id: str = "session_05"
    source_agent_id: Optional[str] = "demo_agent_flight_agent"
    quote: Optional[str] = "My trip is in July."


def assert_source_claim(request: SourceAssertRequest) -> Dict[str, Any]:
    existing = graph_client.get_session_graph(request.session_id).get("nodes", [])
    already_recorded = any(
        node.get("kind") == "FACT"
        and node.get("entity") == request.entity
        and node.get("property_name") == request.property_name
        and str(node.get("property_value", "")).casefold() == request.property_value.casefold()
        and (node.get("metadata") or {}).get("source_session_id") == request.source_session_id
        for node in existing
    )

    if not already_recorded:
        now = datetime.now(timezone.utc)
        msg_id = f"msg_{uuid.uuid4().hex[:10]}"
        fact_id = f"mem_{uuid.uuid4().hex[:10]}"
        quote = request.quote or request.property_value
        graph_client.add_node(MessageNode(
            id=msg_id,
            label=f"{request.source_session_id}: {quote[:30]}",
            user_id=request.entity,
            source_session_id=request.source_session_id,
            message_index=0,
            role="user",
            content=quote,
            session_id=request.session_id,
            created_at=now,
            valid_from=now,
        ))
        graph_client.add_node(FactNode(
            id=fact_id,
            label=f"{request.property_name.replace('_', ' ')}: {request.property_value}",
            entity=request.entity,
            property_name=request.property_name,
            property_value=request.property_value,
            status=FactStatus.VALID,
            source_agent_id=request.source_agent_id,
            session_id=request.session_id,
            created_at=now,
            valid_from=now,
            metadata={
                "source_session_id": request.source_session_id,
                "message_index": 0,
                "quote": quote,
            },
        ))
        graph_client.add_edge(GraphEdge(
            id=f"edge_memory_source_{fact_id}",
            source_id=fact_id,
            target_id=msg_id,
            edge_type=EdgeType.SUPPORTED_BY,
            created_at=now,
        ))

    active_facts = [
        node for node in graph_client.get_session_graph(request.session_id).get("nodes", [])
        if node.get("kind") == "FACT"
        and node.get("entity") == request.entity
        and node.get("property_name") == request.property_name
        and node.get("status") == FactStatus.VALID.value
    ]
    return {
        "status": "already_recorded" if already_recorded else "asserted",
        "session_id": request.session_id,
        "entity": request.entity,
        "property_name": request.property_name,
        "property_value": request.property_value,
        "source_session_id": request.source_session_id,
        "source_agent_id": request.source_agent_id,
        "active_facts": [
            {
                "id": node["id"],
                "property_name": node.get("property_name", ""),
                "property_value": node.get("property_value", ""),
                "source_session_id": (node.get("metadata") or {}).get("source_session_id", ""),
            }
            for node in active_facts
        ],
        "hydradb_connected": graph_client.connected_to_hydradb,
        "engine_mode": "HydraDB Bolt" if graph_client.connected_to_hydradb else "Internal Graph Engine",
    }