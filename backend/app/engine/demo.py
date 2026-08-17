from datetime import datetime, timedelta, timezone
import re
from typing import Any, Dict, Optional

from backend.app.engine.memory import _extract_message_claims, ingest_conversation, query_memory
from backend.app.graph.client import graph_client
from backend.app.models.schemas import (
    AgentNode,
    ArtifactNode,
    DecisionNode,
    EdgeType,
    FactNode,
    FactStatus,
    GraphEdge,
    ConversationMessage,
    IngestConversationRequest,
    MemoryQueryRequest,
    MessageNode,
)


DEMO_SESSION_ID = "memory:demo-user"
DEMO_USER_ID = "demo-user"
DEMO_MAX_SESSIONS = 35
DEMO_NODE_IDS = {
    "demo_msg_june",
    "demo_fact_june",
    "demo_msg_october",
    "demo_fact_october",
    "demo_agent_planner",
    "demo_decision_itinerary",
    "demo_artifact_itinerary",
}

DEMO_SCENARIO_STEPS = [
    {"session_id": "session_01", "prompt": "My trip is in June.", "description": "Trip planned for June"},
    {"session_id": "session_02", "prompt": "I work at Acme Corp.", "description": "Workplace: Acme Corp"},
    {"session_id": "session_03", "prompt": "My work email is sarah@acme.com.", "description": "Email: sarah@acme.com"},
    {"session_id": "session_04", "prompt": "I live in Austin.", "description": "Location: Austin"},
    {"session_id": "session_05", "prompt": "I moved my trip to October.", "description": "Trip superseded -> October"},
    {"session_id": "session_06", "prompt": "Plan my trip itinerary.", "description": "Execute task using current memory (October)"},
    {"session_id": "session_07", "prompt": "When is my trip?", "description": "Query: When is my trip?"},
    {"session_id": "session_08", "prompt": "Where did I go to university?", "description": "Query: University (Abstain)"},
    {"session_id": "session_09", "prompt": "I prefer window seats.", "description": "Preference: window seats"},
    {"session_id": "session_10", "prompt": "I now work at Globex.", "description": "Workplace superseded -> Globex"},
    {"session_id": "session_11", "prompt": "My work email is sarah@globex.io.", "description": "Email superseded -> Globex"},
    {"session_id": "session_12", "prompt": "I moved my trip to December.", "description": "Trip superseded -> December"},
    {"session_id": "session_13", "prompt": "I prefer aisle seats.", "description": "Preference superseded -> aisle"},
    {"session_id": "session_14", "prompt": "Where do I work?", "description": "Query: Where do I work?"},
    {"session_id": "session_15", "prompt": "I now work at Vertex Labs.", "description": "Workplace superseded -> Vertex"},
    {"session_id": "session_16", "prompt": "My work email is sarah@vertexlabs.ai.", "description": "Email superseded -> Vertex"},
    {"session_id": "session_17", "prompt": "I moved my trip to March.", "description": "Trip superseded -> March"},
    {"session_id": "session_18", "prompt": "My favorite color is teal.", "description": "Favorite color: teal"},
    {"session_id": "session_19", "prompt": "My phone number is 512-555-0199.", "description": "Phone number: 512-555-0199"},
    {"session_id": "session_20", "prompt": "I moved my trip to July.", "description": "Trip superseded -> July"},
    {"session_id": "session_21", "prompt": "I prefer window seats.", "description": "Preference superseded -> window"},
    {"session_id": "session_22", "prompt": "When is my trip?", "description": "Query: When is my trip?"},
    {"session_id": "session_23", "prompt": "What is my work email?", "description": "Query: What is my work email?"},
    {"session_id": "session_24", "prompt": "I live in Austin.", "description": "Location repeat (Idempotent)"},
    {"session_id": "session_25", "prompt": "My passport number is 470012345.", "description": "Passport: 470012345"},
    {"session_id": "session_26", "prompt": "I moved my trip to September.", "description": "Trip superseded -> September"},
    {"session_id": "session_27", "prompt": "I now work at Acme Corp.", "description": "Workplace superseded -> Acme"},
    {"session_id": "session_28", "prompt": "My work email is sarah@acme.com.", "description": "Email superseded -> Acme"},
    {"session_id": "session_29", "prompt": "I moved my trip to February.", "description": "Trip superseded -> February"},
    {"session_id": "session_30", "prompt": "When is my trip?", "description": "Query: When is my trip?"},
    {"session_id": "session_31", "prompt": "My favorite color is teal.", "description": "Favorite color: teal"},
    {"session_id": "session_32", "prompt": "I moved my trip to November.", "description": "Trip superseded -> November"},
    {"session_id": "session_33", "prompt": "I now work at Nimbus Systems.", "description": "Workplace superseded -> Nimbus Systems"},
    {"session_id": "session_34", "prompt": "Where do I work?", "description": "Query: Where do I work?"},
    {"session_id": "session_35", "prompt": "Plan my trip itinerary.", "description": "Execute task using current memory (November)"},
]

