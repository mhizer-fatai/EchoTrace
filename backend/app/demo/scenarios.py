from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from backend.app.graph.client import graph_client
from backend.app.models.schemas import (
    AgentNode,
    ArtifactNode,
    DecisionNode,
    EdgeType,
    EvidenceNode,
    FactNode,
    FactStatus,
    GraphEdge,
    NodeKind,
    ToolCallNode,
)


def load_api_deprecation_scenario(session_id: str = "api_deprecation_demo") -> Dict[str, Any]:
    """
    Populates a complete 4-agent collaborative software engineering pipeline:
    Researcher -> Planner -> Coder -> Tester
    """
    graph_client.clear_session(session_id)
    t0 = datetime.now(timezone.utc) - timedelta(hours=2)

    # 1. Agents
    researcher = AgentNode(
        id="agent_researcher",
        label="Researcher Agent",
        agent_name="ResearchAgent",
        role="API Specification Analyst",
        session_id=session_id,
        created_at=t0,
        valid_from=t0,
    )
    planner = AgentNode(
        id="agent_planner",
        label="Planner Agent",
        agent_name="ArchitecturePlanner",
        role="System Architect",
        session_id=session_id,
        created_at=t0,
        valid_from=t0,
    )
    coder = AgentNode(
        id="agent_coder",
        label="Coder Agent",
        agent_name="IntegrationCoder",
        role="Software Engineer",
        session_id=session_id,
        created_at=t0,
        valid_from=t0,
    )
    tester = AgentNode(
        id="agent_tester",
        label="Tester Agent",
        agent_name="QualityAssurance",
        role="Test Automation Engineer",
        session_id=session_id,
        created_at=t0,
        valid_from=t0,
    )

    for ag in [researcher, planner, coder, tester]:
        graph_client.add_node(ag)

    # 2. Evidence & Facts
    ev_api = EvidenceNode(
        id="ev_api_docs",
        label="Docs: PaymentsAPI.pdf",
        source_uri="https://api.payments-corp.com/docs/v1",
        content_snippet="Payments API v1 is the primary production release.",
        session_id=session_id,
        created_at=t0,
        valid_from=t0,
    )
    ev_auth = EvidenceNode(
        id="ev_auth_spec",
        label="Spec: AuthSecurity.md",
        source_uri="https://api.payments-corp.com/docs/auth",
        content_snippet="Bearer Token Authentication is required for v1 transactions.",
        session_id=session_id,
        created_at=t0,
        valid_from=t0,
    )
    ev_db = EvidenceNode(
        id="ev_db_arch",
        label="Arch: DatabaseRFC.pdf",
        source_uri="https://internal.wiki/arch/rfc-102",
        content_snippet="PostgreSQL cluster selected for ACID payment records.",
        session_id=session_id,
        created_at=t0,
        valid_from=t0,
    )
    for ev in [ev_api, ev_auth, ev_db]:
        graph_client.add_node(ev)

    fact_api_version = FactNode(
        id="fact_api_v1",
        label="PaymentsAPI: Version = v1",
        entity="PaymentsAPI",
        property_name="version",
        property_value="v1",
        status=FactStatus.VALID,
        source_agent_id="agent_researcher",
        session_id=session_id,
        created_at=t0,
        valid_from=t0,
    )
    fact_auth_type = FactNode(
        id="fact_auth_bearer",
        label="PaymentsAPI: Auth = Bearer",
        entity="PaymentsAPI",
        property_name="auth_type",
        property_value="Bearer",
        status=FactStatus.VALID,
        source_agent_id="agent_researcher",
        session_id=session_id,
        created_at=t0,
        valid_from=t0,
    )
    fact_db = FactNode(
        id="fact_db_engine",
        label="Database: Engine = Postgres",
        entity="Database",
        property_name="engine",
        property_value="Postgres",
        status=FactStatus.VALID,
        source_agent_id="agent_planner",
        session_id=session_id,
        created_at=t0,
        valid_from=t0,
    )

    for f in [fact_api_version, fact_auth_type, fact_db]:
        graph_client.add_node(f)

    # Edges: Agent -> Produced -> Fact
    graph_client.add_edge(GraphEdge(
        id="edge_ag_f1", source_id="agent_researcher", target_id="fact_api_v1",
        edge_type=EdgeType.PRODUCED, created_at=t0
    ))
    graph_client.add_edge(GraphEdge(
        id="edge_ag_f2", source_id="agent_researcher", target_id="fact_auth_bearer",
        edge_type=EdgeType.PRODUCED, created_at=t0
    ))
    graph_client.add_edge(GraphEdge(
        id="edge_ag_f3", source_id="agent_planner", target_id="fact_db_engine",
        edge_type=EdgeType.PRODUCED, created_at=t0
    ))
    graph_client.add_edge(GraphEdge(
        id="edge_ev_f1", source_id="fact_api_v1", target_id="ev_api_docs",
        edge_type=EdgeType.SUPPORTED_BY, created_at=t0
    ))
    graph_client.add_edge(GraphEdge(
        id="edge_ev_f2", source_id="fact_auth_bearer", target_id="ev_auth_spec",
        edge_type=EdgeType.SUPPORTED_BY, created_at=t0
    ))
    graph_client.add_edge(GraphEdge(
        id="edge_ev_f3", source_id="fact_db_engine", target_id="ev_db_arch",
        edge_type=EdgeType.SUPPORTED_BY, created_at=t0
    ))

    # 3. Decisions
    t1 = t0 + timedelta(minutes=15)
    dec_arch = DecisionNode(
        id="dec_use_v1",
        label="Decision: Integrate v1 Gateway",
        agent_id="agent_planner",
        action_type="ArchitectureSelection",
        rationale="Selected PaymentsAPI v1 SDK based on research specification.",
        is_stale=False,
        session_id=session_id,
        created_at=t1,
        valid_from=t1,
    )
    dec_db = DecisionNode(
        id="dec_db_schema",
        label="Decision: Postgres Transaction Store",
        agent_id="agent_planner",
        action_type="DatabaseDesign",
        rationale="Configure ACID transaction tables for Postgres.",
        is_stale=False,
        session_id=session_id,
        created_at=t1,
        valid_from=t1,
    )

    for d in [dec_arch, dec_db]:
        graph_client.add_node(d)

    # Decision dependencies
    graph_client.add_edge(GraphEdge(
        id="edge_d1_f1", source_id="dec_use_v1", target_id="fact_api_v1",
        edge_type=EdgeType.DEPENDS_ON, created_at=t1
    ))
    graph_client.add_edge(GraphEdge(
        id="edge_d1_f2", source_id="dec_use_v1", target_id="fact_auth_bearer",
        edge_type=EdgeType.DEPENDS_ON, created_at=t1
    ))
    graph_client.add_edge(GraphEdge(
        id="edge_d2_f3", source_id="dec_db_schema", target_id="fact_db_engine",
        edge_type=EdgeType.DEPENDS_ON, created_at=t1
    ))
    graph_client.add_edge(GraphEdge(
        id="edge_ag_d1", source_id="agent_planner", target_id="dec_use_v1",
        edge_type=EdgeType.PRODUCED, created_at=t1
    ))
    graph_client.add_edge(GraphEdge(
        id="edge_ag_d2", source_id="agent_planner", target_id="dec_db_schema",
        edge_type=EdgeType.PRODUCED, created_at=t1
    ))

    # 4. Coding Agent Decisions and Artifacts
    t2 = t1 + timedelta(minutes=20)
    dec_code = DecisionNode(
        id="dec_generate_client",
        label="Decision: Write PaymentsClient",
        agent_id="agent_coder",
        action_type="CodeGeneration",
        rationale="Implement client class wrapping v1 HTTP endpoints with Bearer auth headers.",
        is_stale=False,
        session_id=session_id,
        created_at=t2,
        valid_from=t2,
    )
    graph_client.add_node(dec_code)

    graph_client.add_edge(GraphEdge(
        id="edge_d3_d1", source_id="dec_generate_client", target_id="dec_use_v1",
        edge_type=EdgeType.DEPENDS_ON, created_at=t2
    ))
    graph_client.add_edge(GraphEdge(
        id="edge_ag_d3", source_id="agent_coder", target_id="dec_generate_client",
        edge_type=EdgeType.PRODUCED, created_at=t2
    ))

    art_client = ArtifactNode(
        id="art_client_py",
        label="Artifact: payments_client.py",
        artifact_name="payments_client.py",
        content="""import requests

class PaymentsClient:
    def __init__(self, api_key: str):
        self.base_url = "https://api.payments-corp.com/v1"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def charge(self, amount: int, currency: str = "USD"):
        url = f"{self.base_url}/charges"
        payload = {"amount": amount, "currency": currency}
        return requests.post(url, json=payload, headers=self.headers)
""",
        artifact_type="code",
        is_stale=False,
        session_id=session_id,
        created_at=t2,
        valid_from=t2,
    )
    graph_client.add_node(art_client)

    graph_client.add_edge(GraphEdge(
        id="edge_art1_d3", source_id="art_client_py", target_id="dec_generate_client",
        edge_type=EdgeType.DEPENDS_ON, created_at=t2
    ))

    # 5. Testing Agent Decisions and Artifacts
    t3 = t2 + timedelta(minutes=15)
    dec_test = DecisionNode(
        id="dec_generate_test",
        label="Decision: Generate Unit Tests",
        agent_id="agent_tester",
        action_type="TestGeneration",
        rationale="Generate mock tests targeting the v1 /charges endpoint contract.",
        is_stale=False,
        session_id=session_id,
        created_at=t3,
        valid_from=t3,
    )
    graph_client.add_node(dec_test)

    graph_client.add_edge(GraphEdge(
        id="edge_d4_art1", source_id="dec_generate_test", target_id="art_client_py",
        edge_type=EdgeType.DEPENDS_ON, created_at=t3
    ))
    graph_client.add_edge(GraphEdge(
        id="edge_ag_d4", source_id="agent_tester", target_id="dec_generate_test",
        edge_type=EdgeType.PRODUCED, created_at=t3
    ))

    art_test = ArtifactNode(
        id="art_test_py",
        label="Artifact: test_payments.py",
        artifact_name="test_payments.py",
        content="""import pytest
from payments_client import PaymentsClient

def test_v1_charge(requests_mock):
    requests_mock.post("https://api.payments-corp.com/v1/charges", json={"status": "succeeded"})
    client = PaymentsClient(api_key="test_key")
    resp = client.charge(1000)
    assert resp.json()["status"] == "succeeded"
""",
        artifact_type="code",
        is_stale=False,
        session_id=session_id,
        created_at=t3,
        valid_from=t3,
    )
    graph_client.add_node(art_test)

    graph_client.add_edge(GraphEdge(
        id="edge_art2_d4", source_id="art_test_py", target_id="dec_generate_test",
        edge_type=EdgeType.DEPENDS_ON, created_at=t3
    ))

    return graph_client.get_session_graph(session_id)


