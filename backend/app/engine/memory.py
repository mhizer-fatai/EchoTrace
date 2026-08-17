import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from backend.app.graph.client import graph_client
from backend.app.models.schemas import (
    ConversationMessage,
    EdgeType,
    FactNode,
    FactStatus,
    GraphEdge,
    IngestConversationRequest,
    IngestConversationResponse,
    MemoryCitation,
    MemoryQueryRequest,
    MemoryQueryResponse,
    MessageNode,
)


_STOP_WORDS = {
    "a", "about", "am", "and", "are", "did", "do", "does", "for", "have",
    "i", "in", "is", "it", "me", "my", "of", "on", "the", "to", "what",
    "when", "where", "which", "who", "was",
}

# Maps natural-language query tokens onto the canonical property name so a
# question like "Where do I live?" resolves to the stored "location" fact
# instead of failing on token mismatch.
_PROPERTY_ALIASES = {
    "live": "location",
    "reside": "location",
    "city": "location",
    "work": "workplace",
    "job": "workplace",
    "company": "workplace",
    "employer": "workplace",
    "email": "work_email",
    "prefer": "preference",
    "seat": "preference",
    "color": "favorite_color",
    "phone": "phone_number",
    "cell": "phone_number",
    "passport": "passport_number",
}


def _memory_scope(user_id: str) -> str:
    return f"memory:{user_id}"


def _property_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _extract_message_claims(message: ConversationMessage) -> List[Tuple[str, str]]:
    text = message.content.strip().rstrip(".!?")
    patterns = [
        (r"\bi (?:moved|changed|rescheduled) my (.+?) to (.+)$", lambda m: (m.group(1), m.group(2))),
        (r"\bmy (.+?) (?:is|are) (.+)$", lambda m: (m.group(1), m.group(2))),
        (r"\bi (?:now )?live in (.+)$", lambda m: ("location", m.group(1))),
        (r"\bi (?:now )?work at (.+)$", lambda m: ("workplace", m.group(1))),
        (r"\bi (?:now )?prefer (.+)$", lambda m: ("preference", m.group(1))),
    ]
    for pattern, extract in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            property_name, property_value = extract(match)
            normalized_value = re.sub(
                r"^(?:in|on|at)\s+", "", property_value.strip(), flags=re.IGNORECASE
            )
            return [(_property_name(property_name), normalized_value)]
    return []


def ingest_conversation(request: IngestConversationRequest) -> IngestConversationResponse:
    scope = _memory_scope(request.user_id)
    existing = graph_client.get_session_graph(scope).get("nodes", [])
    active_by_property: Dict[str, Dict] = {
        node["property_name"]: node
        for node in existing
        if node.get("kind") == "FACT"
        and node.get("entity") == request.user_id
        and node.get("status") == FactStatus.VALID.value
    }
    explicit_by_message: Dict[int, List[Tuple[str, str, float]]] = {}
    for claim in request.memories:
        if claim.message_index < 0 or claim.message_index >= len(request.messages):
            raise ValueError(f"Memory claim message_index {claim.message_index} is out of range.")
        explicit_by_message.setdefault(claim.message_index, []).append(
            (_property_name(claim.property_name), claim.property_value, claim.confidence)
        )

    created: List[str] = []
    superseded: List[str] = []
    for index, message in enumerate(request.messages):
        occurred_at = message.timestamp or datetime.now(timezone.utc)
        message_id = f"msg_{uuid.uuid4().hex[:10]}"
        graph_client.add_node(MessageNode(
            id=message_id,
            label=f"{request.session_id} message {index + 1}",
            user_id=request.user_id,
            source_session_id=request.session_id,
            message_index=index,
            role=message.role,
            content=message.content,
            session_id=scope,
            created_at=occurred_at,
            valid_from=occurred_at,
        ))

        claims = explicit_by_message.get(index)
        if claims is None and message.role.lower() == "user":
            claims = [(name, value, 0.85) for name, value in _extract_message_claims(message)]
        for property_name, property_value, confidence in claims or []:
            previous = active_by_property.get(property_name)
            if previous and str(previous.get("property_value")).casefold() == property_value.casefold():
                continue
            fact_id = f"mem_{uuid.uuid4().hex[:10]}"
            metadata = {
                "user_id": request.user_id,
                "source_session_id": request.session_id,
                "message_index": index,
                "quote": message.content,
            }
            graph_client.add_node(FactNode(
                id=fact_id,
                label=f"{property_name.replace('_', ' ')}: {property_value}",
                entity=request.user_id,
                property_name=property_name,
                property_value=property_value,
                confidence=confidence,
                session_id=scope,
                created_at=occurred_at,
                valid_from=occurred_at,
                metadata=metadata,
            ))
            graph_client.add_edge(GraphEdge(
                id=f"edge_memory_source_{fact_id}",
                source_id=fact_id,
                target_id=message_id,
                edge_type=EdgeType.SUPPORTED_BY,
                created_at=occurred_at,
            ))
            if previous:
                graph_client.supersede_fact_nodes(previous["id"], fact_id, occurred_at)
                superseded.append(previous["id"])
            active_by_property[property_name] = graph_client.get_node(fact_id) or {
                "id": fact_id,
                "property_name": property_name,
                "property_value": property_value,
            }
            created.append(fact_id)

    return IngestConversationResponse(
        user_id=request.user_id,
        session_id=request.session_id,
        messages_ingested=len(request.messages),
        memories_created=created,
        memories_superseded=superseded,
    )


