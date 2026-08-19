from datetime import datetime, timedelta, timezone
import uuid

from backend.app.engine.memory import ingest_conversation, query_memory
from backend.app.graph.client import graph_client
from backend.app.models.schemas import (
    ConversationMessage,
    FactNode,
    FactStatus,
    IngestConversationRequest,
    MemoryQueryRequest,
)


def _user_with_conflicting_trip():
    user_id = f"conflict_user_{uuid.uuid4().hex[:10]}"
    scope = f"memory:{user_id}"
    first = datetime.now(timezone.utc) - timedelta(days=2)
    now = datetime.now(timezone.utc)

    ingest_conversation(IngestConversationRequest(
        user_id=user_id,
        session_id="session_01",
        messages=[ConversationMessage(role="user", content="My trip is in June.", timestamp=first)],
    ))
    # A second source records a conflicting value WITHOUT an explicit update,
    # so both facts remain active side-by-side.
    graph_client.add_node(FactNode(
        id=f"mem_conflict_{uuid.uuid4().hex[:8]}",
        label="trip: July",
        entity=user_id,
        property_name="trip",
        property_value="July",
        status=FactStatus.VALID,
        session_id=scope,
        created_at=now,
        valid_from=now,
        metadata={"source_session_id": "session_05", "message_index": 0, "quote": "My trip is in July."},
    ))
    return user_id


def test_query_abstains_with_conflict_when_two_active_facts_disagree():
    user_id = _user_with_conflicting_trip()
    answer = query_memory(MemoryQueryRequest(user_id=user_id, question="When is my trip?"))

    assert answer.status == "CONFLICT"
    assert answer.property_name == "trip"
    assert answer.answer is None
    assert len(answer.evidence) == 2
    assert {citation.value for citation in answer.evidence} == {"June", "July"}


def test_single_active_fact_still_answers():
    user_id = f"conflict_single_{uuid.uuid4().hex[:10]}"
    ingest_conversation(IngestConversationRequest(
        user_id=user_id,
        session_id="session_01",
        messages=[ConversationMessage(role="user", content="My trip is in June.")],
    ))
    answer = query_memory(MemoryQueryRequest(user_id=user_id, question="When is my trip?"))

    assert answer.status == "ANSWERED"
    assert answer.answer == "June"
    assert len(answer.evidence) == 1


def test_explicit_change_supersedes_all_conflicting_facts():
    user_id = _user_with_conflicting_trip()
    later = datetime.now(timezone.utc) + timedelta(minutes=5)
    result = ingest_conversation(IngestConversationRequest(
        user_id=user_id,
        session_id="session_06",
        messages=[ConversationMessage(role="user", content="I moved my trip to October.", timestamp=later)],
    ))

    # Both June and July must be superseded, not just one of them.
    assert len(result.memories_superseded) == 2

    answer = query_memory(MemoryQueryRequest(user_id=user_id, question="When is my trip?"))
    assert answer.status == "ANSWERED"
    assert answer.answer == "October"
    assert {citation.value for citation in answer.history} == {"June", "July"}