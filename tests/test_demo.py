from backend.app.engine.demo import DEMO_SESSION_ID, replay_scale_story, seed_memory_story
from backend.app.graph.client import graph_client


def test_memory_story_is_repeatable_and_connected():
    graph_client.clear_session(DEMO_SESSION_ID)

    first = seed_memory_story()
    second = seed_memory_story()
    graph = graph_client.get_session_graph(DEMO_SESSION_ID)

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
    graph_client.clear_session(DEMO_SESSION_ID)

    first = replay_scale_story()
    second = replay_scale_story()
    graph = graph_client.get_session_graph(DEMO_SESSION_ID)
    nodes = graph["nodes"]
    edges = graph["edges"]

    assert first["sessions_requested"] == 30
    assert first["sessions_ingested"] == 30
    assert first["sessions_skipped"] == 0
    assert first["memories_superseded"] >= 10
    assert second["sessions_ingested"] == 0
    assert second["sessions_skipped"] == 30
    assert len([node for node in nodes if node["kind"] == "MESSAGE"]) == 30
    assert len([node for node in nodes if node["kind"] == "FACT"]) == first["memories_created"]
    assert len([edge for edge in edges if edge["edge_type"] == "SUPERSEDED_BY"]) == first["memories_superseded"]
    assert any("university" in node.get("content", "").lower() for node in nodes if node["kind"] == "MESSAGE")
