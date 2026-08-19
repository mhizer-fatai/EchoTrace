"""
Deterministic benchmark for the EchoTrace memory layer.

Ingests a 35-session corpus (optionally padded toward ~115k tokens) into a
dedicated benchmark user's memory on real HydraDB, then asks a scored set of
questions covering:

  * current-truth retrieval after supersession
  * historical (superseded) recall
  * cross-session synthesis
  * abstention (INSUFFICIENT_EVIDENCE) on never-recorded facts

Run it directly:  python -m scripts.benchmark
"""

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from backend.app.engine.memory import _memory_scope, ingest_conversation, query_memory
from backend.app.engine.studio import STORY_SCENARIO_STEPS
from backend.app.graph.client import graph_client
from backend.app.models.schemas import (
    ConversationMessage,
    IngestConversationRequest,
    MemoryQueryRequest,
)

BENCH_USER_ID = "bench-user"
DEFAULT_TARGET_TOKENS = 115_000
# Rough heuristic: ~4 chars per token for English prose.
_CHARS_PER_TOKEN = 4.0

# Filler sentences that intentionally carry no extractable facts. They pad the
# corpus toward the 115k-token scale target without changing any answer.
_FILLER_POOL = [
    "The morning standup covered the release timeline and the incident from Tuesday.",
    "We scheduled a follow-up design review for next week after the product feedback.",
    "The build pipeline ran clean on the latest commit before lunch.",
    "I reviewed the onboarding notes and left comments on the migration plan.",
    "The client asked for a status update on the rollout schedule.",
    "Everyone agreed to move the sync earlier so it does not overlap with the walkthrough.",
    "The telemetry dashboard showed steady traffic overnight.",
    "We rotated the staging credentials after the security audit.",
    "The team split the backlog into two sprints to keep the scope manageable.",
    "I committed the parser changes and opened a pull request for review.",
    "The office network was upgraded over the weekend to support the new floor layout.",
    "Documentation was updated to reflect the latest API contracts.",
    "We tested the retry path with a simulated timeout and it recovered cleanly.",
    "The report covers the quarter, the projections, and the open risks.",
    "I archived the old meeting notes and moved the agenda to the shared drive.",
    "The deployment ran a canary first and then rolled out to all regions.",
    "We triaged the open tickets and reprioritized the two most urgent items.",
    "The metrics were exported at the end of each hour for the compliance check.",
    "I updated the playbook with the runbook steps from last week's drill.",
    "The data sync completed before the morning snapshot was taken.",
]

# Each filler message bundles several filler sentences so the corpus reaches the
# 115k-token target with a tractable number of messages/nodes.
_FILLER_SENTENCES_PER_MESSAGE = 12


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def _corpus_tokens(messages: List[str]) -> int:
    return sum(estimate_tokens(m) for m in messages)


def build_benchmark_corpus(
    session_count: int = 35,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    seed: int = 20260816,
) -> List[Tuple[str, List[str]]]:
    """Return [(session_id, [message, ...]), ...] padded toward target_tokens.

    The first session_count prompts come from the 35-session studio story so the
    benchmark and the interactive UI exercise the same facts and supersessions.
    The remaining messages are deterministic filler that carries no facts.
    """
    rng = random.Random(seed)
    story_prompts = [step["prompt"] for step in STORY_SCENARIO_STEPS]

    sessions: List[Tuple[str, List[str]]] = []
    for index in range(1, session_count + 1):
        session_id = f"session_{index:02d}"
        if index <= len(story_prompts):
            messages: List[str] = [story_prompts[index - 1]]
        else:
            messages = []
        sessions.append((session_id, messages))

    current_tokens = sum(_corpus_tokens(messages) for _, messages in sessions)
    filler_index = 0
    while current_tokens < target_tokens:
        for _, messages in sessions:
            if current_tokens >= target_tokens:
                break
            bundle = " ".join(
                _FILLER_POOL[(filler_index + offset) % len(_FILLER_POOL)]
                for offset in range(_FILLER_SENTENCES_PER_MESSAGE)
            )
            filler_index += 1
            messages.append(bundle)
            current_tokens += estimate_tokens(bundle)
    return sessions


def _statement(messages: List[str], session_index: int) -> List[ConversationMessage]:
    base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc) + timedelta(days=session_index)
    return [
        ConversationMessage(role="user", content=content, timestamp=base + timedelta(minutes=index))
        for index, content in enumerate(messages)
    ]


# (question, expected_answer, {status, history_contains})
BENCH_QUESTIONS: List[Tuple[str, str, Dict[str, Any]]] = [
    ("When is my trip?", "November", {"history_contains": ["June", "October", "December", "February"]}),
    ("What month was my trip before November?", "February", {"as_of_history": True}),
    ("Where do I work?", "Nimbus Systems", {"history_contains": ["Acme Corp", "Globex", "Vertex Labs"]}),
    ("What is my work email?", "sarah@acme.com", {"history_contains": ["sarah@globex.io", "sarah@vertexlabs.ai"]}),
    ("Where do I live?", "Austin", {}),
    ("What seat do I prefer?", "window seats", {"history_contains": ["aisle seats"]}),
    ("What is my favorite color?", "teal", {}),
    ("What is my phone number?", "512-555-0199", {}),
    ("What is my passport number?", "470012345", {}),
    ("Where did I go to university?", "ABSTAIN", {"status": "INSUFFICIENT_EVIDENCE"}),
    ("What is my pet's name?", "ABSTAIN", {"status": "INSUFFICIENT_EVIDENCE"}),
    ("What is my mother's maiden name?", "ABSTAIN", {"status": "INSUFFICIENT_EVIDENCE"}),
    ("What is my next performance review date?", "ABSTAIN", {"status": "INSUFFICIENT_EVIDENCE"}),
    # Multi-hop: synthesize across two properties by walking the timeline.
    ("Which workplace was active when my trip was in July?", "Vertex Labs", {}),
    ("Which workplace was active when my trip was in February?", "Acme Corp", {}),
    ("What was my work email when my trip was in July?", "sarah@vertexlabs.ai", {}),
    # Temporal: what was true as of a specific instant.
    ("What was my trip as of 2026-01-10?", "October", {}),
    ("What was my trip as of 2026-01-15?", "December", {}),
]


