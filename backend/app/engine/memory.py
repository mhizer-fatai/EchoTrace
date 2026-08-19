import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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
    active_by_property: Dict[str, List[Dict]] = {}
    for node in existing:
        if (
            node.get("kind") == "FACT"
            and node.get("entity") == request.user_id
            and node.get("status") == FactStatus.VALID.value
        ):
            active_by_property.setdefault(node["property_name"], []).append(node)
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
            previous_active = active_by_property.get(property_name) or []
            if any(
                str(previous.get("property_value")).casefold() == property_value.casefold()
                for previous in previous_active
            ):
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
            # Supersede every currently-active fact for this property so an
            # explicit change resolves prior conflicts instead of leaving
            # contradictory claims valid side-by-side.
            for previous in previous_active:
                graph_client.supersede_fact_nodes(previous["id"], fact_id, occurred_at)
                superseded.append(previous["id"])
            active_by_property[property_name] = [graph_client.get_node(fact_id) or {
                "id": fact_id,
                "property_name": property_name,
                "property_value": property_value,
            }]
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


def _as_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_as_of(explicit: Optional[str]) -> Optional[datetime]:
    if not explicit:
        return None
    return _as_datetime(explicit)


def _parse_as_of_from_question(question: str) -> Optional[datetime]:
    match = re.search(
        r"\bas of\s+([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})", question, re.IGNORECASE
    )
    if not match:
        return None
    try:
        return datetime(
            int(match.group(1)), int(match.group(2)), int(match.group(3)),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None


def _mentioned_properties(facts: List[Dict], question_tokens: set) -> set:
    """Properties the question explicitly points at (via alias or property name)."""
    mentioned = set()
    for token in question_tokens:
        canonical = _PROPERTY_ALIASES.get(token)
        if canonical:
            mentioned.add(canonical)
    for fact in facts:
        property_name = str(fact.get("property_name", ""))
        property_parts = {
            token for token in re.findall(r"[a-z0-9]+", property_name.lower())
            if len(token) > 1
        }
        if property_parts & question_tokens:
            mentioned.add(property_name)
    return mentioned


def _value_matched_properties(facts: List[Dict], question_tokens: set) -> List[str]:
    """Properties whose stored value words appear in the question (e.g. 'October')."""
    value_tokens_by_property: Dict[str, set] = {}
    for fact in facts:
        property_name = str(fact.get("property_name", ""))
        value_tokens = _tokens(str(fact.get("property_value", "")))
        if value_tokens:
            value_tokens_by_property.setdefault(property_name, set()).update(value_tokens)
    return [
        property_name
        for property_name, value_tokens in value_tokens_by_property.items()
        if question_tokens & value_tokens
    ]


def _matching_fact(facts: List[Dict], property_name: str, question_tokens: set) -> Optional[Dict]:
    """The fact whose value words all appear in the question (latest first)."""
    candidates = [
        fact for fact in facts if str(fact.get("property_name", "")) == property_name
    ]
    candidates.sort(key=lambda fact: str(fact.get("valid_from", "")), reverse=True)
    for fact in candidates:
        value_tokens = _tokens(str(fact.get("property_value", "")))
        if value_tokens and value_tokens.issubset(question_tokens):
            return fact
    return None


def _fact_valid_at(facts: List[Dict], property_name: str, at: Optional[datetime]) -> Optional[Dict]:
    """The fact for `property_name` that was in effect at instant `at`."""
    if at is None:
        return None
    candidates = []
    for fact in facts:
        if str(fact.get("property_name", "")) != property_name:
            continue
        valid_from = _as_datetime(fact.get("valid_from"))
        valid_to = _as_datetime(fact.get("valid_to"))
        if valid_from is None or valid_from > at:
            continue
        if valid_to is not None and valid_to <= at:
            continue
        candidates.append(fact)
    if not candidates:
        return None
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    return max(candidates, key=lambda fact: _as_datetime(fact.get("valid_from")) or epoch)


def _property_mention_score(property_name: str, question_tokens: set) -> int:
    """How directly the question points at a property.

    Direct property-name words count double (e.g. "email" naming work_email),
    alias hits count once (e.g. "work" hinting at workplace). The anchor
    property's own value words are excluded by the caller so they never inflate
    the target's score.
    """
    property_parts = {
        token for token in re.findall(r"[a-z0-9]+", property_name.lower())
        if len(token) > 1
    }
    alias_hits = {
        token for token, canonical in _PROPERTY_ALIASES.items()
        if canonical == property_name and token in question_tokens
    }
    return len(property_parts & question_tokens) * 2 + len(alias_hits)


def _detect_multihop(
    facts: List[Dict], question_tokens: set, explicit_target: Optional[str]
) -> Tuple[Optional[str], Optional[str], Optional[Dict]]:
    """Resolve (target_property, anchor_property, anchor_fact) from a multi-hop
    question such as "Which workplace was active when my trip was in October?".

    The anchor is the property whose value words appear in the question (e.g.
    'trip' -> 'October'); the target is the other property the question points
    at most directly (e.g. 'workplace', or 'work_email' for "work email").
    """
    mentioned = _mentioned_properties(facts, question_tokens)
    value_matched = _value_matched_properties(facts, question_tokens)

    if explicit_target:
        target = explicit_target
        anchors = [property_name for property_name in value_matched if property_name != target]
        if not anchors:
            return None, None, None
        anchor_fact = _matching_fact(facts, anchors[0], question_tokens)
        return target, anchors[0], anchor_fact

    if len(value_matched) == 1 and len(mentioned) >= 2:
        anchor_property = value_matched[0]
        candidates = [
            property_name for property_name in mentioned if property_name != anchor_property
        ]
        if candidates:
            scored = [
                (_property_mention_score(property_name, question_tokens), property_name)
                for property_name in candidates
            ]
            scored.sort(reverse=True)
            # Only treat it as multi-hop if the question actually points at the
            # target (score > 0); otherwise fall through to single-fact lookup.
            if scored[0][0] > 0:
                anchor_fact = _matching_fact(facts, anchor_property, question_tokens)
                return scored[0][1], anchor_property, anchor_fact
    return None, None, None


def _conflict_response(active: List[Dict], property_name: str) -> MemoryQueryResponse:
    """Two or more active facts claim different values for the same property.

    EchoTrace treats this as insufficient agreement to answer and abstains,
    reporting every conflicting claim instead of guessing at one.
    """
    active_sorted = sorted(
        active, key=lambda fact: str(fact.get("valid_from", "")), reverse=True
    )
    return MemoryQueryResponse(
        status="CONFLICT",
        property_name=property_name,
        evidence=[_citation(fact) for fact in active_sorted],
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

    as_of = _parse_as_of(request.as_of) or _parse_as_of_from_question(request.question)
    if as_of is not None:
        # Temporal query: answer with whatever was true at that instant.
        ranked = []
        for fact in facts:
            property_name = str(fact.get("property_name", ""))
            label_tokens = _tokens(str(fact.get("label", "")))
            property_tokens = {property_name}
            score = len(question_tokens & property_tokens) * 3 + len(question_tokens & label_tokens)
            if score:
                ranked.append((score, fact))
        if not ranked:
            return MemoryQueryResponse(status="INSUFFICIENT_EVIDENCE")
        ranked.sort(key=lambda item: (item[0], str(item[1].get("valid_from", ""))), reverse=True)
        property_name = ranked[0][1]["property_name"]
        fact = _fact_valid_at(facts, property_name, as_of)
        if fact is None:
            return MemoryQueryResponse(status="INSUFFICIENT_EVIDENCE", property_name=property_name)
        history = sorted(
            (f for f in facts if f.get("property_name") == property_name and f["id"] != fact["id"]),
            key=lambda f: str(f.get("valid_from", "")),
            reverse=True,
        )
        return MemoryQueryResponse(
            status="ANSWERED",
            answer=str(fact["property_value"]),
            property_name=property_name,
            evidence=[_citation(fact)],
            history=[_citation(f) for f in history] if request.include_history else [],
            as_of=str(as_of),
        )

    target, anchor_property, anchor_fact = _detect_multihop(facts, question_tokens, request.target_property)
    if target and anchor_fact is not None:
        anchor_time = _as_datetime(anchor_fact.get("valid_from"))
        target_fact = _fact_valid_at(facts, target, anchor_time)
        if target_fact is not None:
            history = sorted(
                (f for f in facts if f.get("property_name") == target and f["id"] != target_fact["id"]),
                key=lambda f: str(f.get("valid_from", "")),
                reverse=True,
            )
            return MemoryQueryResponse(
                status="ANSWERED",
                answer=str(target_fact["property_value"]),
                property_name=target,
                evidence=[_citation(target_fact)],
                history=[_citation(f) for f in history] if request.include_history else [],
                anchor_property_name=anchor_property,
                anchor_value=str(anchor_fact.get("property_value", "")),
                as_of=str(anchor_fact.get("valid_from", "")),
            )
        return MemoryQueryResponse(status="INSUFFICIENT_EVIDENCE", property_name=target)

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
    if len(active) > 1 and len({
        str(fact.get("property_value", "")).casefold() for fact in active
    }) > 1:
        return _conflict_response(active, property_name)
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
