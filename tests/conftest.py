import pytest

from backend.app.graph.client import graph_client


@pytest.fixture(autouse=True)
def use_isolated_graph_store(monkeypatch):
    monkeypatch.setattr(graph_client, "connected_to_hydradb", False)
