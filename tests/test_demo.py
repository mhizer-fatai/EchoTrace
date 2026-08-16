from backend.app.engine.demo import DEMO_SESSION_ID, seed_track_three_demo
from backend.app.graph.client import graph_client


def test_track_three_demo_is_repeatable_and_connected():
    graph_client.clear_session(DEMO_SESSION_ID)

    first = seed_track_three_demo()
    second = seed_track_three_demo()
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