def _tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 1 and token not in _STOP_WORDS
    }


def _citation(node: Dict) -> MemoryCitation:
    metadata = node.get("metadata") or {}
    if isinstance(metadata, str):
        import json
        metadata = json.loads(metadata)
    return MemoryCitation(
        fact_id=node["id"],
        session_id=metadata.get("source_session_id", "unknown"),
        message_index=int(metadata.get("message_index", 0)),
        quote=metadata.get("quote", ""),
        value=str(node.get("property_value", "")),
        status=str(node.get("status", "")),
        recorded_at=str(node.get("valid_from", "")),
    )


def query_memory(request: MemoryQueryRequest) -> MemoryQueryResponse:
    nodes = graph_client.get_session_graph(_memory_scope(request.user_id)).get("nodes", [])
    facts = [
        node for node in nodes
        if node.get("kind") == "FACT" and node.get("entity") == request.user_id
    ]
    question_tokens = _tokens(request.question)
    for token in list(question_tokens):
        canonical = _PROPERTY_ALIASES.get(token)
        if canonical:
            question_tokens.add(canonical)
    ranked = []
    for fact in facts:
        property_name = str(fact.get("property_name", ""))
        label_tokens = _tokens(str(fact.get("label", "")))
        # The canonical property name is compared as a single token (e.g.
        # "work_email") so "work email" does not bleed into "workplace".
        property_tokens = {property_name}
        score = len(question_tokens & property_tokens) * 3 + len(question_tokens & label_tokens)
        if score:
            ranked.append((score, fact))
    if not ranked:
        return MemoryQueryResponse(status="INSUFFICIENT_EVIDENCE")

    ranked.sort(key=lambda item: (item[0], str(item[1].get("valid_from", ""))), reverse=True)
    property_name = ranked[0][1]["property_name"]
    related = [fact for fact in facts if fact.get("property_name") == property_name]
    active = [fact for fact in related if fact.get("status") == FactStatus.VALID.value]
    if not active:
        return MemoryQueryResponse(status="INSUFFICIENT_EVIDENCE", property_name=property_name)
    current = max(active, key=lambda fact: str(fact.get("valid_from", "")))
    history = sorted(
        (fact for fact in related if fact["id"] != current["id"]),
        key=lambda fact: str(fact.get("valid_from", "")),
        reverse=True,
    )
    return MemoryQueryResponse(
        status="ANSWERED",
        answer=str(current["property_value"]),
        property_name=property_name,
        evidence=[_citation(current)],
        history=[_citation(fact) for fact in history] if request.include_history else [],
    )
