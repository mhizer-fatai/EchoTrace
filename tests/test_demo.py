from backend.app.engine.demo import DEMO_SESSION_ID, seed_memory_story
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