DEMO_SCALE_SCRIPT = [item["prompt"] for item in DEMO_SCENARIO_STEPS]


def _fact_summary(fact_id: str) -> Dict[str, str]:
    node = graph_client.get_node(fact_id) or {}
    return {
        "id": fact_id,
        "property_name": str(node.get("property_name", "")),
        "property_value": str(node.get("property_value", "")),
        "label": str(node.get("label", fact_id)),
    }


def _next_live_session_id() -> str:
    graph = graph_client.get_session_graph(DEMO_SESSION_ID)
    numbers = []
    for node in graph.get("nodes", []):
        if node.get("kind") != "MESSAGE":
            continue
        match = re.fullmatch(r"session_(\d+)", str(node.get("source_session_id", "")))
        if not match:
            match = re.fullmatch(r"live_(\d+)", str(node.get("source_session_id", "")))
        if match:
            numbers.append(int(match.group(1)))
    return f"session_{max(numbers, default=0) + 1:02d}"


def _session_number(session_id: str) -> int:
    match = re.fullmatch(r"session_(\d+)", session_id)
    return int(match.group(1)) if match else 0


def _is_question(text: str) -> bool:
    clean = text.strip().lower()
    if clean.endswith("?"):
        return True
    first_word = clean.split()[0] if clean.split() else ""
    return first_word in {"when", "what", "where", "who", "why", "how", "which"}


_TASK_KEYWORDS = ("plan", "execute", "book", "prepare", "itinerary", "create a", "schedule", "organize", "organise", "arrange")


def _is_task(text: str) -> bool:
    clean = text.strip().lower()
    return any(keyword in clean for keyword in _TASK_KEYWORDS)


def _current_active_fact(property_name: str) -> Optional[Dict[str, Any]]:
    graph = graph_client.get_session_graph(DEMO_SESSION_ID)
    candidates = [
        node for node in graph.get("nodes", [])
        if node.get("kind") == "FACT"
        and node.get("property_name") == property_name
        and node.get("status") == FactStatus.VALID.value
        and node.get("entity") == DEMO_USER_ID
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda node: str(node.get("valid_from", "")))


