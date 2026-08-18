import pytest

from backend.app.engine import demo
from backend.app.graph.client import graph_client
from backend.app.engine.memory import query_memory
from backend.app.models.schemas import MemoryQueryRequest


TEST_SESSION_ID = "memory:test-demo"
TEST_USER_ID = "test-demo"


@pytest.fixture(autouse=True)
def isolated_demo_scope(monkeypatch):
    """Route every demo engine call into a throwaway scope so the tests
    never write into the live demo-user graph the website reads."""
    monkeypatch.setattr(demo, "DEMO_SESSION_ID", TEST_SESSION_ID)
    monkeypatch.setattr(demo, "DEMO_USER_ID", TEST_USER_ID)
    graph_client.clear_session(TEST_SESSION_ID)
    yield
    graph_client.clear_session(TEST_SESSION_ID)


def test_memory_story_is_repeatable_and_connected():
    first = demo.seed_memory_story()
    second = demo.seed_memory_story()
    graph = graph_client.get_session_graph(TEST_SESSION_ID)

    assert first["answer"]["answer"] == "October"
    assert first["answer"]["history"][0]["value"] == "June"
    assert first["unsupported_question_status"] == "INSUFFICIENT_EVIDENCE"
    assert second["answer"]["answer"] == "October"
    assert len(graph["nodes"]) == 7
    assert len(graph["edges"]) == 6
    assert {node["kind"].value if hasattr(node["kind"], "value") else node["kind"] for node in graph["nodes"]} == {
        "MESSAGE", "FACT", "AGENT", "DECISION", "ARTIFACT"
    }


def test_scale_story_replays_through_real_memory_pipeline_idempotently():
    first = demo.replay_scale_story()
    second = demo.replay_scale_story()
    graph = graph_client.get_session_graph(TEST_SESSION_ID)
    nodes = graph["nodes"]
    edges = graph["edges"]

    assert first["sessions_requested"] == 35
    assert first["sessions_ingested"] == 35
    assert first["sessions_skipped"] == 0
    assert first["memories_superseded"] >= 10
    assert second["sessions_ingested"] == 0
    assert second["sessions_skipped"] == 35
    assert len([node for node in nodes if node["kind"] == "MESSAGE"]) == 35
    assert len([node for node in nodes if node["kind"] == "FACT"]) == first["memories_created"]
    assert len([edge for edge in edges if edge["edge_type"] == "SUPERSEDED_BY"]) == first["memories_superseded"]
    assert any("university" in node.get("content", "").lower() for node in nodes if node["kind"] == "MESSAGE")


def test_multi_hop_query_walks_timeline_across_properties():
    demo.replay_scale_story()

    workplace = query_memory(MemoryQueryRequest(
        user_id=TEST_USER_ID,
        question="Which workplace was active when my trip was in July?",
    ))
    assert workplace.status == "ANSWERED"
    assert workplace.answer == "Vertex Labs"
    assert workplace.property_name == "workplace"
    assert workplace.anchor_property_name == "trip"
    assert workplace.anchor_value == "July"

    email = query_memory(MemoryQueryRequest(
        user_id=TEST_USER_ID,
        question="What was my work email when my trip was in July?",
    ))
    assert email.status == "ANSWERED"
    assert email.answer == "sarah@vertexlabs.ai"
    assert email.property_name == "work_email"

    snapshot = query_memory(MemoryQueryRequest(
        user_id=TEST_USER_ID,
        question="What was my trip?",
        as_of="2026-08-16T09:10:00+00:00",
    ))
    assert snapshot.status == "ANSWERED"
    assert snapshot.answer == "October"
    assert snapshot.as_of is not None