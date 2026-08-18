from datetime import datetime, timezone

from backend.app.graph.client import graph_client
from backend.app.models.schemas import (
    AgentNode,
    ArtifactNode,
    DecisionNode,
    EdgeType,
    EvidenceNode,
    FactNode,
    GraphEdge,
)


def load_workflow(session_id: str) -> None:
    now = datetime.now(timezone.utc)
    nodes = [
        AgentNode(
            id="agent_research",
            label="Research",
            agent_name="Research",
            role="researcher",
            session_id=session_id,
            created_at=now,
            valid_from=now,
        ),
        EvidenceNode(
            id="evidence_api",
            label="API documentation",
            source_uri="https://docs.example.test/api",
            content_snippet="Current API version",
            session_id=session_id,
            created_at=now,
            valid_from=now,
        ),
        FactNode(
            id="fact_api",
            label="API version",
            entity="API",
            property_name="version",
            property_value="v1",
            source_agent_id="agent_research",
            session_id=session_id,
            created_at=now,
            valid_from=now,
        ),
        DecisionNode(
            id="decision_client",
            label="Generate client",
            agent_id="agent_research",
            action_type="code_generation",
            rationale="Target v1",
            executor_url="https://executor.example.test/decision",
            session_id=session_id,
            created_at=now,
            valid_from=now,
        ),
        ArtifactNode(
            id="artifact_client",
            label="client.py",
            artifact_name="client.py",
            content="API_VERSION = 'v1'",
            executor_url="https://executor.example.test/artifact",
            session_id=session_id,
            created_at=now,
            valid_from=now,
        ),
    ]
    for node in nodes:
        graph_client.add_node(node)
    for edge in [
        GraphEdge(id="produced", source_id="agent_research", target_id="fact_api", edge_type=EdgeType.PRODUCED, created_at=now),
        GraphEdge(id="evidence", source_id="fact_api", target_id="evidence_api", edge_type=EdgeType.SUPPORTED_BY, created_at=now),
        GraphEdge(id="decision_dep", source_id="decision_client", target_id="fact_api", edge_type=EdgeType.DEPENDS_ON, created_at=now),
        GraphEdge(id="artifact_dep", source_id="artifact_client", target_id="decision_client", edge_type=EdgeType.DEPENDS_ON, created_at=now),
    ]:
        graph_client.add_edge(edge)
