import pytest
import uuid
from datetime import datetime, timezone, timedelta
from backend.app.graph.client import graph_client
from backend.app.models.schemas import FactNode, FactStatus, GraphEdge, EdgeType, NodeKind


def test_graph_node_and_edge_insertions():
    session_id = f"test_graph_queries_session_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)

    fact1 = FactNode(
        id="f_q1",
        label="Test Entity: attr",
        entity="TestEntity",
        property_name="attr",
        property_value="val1",
        status=FactStatus.VALID,
        session_id=session_id,
        created_at=now,
        valid_from=now,
    )
    graph_client.add_node(fact1)

    node = graph_client.get_node("f_q1")
    assert node is not None
    assert node["entity"] == "TestEntity"
    assert node["property_value"] == "val1"


def test_temporal_graph_snapshot():
    session_id = f"test_temporal_session_{uuid.uuid4().hex[:10]}"
    t0 = datetime.now(timezone.utc) - timedelta(days=2)
    t1 = datetime.now(timezone.utc) - timedelta(days=1)
    t2 = datetime.now(timezone.utc)

    # Fact valid only between t0 and t1
    f_old = FactNode(
        id="f_temporal_old",
        label="Old Fact",
        entity="System",
        property_name="status",
        property_value="alpha",
        status=FactStatus.SUPERSEDED,
        session_id=session_id,
        created_at=t0,
        valid_from=t0,
        valid_to=t1,
    )
    # Fact valid starting at t1
    f_new = FactNode(
        id="f_temporal_new",
        label="New Fact",
        entity="System",
        property_name="status",
        property_value="beta",
        status=FactStatus.VALID,
        session_id=session_id,
        created_at=t1,
        valid_from=t1,
        valid_to=None,
    )

    graph_client.add_node(f_old)
    graph_client.add_node(f_new)

    # Query snapshot between t0 and t1 (should only contain f_old)
    snapshot_past = graph_client.get_session_graph(
        session_id, snapshot_time=t0 + timedelta(hours=12)
    )
    node_ids_past = [n["id"] for n in snapshot_past["nodes"]]
    assert "f_temporal_old" in node_ids_past
    assert "f_temporal_new" not in node_ids_past

    # Query snapshot at present t2 (should only contain f_new)
    snapshot_present = graph_client.get_session_graph(session_id, snapshot_time=t2)
    node_ids_present = [n["id"] for n in snapshot_present["nodes"]]
    assert "f_temporal_new" in node_ids_present
    assert "f_temporal_old" not in node_ids_present