def _execute_demo_task(content: str, source_session_id: str, occurred_at: datetime) -> Dict[str, Any]:
    clean = content.strip().lower()
    property_name = "trip" if "trip" in clean else ("workplace" if "work" in clean else "email" if "email" in clean else "trip")
    current_fact = _current_active_fact(property_name)
    if not current_fact:
        return {
            "executed": False,
            "assistant_reply": f"I can't execute that task yet — I have no current memory for `{property_name.replace('_', ' ')}`. Add it first and I'll use it.",
            "created_nodes": [],
            "current_fact": None,
        }

    task_slug = source_session_id.replace(":", "_").replace(" ", "_")
    agent_id = f"demo_agent_{task_slug}"
    decision_id = f"demo_decision_{task_slug}"
    artifact_id = f"demo_artifact_{task_slug}"

    agent = AgentNode(
        id=agent_id,
        label="Travel Planner",
        agent_name="Travel Planner",
        role="itinerary agent",
        session_id=DEMO_SESSION_ID,
        created_at=occurred_at,
        valid_from=occurred_at,
    )
    decision = DecisionNode(
        id=decision_id,
        label=f"Plan the {current_fact['property_value']} itinerary",
        agent_id=agent_id,
        action_type=f"Plan {property_name.replace('_', ' ')}",
        rationale=f"Latest supported {property_name.replace('_', ' ')} is {current_fact['property_value']}.",
        executor_url="http://host.docker.internal:8001/demo/decision",
        session_id=DEMO_SESSION_ID,
        created_at=occurred_at,
        valid_from=occurred_at,
    )
    artifact = ArtifactNode(
        id=artifact_id,
        label=f"{current_fact['property_value']} itinerary",
        artifact_name=f"{current_fact['property_value'].lower()}_itinerary.md",
        content=f"# {current_fact['property_value']} trip\n\nThe itinerary uses the current memory from {current_fact.get('metadata', {}).get('source_session_id', source_session_id)}.",
        artifact_type="document",
        executor_url="http://host.docker.internal:8001/demo/artifact",
        session_id=DEMO_SESSION_ID,
        created_at=occurred_at,
        valid_from=occurred_at,
    )

    graph_client.add_node(agent)
    graph_client.add_node(decision)
    graph_client.add_node(artifact)
    graph_client.add_edge(GraphEdge(
        id=f"edge_agent_dec_{agent_id}_{decision_id}",
        source_id=agent_id,
        target_id=decision_id,
        edge_type=EdgeType.PRODUCED,
        created_at=occurred_at,
    ))
    graph_client.add_edge(GraphEdge(
        id=f"edge_dec_mem_{decision_id}_{current_fact['id']}",
        source_id=decision_id,
        target_id=current_fact["id"],
        edge_type=EdgeType.DEPENDS_ON,
        created_at=occurred_at,
    ))
    graph_client.add_edge(GraphEdge(
        id=f"edge_art_dec_{artifact_id}_{decision_id}",
        source_id=artifact_id,
        target_id=decision_id,
        edge_type=EdgeType.DEPENDS_ON,
        created_at=occurred_at,
    ))

    return {
        "executed": True,
        "assistant_reply": (
            f"Executing {property_name.replace('_', ' ')} planning using your **current** memory: "
            f"**{current_fact['property_value']}** (from `{current_fact.get('metadata', {}).get('source_session_id', 'earlier session')}`).\n\n"
            f"🔄 Superseded values are ignored automatically.\n"
            f"⚡ HydraDB: {agent_id} -> {decision_id} -> {artifact_id}, all `DEPENDS_ON` your active fact."
        ),
        "created_nodes": [agent_id, decision_id, artifact_id],
        "current_fact": _fact_summary(current_fact["id"]),
    }


