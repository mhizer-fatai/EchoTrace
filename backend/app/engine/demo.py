from datetime import datetime, timezone
from typing import Any, Dict

from backend.app.engine.memory import query_memory
from backend.app.graph.client import graph_client
from backend.app.models.schemas import (
    AgentNode,
    ArtifactNode,
    DecisionNode,
    EdgeType,
    FactNode,
    FactStatus,
    GraphEdge,
    MemoryQueryRequest,
    MessageNode,
)


DEMO_SESSION_ID = "memory:demo-user"
DEMO_NODE_IDS = {
    "demo_msg_june",
    "demo_fact_june",
    "demo_msg_october",
    "demo_fact_october",
    "demo_agent_planner",
    "demo_decision_itinerary",
    "demo_artifact_itinerary",
}


def _demo_response() -> Dict[str, Any]:
    answer = query_memory(MemoryQueryRequest(
        user_id="demo-user",
        question="When is my trip?",
    ))
    abstention = query_memory(MemoryQueryRequest(
        user_id="demo-user",
        question="Where did I go to university?",
    ))
    return {
        "session_id": DEMO_SESSION_ID,
        "question": "When is my trip?",
        "answer": answer.model_dump(),
        "unsupported_question_status": abstention.status,
    }


def seed_memory_story() -> Dict[str, Any]:
    existing = graph_client.get_session_graph(DEMO_SESSION_ID)
    existing_ids = {node["id"] for node in existing.get("nodes", [])}
    if DEMO_NODE_IDS.issubset(existing_ids) and len(existing.get("edges", [])) >= 6:
        return _demo_response()

    june_at = datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc)
    october_at = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
    decision_at = datetime(2026, 8, 15, 12, 5, tzinfo=timezone.utc)
    nodes = [
        MessageNode(
            id="demo_msg_june",
            label="Session 04: trip planned for June",
            user_id="demo-user",
            source_session_id="session_04",
            message_index=0,
            role="user",
            content="My trip is in June.",
            session_id=DEMO_SESSION_ID,
            created_at=june_at,
            valid_from=june_at,
        ),
        FactNode(
            id="demo_fact_june",
            label="Trip: June (superseded)",
            entity="demo-user",
            property_name="trip",
            property_value="June",
            status=FactStatus.SUPERSEDED,
            session_id=DEMO_SESSION_ID,
            created_at=june_at,
            valid_from=june_at,
            valid_to=october_at,
            metadata={
                "source_session_id": "session_04",
                "message_index": 0,
                "quote": "My trip is in June.",
            },
        ),
        MessageNode(
            id="demo_msg_october",
            label="Session 18: trip moved to October",
            user_id="demo-user",
            source_session_id="session_18",
            message_index=0,
            role="user",
            content="I moved my trip to October.",
            session_id=DEMO_SESSION_ID,
            created_at=october_at,
            valid_from=october_at,
        ),
        FactNode(
            id="demo_fact_october",
            label="Trip: October (current)",
            entity="demo-user",
            property_name="trip",
            property_value="October",
            status=FactStatus.VALID,
            session_id=DEMO_SESSION_ID,
            created_at=october_at,
            valid_from=october_at,
            metadata={
                "source_session_id": "session_18",
                "message_index": 0,
                "quote": "I moved my trip to October.",
            },
        ),
        AgentNode(
            id="demo_agent_planner",
            label="Travel Planner",
            agent_name="Travel Planner",
            role="itinerary agent",
            session_id=DEMO_SESSION_ID,
            created_at=decision_at,
            valid_from=decision_at,
        ),
        DecisionNode(
            id="demo_decision_itinerary",
            label="Plan the October itinerary",
            agent_id="demo_agent_planner",
            action_type="Plan October trip",
            rationale="The latest supported trip month is October.",
            executor_url="http://host.docker.internal:8001/demo/decision",
            session_id=DEMO_SESSION_ID,
            created_at=decision_at,
            valid_from=decision_at,
        ),
        ArtifactNode(
            id="demo_artifact_itinerary",
            label="October itinerary",
            artifact_name="october_itinerary.md",
            content="# October trip\n\nThe itinerary uses the current memory from session 18.",
            artifact_type="document",
            executor_url="http://host.docker.internal:8001/demo/artifact",
            session_id=DEMO_SESSION_ID,
            created_at=decision_at,
            valid_from=decision_at,
        ),
    ]
    for node in nodes:
        graph_client.add_node(node)

    edges = [
        GraphEdge(id="demo_edge_june_source", source_id="demo_fact_june", target_id="demo_msg_june", edge_type=EdgeType.SUPPORTED_BY, created_at=june_at),
        GraphEdge(id="demo_edge_october_source", source_id="demo_fact_october", target_id="demo_msg_october", edge_type=EdgeType.SUPPORTED_BY, created_at=october_at),
        GraphEdge(id="demo_edge_superseded", source_id="demo_fact_june", target_id="demo_fact_october", edge_type=EdgeType.SUPERSEDED_BY, created_at=october_at),
        GraphEdge(id="demo_edge_agent_decision", source_id="demo_agent_planner", target_id="demo_decision_itinerary", edge_type=EdgeType.PRODUCED, created_at=decision_at),
        GraphEdge(id="demo_edge_decision_memory", source_id="demo_decision_itinerary", target_id="demo_fact_october", edge_type=EdgeType.DEPENDS_ON, created_at=decision_at),
        GraphEdge(id="demo_edge_artifact_decision", source_id="demo_artifact_itinerary", target_id="demo_decision_itinerary", edge_type=EdgeType.DEPENDS_ON, created_at=decision_at),
    ]
    for edge in edges:
        graph_client.add_edge(edge)

    return _demo_response()
