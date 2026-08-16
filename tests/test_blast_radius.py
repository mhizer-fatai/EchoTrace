from unittest.mock import Mock, patch

from backend.app.config import settings
from backend.app.engine.blast_radius import calculate_blast_radius
from backend.app.engine.healer import heal_subgraph
from backend.app.engine.invalidator import invalidate_fact
from backend.app.graph.client import graph_client
from backend.app.models.schemas import InvalidateFactRequest
from tests.fixtures import load_workflow


def test_blast_radius_only_contains_executable_dependents():
    session_id = "test_blast_session"
    load_workflow(session_id)

    report = calculate_blast_radius("fact_api", session_id)

    assert set(node["id"] for node in report.affected_nodes) == {
        "decision_client",
        "artifact_client",
    }
    assert report.remediation_order == ["decision_client", "artifact_client"]


def test_invalidation_reexecutes_webhooks_in_dependency_order():
    session_id = "test_execution_session"
    load_workflow(session_id)
    invalidate_fact(
        InvalidateFactRequest(
            fact_id="fact_api",
            reason="Superseded by current documentation",
            replacement_value="v2",
        ),
        session_id,
    )
    responses = [
        {"success": True, "rationale": "Target v2"},
        {"success": True, "content": "API_VERSION = 'v2'"},
    ]

    def post(url, **kwargs):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = responses.pop(0)
        return response

    previous_hosts = settings.executor_allowed_hosts
    settings.executor_allowed_hosts = "executor.example.test"
    try:
        with patch("backend.app.engine.healer.requests.post", side_effect=post) as request_post:
            result = heal_subgraph(session_id)
    finally:
        settings.executor_allowed_hosts = previous_hosts

    assert result.success is True
    assert result.re_executed_nodes == ["decision_client", "artifact_client"]
    assert [call.args[0] for call in request_post.call_args_list] == [
        "https://executor.example.test/decision",
        "https://executor.example.test/artifact",
    ]
    assert graph_client.get_node("artifact_client")["content"] == "API_VERSION = 'v2'"


def test_failed_executor_leaves_node_stale():
    session_id = "test_failed_execution_session"
    load_workflow(session_id)
    graph_client.mark_node_stale("decision_client")
    previous_hosts = settings.executor_allowed_hosts
    settings.executor_allowed_hosts = "executor.example.test"
    try:
        with patch("backend.app.engine.healer.requests.post", side_effect=RuntimeError("offline")):
            result = heal_subgraph(session_id)
    finally:
        settings.executor_allowed_hosts = previous_hosts

    assert result.success is False
    assert graph_client.get_node("decision_client")["is_stale"] is True