def _normalize(value: str) -> str:
    return str(value).strip().lower()


def _score_question(question: str, expected: str, opts: Dict[str, Any], user_id: str) -> Tuple[bool, str]:
    result = query_memory(MemoryQueryRequest(
        user_id=user_id,
        question=question,
        include_history=True,
    ))

    if opts.get("status"):
        if result.status != opts["status"]:
            return False, f"expected {opts['status']}, got {result.status}"
        return True, "abstained correctly (INSUFFICIENT_EVIDENCE)"

    if expected == "ABSTAIN":
        if result.status == "INSUFFICIENT_EVIDENCE":
            return True, "abstained correctly (INSUFFICIENT_EVIDENCE)"
        return False, f"expected abstention, got {result.status}"

    if result.status != "ANSWERED":
        return False, f"expected answer, got {result.status}"

    if opts.get("as_of_history"):
        # The value immediately before the current one is the head of the
        # reverse-chronological history list.
        if not result.history:
            return False, "expected superseded history, got none"
        if _normalize(result.history[0].value) != _normalize(expected):
            return False, f"expected history head '{expected}', got '{result.history[0].value}'"
        return True, f"current '{result.answer}' with previous '{result.history[0].value}'"

    if _normalize(result.answer) != _normalize(expected):
        return False, f"expected '{expected}', got '{result.answer}'"

    history_values = {_normalize(h.value) for h in result.history}
    for need in opts.get("history_contains", []):
        if _normalize(need) not in history_values:
            return False, f"history missing '{need}' (got {sorted(history_values)})"

    cited = result.evidence[0].session_id if result.evidence else "?"
    return True, f"answered '{result.answer}' cited from {cited}"


def run_benchmark(
    session_count: int = 35,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    verbose: bool = True,
    user_id: str | None = None,
) -> Dict[str, Any]:
    # Use a fresh, uniquely-named scope per run. Clearing the previous run with
    # a single DETACH DELETE would exceed HydraDB's server-side query timeout
    # on the 600-node corpus, so each run writes to its own scope instead.
    run_user = user_id or f"{BENCH_USER_ID}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    scope = _memory_scope(run_user)

    corpus = build_benchmark_corpus(session_count, target_tokens)
    total_messages = sum(len(messages) for _, messages in corpus)
    total_tokens = sum(_corpus_tokens(messages) for _, messages in corpus)

    created = 0
    superseded = 0
    for session_index, (session_id, messages) in enumerate(corpus):
        result = ingest_conversation(IngestConversationRequest(
            user_id=run_user,
            session_id=session_id,
            messages=_statement(messages, session_index),
        ))
        created += len(result.memories_created)
        superseded += len(result.memories_superseded)

    detail = []
    correct = 0
    for question, expected, opts in BENCH_QUESTIONS:
        ok, reason = _score_question(question, expected, opts, run_user)
        if ok:
            correct += 1
        detail.append({
            "question": question,
            "expected": expected,
            "ok": ok,
            "reason": reason,
        })

    graph = graph_client.get_session_graph(scope)
    report = {
        "engine_mode": "HydraDB Bolt" if graph_client.connected_to_hydradb else "Internal Graph Engine",
        "scope": scope,
        "sessions": len(corpus),
        "messages": total_messages,
        "corpus_tokens": total_tokens,
        "facts_created": created,
        "facts_superseded": superseded,
        "questions_asked": len(BENCH_QUESTIONS),
        "questions_correct": correct,
        "score": round(correct / len(BENCH_QUESTIONS) * 100, 1),
        "node_count": len(graph.get("nodes", [])),
        "edge_count": len(graph.get("edges", [])),
        "detail": detail,
    }
    if verbose:
        print(_format_report(report))
    return report


def _format_report(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("ECHOTRACE MEMORY BENCHMARK")
    lines.append("=" * 46)
    lines.append(f"Engine mode      : {report['engine_mode']}")
    lines.append(f"Scope            : {report['scope']}")
    lines.append(f"Sessions         : {report['sessions']}")
    lines.append(f"Messages         : {report['messages']}")
    lines.append(f"Corpus size      : ~{report['corpus_tokens']:,} tokens")
    lines.append(f"Facts created    : {report['facts_created']}")
    lines.append(f"Facts superseded : {report['facts_superseded']}")
    lines.append(f"Graph            : {report['node_count']} nodes, {report['edge_count']} edges")
    lines.append("")
    lines.append(f"Questions asked  : {report['questions_asked']}")
    lines.append(f"Correct          : {report['questions_correct']}")
    lines.append(f"SCORE            : {report['score']}%")
    lines.append("")
    lines.append("DETAIL")
    lines.append("-" * 46)
    for item in report["detail"]:
        mark = "PASS" if item["ok"] else "FAIL"
        lines.append(f"[{mark}] {item['question']} -> {item['reason']}")
    return "\n".join(lines)
