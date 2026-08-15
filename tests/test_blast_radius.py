import pytest
from backend.app.demo.scenarios import load_api_deprecation_scenario
from backend.app.engine.blast_radius import calculate_blast_radius
from backend.app.engine.invalidator import invalidate_fact
from backend.app.engine.healer import heal_subgraph
from backend.app.models.schemas import InvalidateFactRequest, FactStatus


def test_blast_radius_calculation():
    session_id = "test_blast_session"
    load_api_deprecation_scenario(session_id)

    # Calculate blast radius for fact_api_v1
    report = calculate_blast_radius("fact_api_v1", session_id=session_id)

    assert report.invalidated_fact_id == "fact_api_v1"
    # Should affect dec_use_v1 -> dec_generate_client -> art_client_py -> dec_generate_test -> art_test_py
    assert report.affected_nodes_count >= 4
    assert report.affected_decisions_count >= 2
    assert report.affected_artifacts_count >= 2
    assert len(report.remediation_order) >= 4


def test_fact_invalidation_and_heal():
    session_id = "test_invalidation_session"
    load_api_deprecation_scenario(session_id)

    req = InvalidateFactRequest(
        fact_id="fact_api_v1",
        reason="API v1 was deprecated.",
        replacement_value="v2",
        auto_heal=False,
    )
    result = invalidate_fact(req, session_id=session_id)

    assert result["status"] == "success"
    assert result["new_fact_id"] is not None
    assert result["blast_radius"]["affected_nodes_count"] >= 4

    # Now execute selective auto-heal
    heal_resp = heal_subgraph(session_id=session_id)
    assert heal_resp.success is True
    assert len(heal_resp.re_executed_nodes) >= 4
    assert len(heal_resp.updated_artifacts) >= 2
