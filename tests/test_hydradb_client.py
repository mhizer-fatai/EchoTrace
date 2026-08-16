from datetime import datetime, timezone
from unittest.mock import Mock

from backend.app.graph.client import HydraDBClient
from backend.app.models.schemas import EdgeType, FactNode, GraphEdge


def test_connected_client_writes_to_hydradb_not_memory():
    client = HydraDBClient.__new__(HydraDBClient)
    client.connected_to_hydradb = True
    client.bolt_driver = Mock()
    client.in_memory = Mock()
    client.execute_cypher = Mock(side_effect=[[], []])
    now = datetime.now(timezone.utc)

    result = client.add_node(FactNode(
        id="fact_remote",
        label="Remote fact",
        entity="Service",
        property_name="version",
        property_value="v2",
        session_id="remote",
        created_at=now,
        valid_from=now,
    ))

    assert result["id"] == "fact_remote"
    assert client.execute_cypher.call_count == 2
    client.in_memory.add_node.assert_not_called()


def test_connected_client_edges_match_existing_nodes():
    client = HydraDBClient.__new__(HydraDBClient)
    client.connected_to_hydradb = True
    client.bolt_driver = Mock()
    client.execute_cypher = Mock()
    edge = GraphEdge(
        id="edge_remote",
        source_id="decision_remote",
        target_id="fact_remote",
        edge_type=EdgeType.DEPENDS_ON,
    )

    client.add_edge(edge)

    query, parameters = client.execute_cypher.call_args.args
    assert "MERGE (source:EchoTraceNode" in query
    assert "target:EchoTraceNode" in query
    assert "CREATE (:EchoTraceNode" not in query
    assert parameters["source_native_id"] == client._native_id("decision_remote")
    assert parameters["target_native_id"] == client._native_id("fact_remote")
