from datetime import datetime, timezone

from backend.app.engine.contradiction import detect_contradictions, generate_memory_health_report
from backend.app.graph.client import graph_client
from backend.app.models.schemas import FactNode
from tests.fixtures import load_workflow


def test_contradiction_detection():
    session_id = "test_conflict_session"
    graph_client.clear_session(session_id)
    now = datetime.now(timezone.utc)
    for fact_id, value in [("fact_pg", "PostgreSQL"), ("fact_mongo", "MongoDB")]:
        graph_client.add_node(FactNode(
            id=fact_id,
            label=value,
            entity="PrimaryStore",
            property_name="type",
            property_value=value,
            session_id=session_id,
            created_at=now,
            valid_from=now,
        ))

    contradictions = detect_contradictions(session_id)
    assert len(contradictions) == 1
    assert contradictions[0].fact_a_value != contradictions[0].fact_b_value


def test_memory_health_report():
    session_id = "test_health_session"
    load_workflow(session_id)
    report = generate_memory_health_report(session_id)
    assert report.total_facts == 1
    assert report.evidence_coverage_pct == 100.0
    assert report.health_score == 100.0
