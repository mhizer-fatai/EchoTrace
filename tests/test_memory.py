from datetime import datetime, timedelta, timezone
import uuid

import pytest

from backend.app.engine.memory import ingest_conversation, query_memory
from backend.app.graph.client import graph_client
from backend.app.models.schemas import (
    ConversationMessage,
    IngestConversationRequest,
    MemoryClaim,
    MemoryQueryRequest,
)


def test_cross_session_memory_returns_current_value_and_history():
    user_id = f"memory_user_temporal_{uuid.uuid4().hex[:10]}"
    first = datetime.now(timezone.utc) - timedelta(days=10)
    latest = datetime.now(timezone.utc)

    ingest_conversation(IngestConversationRequest(
        user_id=user_id,
        session_id="session_04",
        messages=[ConversationMessage(
            role="user",
            content="My trip is in June.",
            timestamp=first,
        )],
    ))
    result = ingest_conversation(IngestConversationRequest(
        user_id=user_id,
        session_id="session_18",
        messages=[ConversationMessage(
            role="user",
            content="I moved my trip to October.",
            timestamp=latest,
        )],
    ))
    answer = query_memory(MemoryQueryRequest(
        user_id=user_id,
        question="When is my trip?",
    ))

    assert len(result.memories_superseded) == 1
    assert answer.status == "ANSWERED"
    assert answer.answer == "October"
    assert answer.evidence[0].session_id == "session_18"
    assert answer.history[0].value == "June"
    assert answer.history[0].status == "SUPERSEDED"


def test_memory_query_abstains_without_supporting_evidence():
    user_id = f"memory_user_abstention_{uuid.uuid4().hex[:10]}"
    ingest_conversation(IngestConversationRequest(
        user_id=user_id,
        session_id="session_01",
        messages=[ConversationMessage(role="user", content="My favorite color is green.")],
    ))

    answer = query_memory(MemoryQueryRequest(
        user_id=user_id,
        question="Where did I go to university?",
    ))

    assert answer.status == "INSUFFICIENT_EVIDENCE"
    assert answer.answer is None
    assert answer.evidence == []


def test_explicit_memory_claims_support_unstructured_messages():
    user_id = f"memory_user_explicit_{uuid.uuid4().hex[:10]}"
    result = ingest_conversation(IngestConversationRequest(
        user_id=user_id,
        session_id="session_09",
        messages=[ConversationMessage(
            role="user",
            content="The ceremony has been pushed back until the first Saturday in May.",
        )],
        memories=[MemoryClaim(
            property_name="wedding date",
            property_value="the first Saturday in May",
            message_index=0,
        )],
    ))
    answer = query_memory(MemoryQueryRequest(
        user_id=user_id,
        question="What is the wedding date?",
    ))

    assert len(result.memories_created) == 1
    assert answer.answer == "the first Saturday in May"
    assert answer.evidence[0].quote.startswith("The ceremony")


def test_memory_claim_rejects_invalid_message_index():
    with pytest.raises(ValueError, match="out of range"):
        ingest_conversation(IngestConversationRequest(
            user_id="memory_user_invalid",
            session_id="session_01",
            messages=[ConversationMessage(role="user", content="Hello")],
            memories=[MemoryClaim(
                property_name="location",
                property_value="Berlin",
                message_index=3,
            )],
        ))