def load_contradiction_scenario(session_id: str = "conflict_demo") -> Dict[str, Any]:
    """
    Populates a scenario with active conflicting beliefs to demonstrate the Contradiction Monitor.
    """
    graph_client.clear_session(session_id)
    now = datetime.now(timezone.utc)

    # Agents
    ag1 = AgentNode(id="ag_infra_1", label="Infra Agent East", agent_name="InfraEast", role="Infra", session_id=session_id)
    ag2 = AgentNode(id="ag_infra_2", label="Infra Agent West", agent_name="InfraWest", role="Infra", session_id=session_id)
    graph_client.add_node(ag1)
    graph_client.add_node(ag2)

    # Conflicting Facts
    f1 = FactNode(
        id="fact_db_pg",
        label="PrimaryStore: type = PostgreSQL",
        entity="PrimaryStore",
        property_name="type",
        property_value="PostgreSQL",
        status=FactStatus.VALID,
        source_agent_id="ag_infra_1",
        session_id=session_id,
        created_at=now - timedelta(hours=1),
        valid_from=now - timedelta(hours=1),
    )
    f2 = FactNode(
        id="fact_db_mongo",
        label="PrimaryStore: type = MongoDB",
        entity="PrimaryStore",
        property_name="type",
        property_value="MongoDB",
        status=FactStatus.VALID,
        source_agent_id="ag_infra_2",
        session_id=session_id,
        created_at=now,
        valid_from=now,
    )
    graph_client.add_node(f1)
    graph_client.add_node(f2)

    graph_client.add_edge(GraphEdge(
        id="edge_c1", source_id="ag_infra_1", target_id="fact_db_pg",
        edge_type=EdgeType.PRODUCED, created_at=now
    ))
    graph_client.add_edge(GraphEdge(
        id="edge_c2", source_id="ag_infra_2", target_id="fact_db_mongo",
        edge_type=EdgeType.PRODUCED, created_at=now
    ))

    return graph_client.get_session_graph(session_id)