def ingest_demo_message(
    content: str,
    session_id: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    content = content.strip()
    if not content:
        raise ValueError("Message content cannot be empty.")
    source_session_id = session_id or _next_live_session_id()
    now = occurred_at or datetime.now(timezone.utc)

    existing = graph_client.get_session_graph(DEMO_SESSION_ID).get("nodes", [])
    if session_id is None and _session_number(source_session_id) > DEMO_MAX_SESSIONS:
        return {
            "session_id": source_session_id,
            "content": content,
            "assistant_reply": (
                f"You've reached the **{DEMO_MAX_SESSIONS}-session cap** for this demo memory. "
                f"Cross-session memory is fully populated — start a new chat thread on a fresh store to begin again."
            ),
            "is_query": False,
            "reached_cap": True,
            "skipped": True,
            "messages_ingested": 0,
            "extracted": [],
            "created": [],
            "superseded": [],
            "hydradb_connected": graph_client.connected_to_hydradb,
            "engine_mode": "HydraDB Bolt" if graph_client.connected_to_hydradb else "Internal Graph Engine",
            "node_count": len(existing),
            "edge_count": len(graph_client.get_session_graph(DEMO_SESSION_ID).get("edges", [])),
        }

    already_recorded = any(
        (node.get("source_session_id") or (node.get("metadata") or {}).get("source_session_id"))
        == source_session_id
        for node in existing
    )
    if already_recorded:
        return {
            "session_id": source_session_id,
            "content": content,
            "assistant_reply": f"Session `{source_session_id}` already exists in memory — skipped (idempotent replay).",
            "is_query": False,
            "skipped": True,
            "messages_ingested": 0,
            "extracted": [],
            "created": [],
            "superseded": [],
            "hydradb_connected": graph_client.connected_to_hydradb,
            "engine_mode": "HydraDB Bolt" if graph_client.connected_to_hydradb else "Internal Graph Engine",
            "node_count": len(existing),
            "edge_count": len(graph_client.get_session_graph(DEMO_SESSION_ID).get("edges", [])),
        }

    if _is_task(content):
        msg_id = f"msg_task_{int(now.timestamp())}_{source_session_id}"
        graph_client.add_node(MessageNode(
            id=msg_id,
            label=f"{source_session_id}: {content[:30]}",
            user_id=DEMO_USER_ID,
            source_session_id=source_session_id,
            message_index=0,
            role="user",
            content=content,
            session_id=DEMO_SESSION_ID,
            created_at=now,
            valid_from=now,
        ))
        task_result = _execute_demo_task(content, source_session_id, now)
        current_graph = graph_client.get_session_graph(DEMO_SESSION_ID)
        return {
            "session_id": source_session_id,
            "content": content,
            "assistant_reply": task_result["assistant_reply"],
            "is_query": False,
            "is_task": True,
            "task_executed": task_result["executed"],
            "created_nodes": task_result["created_nodes"],
            "current_fact": task_result["current_fact"],
            "skipped": False,
            "messages_ingested": 1,
            "extracted": [],
            "created": [],
            "superseded": [],
            "hydradb_connected": graph_client.connected_to_hydradb,
            "engine_mode": "HydraDB Bolt" if graph_client.connected_to_hydradb else "Internal Graph Engine",
            "node_count": len(current_graph.get("nodes", [])),
            "edge_count": len(current_graph.get("edges", [])),
        }

    if _is_question(content):
        # Record the question message in the graph
        msg_id = f"msg_query_{int(now.timestamp())}_{source_session_id}"
        graph_client.add_node(MessageNode(
            id=msg_id,
            label=f"{source_session_id}: {content[:30]}",
            user_id=DEMO_USER_ID,
            source_session_id=source_session_id,
            message_index=0,
            role="user",
            content=content,
            session_id=DEMO_SESSION_ID,
            created_at=now,
            valid_from=now,
        ))

        query_res = query_memory(MemoryQueryRequest(
            user_id=DEMO_USER_ID,
            question=content,
            include_history=True,
        ))

        if query_res.status == "ANSWERED":
            source_s = query_res.evidence[0].session_id if query_res.evidence else "earlier session"
            if query_res.anchor_property_name:
                reply = (
                    f"When your **{query_res.anchor_property_name.replace('_', ' ')}** was "
                    f"**{query_res.anchor_value}**, your **{query_res.property_name.replace('_', ' ')}** "
                    f"was **{query_res.answer}**.\n\n"
                    f"🔗 **Synthesized** by walking the timeline: `{query_res.anchor_property_name}` "
                    f"anchored the moment, then the active `{query_res.property_name}` was resolved.\n"
                    f"📌 **Cited Source:** `{source_s}`"
                )
            elif query_res.as_of:
                reply = (
                    f"As of **{query_res.as_of}**, your **{query_res.property_name.replace('_', ' ')}** "
                    f"was **{query_res.answer}**.\n\n"
                    f"🕰️ **Temporal snapshot** from the memory timeline.\n"
                    f"📌 **Cited Source:** `{source_s}`"
                )
            else:
                reply = f"Based on your cross-session memory, your **{query_res.property_name.replace('_', ' ')}** is **{query_res.answer}**.\n\n📌 **Cited Source:** `{source_s}`"
            if query_res.history:
                history_lines = "\n".join(f"- `{h.value}` (from `{h.session_id}`)" for h in query_res.history)
                reply += f"\n\n⏳ **Superseded History:**\n{history_lines}"
        else:
            reply = f"I don't have any recorded memory regarding '{content}'.\n\n🛡️ **Status:** `INSUFFICIENT_EVIDENCE`\nEchoTrace abstains from answering rather than hallucinating an unrecorded fact."

        current_graph = graph_client.get_session_graph(DEMO_SESSION_ID)
        return {
            "session_id": source_session_id,
            "content": content,
            "assistant_reply": reply,
            "is_query": True,
            "query_result": query_res.model_dump(),
            "skipped": False,
            "messages_ingested": 1,
            "extracted": [],
            "created": [],
            "superseded": [],
            "hydradb_connected": graph_client.connected_to_hydradb,
            "engine_mode": "HydraDB Bolt" if graph_client.connected_to_hydradb else "Internal Graph Engine",
            "node_count": len(current_graph.get("nodes", [])),
            "edge_count": len(current_graph.get("edges", [])),
        }

    # Statement ingestion path
    message = ConversationMessage(
        role="user",
        content=content,
        timestamp=now,
    )
    extracted = [
        {"property_name": name, "property_value": value}
        for name, value in _extract_message_claims(message)
    ]
    result = ingest_conversation(IngestConversationRequest(
        user_id=DEMO_USER_ID,
        session_id=source_session_id,
        messages=[message],
    ))

    created_facts = [_fact_summary(fid) for fid in result.memories_created]
    superseded_facts = [_fact_summary(fid) for fid in result.memories_superseded]

    if created_facts:
        new_fact = created_facts[0]
        if superseded_facts:
            old_fact = superseded_facts[0]
            reply = f"Updated your memory! **{new_fact['property_name'].replace('_', ' ')}** is now **{new_fact['property_value']}**.\n\n🔄 **Superseded Previous:** `{old_fact['property_value']}`\n⚡ **HydraDB:** Created `SUPERSEDED_BY` temporal edge"
        else:
            reply = f"Saved to cross-session memory! **{new_fact['property_name'].replace('_', ' ')}** is **{new_fact['property_value']}**.\n\n⚡ **HydraDB:** Stored with `SUPPORTED_BY` provenance edge"
    else:
        reply = "Noted your message in this session history."

    current_graph = graph_client.get_session_graph(DEMO_SESSION_ID)
    return {
        "session_id": source_session_id,
        "content": content,
        "assistant_reply": reply,
        "is_query": False,
        "skipped": False,
        "messages_ingested": result.messages_ingested,
        "extracted": extracted,
        "created": created_facts,
        "superseded": superseded_facts,
        "hydradb_connected": graph_client.connected_to_hydradb,
        "engine_mode": "HydraDB Bolt" if graph_client.connected_to_hydradb else "Internal Graph Engine",
        "node_count": len(current_graph.get("nodes", [])),
        "edge_count": len(current_graph.get("edges", [])),
    }


def reset_demo_story() -> Dict[str, Any]:
    graph_client.clear_session(DEMO_SESSION_ID)
    return {
        "status": "cleared",
        "session_id": DEMO_SESSION_ID,
        "user_id": DEMO_USER_ID,
        "hydradb_connected": graph_client.connected_to_hydradb,
        "engine_mode": "HydraDB Bolt" if graph_client.connected_to_hydradb else "Internal Graph Engine",
    }


def replay_scale_story() -> Dict[str, Any]:
    start = datetime(2026, 8, 16, 9, 0, tzinfo=timezone.utc)
    steps = [
        ingest_demo_message(
            content,
            session_id=f"scale_{index:02d}",
            occurred_at=start + timedelta(minutes=index),
        )
        for index, content in enumerate(DEMO_SCALE_SCRIPT, start=1)
    ]
    graph = graph_client.get_session_graph(DEMO_SESSION_ID)
    return {
        "user_id": DEMO_USER_ID,
        "session_id": DEMO_SESSION_ID,
        "hydradb_connected": graph_client.connected_to_hydradb,
        "engine_mode": "HydraDB Bolt" if graph_client.connected_to_hydradb else "Internal Graph Engine",
        "sessions_requested": len(DEMO_SCALE_SCRIPT),
        "sessions_ingested": sum(not step["skipped"] for step in steps),
        "sessions_skipped": sum(step["skipped"] for step in steps),
        "memories_created": sum(len(step["created"]) for step in steps),
        "memories_superseded": sum(len(step["superseded"]) for step in steps),
        "node_count": len(graph.get("nodes", [])),
        "edge_count": len(graph.get("edges", [])),
        "steps": steps,
    }


def _demo_response() -> Dict[str, Any]:
    answer = query_memory(MemoryQueryRequest(
        user_id="demo-user",
        question="When is my trip?",
    ))
    abstention = query_memory(MemoryQueryRequest(
        user_id="demo-user",
        question="Where did I go to university?",
    ))
    return {
        "session_id": DEMO_SESSION_ID,
        "question": "When is my trip?",
        "answer": answer.model_dump(),
        "unsupported_question_status": abstention.status,
    }


def seed_memory_story() -> Dict[str, Any]:
    existing = graph_client.get_session_graph(DEMO_SESSION_ID)
    existing_ids = {node["id"] for node in existing.get("nodes", [])}
    if DEMO_NODE_IDS.issubset(existing_ids) and len(existing.get("edges", [])) >= 6:
        return _demo_response()

    june_at = datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc)
    october_at = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
    decision_at = datetime(2026, 8, 15, 12, 5, tzinfo=timezone.utc)
    nodes = [
        MessageNode(
            id="demo_msg_june",
            label="Session 04: trip planned for June",
            user_id="demo-user",
            source_session_id="session_04",
            message_index=0,
            role="user",
            content="My trip is in June.",
            session_id=DEMO_SESSION_ID,
            created_at=june_at,
            valid_from=june_at,
        ),
        FactNode(
            id="demo_fact_june",
            label="Trip: June (superseded)",
            entity="demo-user",
            property_name="trip",
            property_value="June",
            status=FactStatus.SUPERSEDED,
            session_id=DEMO_SESSION_ID,
            created_at=june_at,
            valid_from=june_at,
            valid_to=october_at,
            metadata={
                "source_session_id": "session_04",
                "message_index": 0,
                "quote": "My trip is in June.",
            },
        ),
        MessageNode(
            id="demo_msg_october",
            label="Session 18: trip moved to October",
            user_id="demo-user",
            source_session_id="session_18",
            message_index=0,
            role="user",
            content="I moved my trip to October.",
            session_id=DEMO_SESSION_ID,
            created_at=october_at,
            valid_from=october_at,
        ),
        FactNode(
            id="demo_fact_october",
            label="Trip: October (current)",
            entity="demo-user",
            property_name="trip",
            property_value="October",
            status=FactStatus.VALID,
            session_id=DEMO_SESSION_ID,
            created_at=october_at,
            valid_from=october_at,
            metadata={
                "source_session_id": "session_18",
                "message_index": 0,
                "quote": "I moved my trip to October.",
            },
        ),
        AgentNode(
            id="demo_agent_planner",
            label="Travel Planner",
            agent_name="Travel Planner",
            role="itinerary agent",
            session_id=DEMO_SESSION_ID,
            created_at=decision_at,
            valid_from=decision_at,
        ),
        DecisionNode(
            id="demo_decision_itinerary",
            label="Plan the October itinerary",
            agent_id="demo_agent_planner",
            action_type="Plan October trip",
            rationale="The latest supported trip month is October.",
            executor_url="http://host.docker.internal:8001/demo/decision",
            session_id=DEMO_SESSION_ID,
            created_at=decision_at,
            valid_from=decision_at,
        ),
        ArtifactNode(
            id="demo_artifact_itinerary",
            label="October itinerary",
            artifact_name="october_itinerary.md",
            content="# October trip\n\nThe itinerary uses the current memory from session 18.",
            artifact_type="document",
            executor_url="http://host.docker.internal:8001/demo/artifact",
            session_id=DEMO_SESSION_ID,
            created_at=decision_at,
            valid_from=decision_at,
        ),
    ]
    for node in nodes:
        graph_client.add_node(node)

    edges = [
        GraphEdge(id="demo_edge_june_source", source_id="demo_fact_june", target_id="demo_msg_june", edge_type=EdgeType.SUPPORTED_BY, created_at=june_at),
        GraphEdge(id="demo_edge_october_source", source_id="demo_fact_october", target_id="demo_msg_october", edge_type=EdgeType.SUPPORTED_BY, created_at=october_at),
        GraphEdge(id="demo_edge_superseded", source_id="demo_fact_june", target_id="demo_fact_october", edge_type=EdgeType.SUPERSEDED_BY, created_at=october_at),
        GraphEdge(id="demo_edge_agent_decision", source_id="demo_agent_planner", target_id="demo_decision_itinerary", edge_type=EdgeType.PRODUCED, created_at=decision_at),
        GraphEdge(id="demo_edge_decision_memory", source_id="demo_decision_itinerary", target_id="demo_fact_october", edge_type=EdgeType.DEPENDS_ON, created_at=decision_at),
        GraphEdge(id="demo_edge_artifact_decision", source_id="demo_artifact_itinerary", target_id="demo_decision_itinerary", edge_type=EdgeType.DEPENDS_ON, created_at=decision_at),
    ]
    for edge in edges:
        graph_client.add_edge(edge)

    return _demo_response()
