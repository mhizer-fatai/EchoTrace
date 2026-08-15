import pytest
from backend.app.demo.scenarios import load_contradiction_scenario, load_api_deprecation_scenario
from backend.app.engine.contradiction import detect_contradictions, generate_memory_health_report


def test_contradiction_detection():
    session_id = "test_conflict_session"
    load_contradiction_scenario(session_id)

    contradictions = detect_contradictions(session_id)
    assert len(contradictions) == 1
    assert contradictions[0].entity == "PrimaryStore"
    assert contradictions[0].property_name == "type"
    assert contradictions[0].fact_a_value != contradictions[0].fact_b_value


def test_memory_health_report():
    session_id = "test_health_session"
    load_api_deprecation_scenario(session_id)

    report = generate_memory_health_report(session_id)
    assert report.total_facts >= 3
    assert report.valid_facts >= 3
    assert report.stale_decisions == 0
    assert report.health_score >= 90.0
    assert report.evidence_coverage_pct > 0.0
