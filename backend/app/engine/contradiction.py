from datetime import datetime, timezone
import logging
from typing import List

from backend.app.graph.client import graph_client
from backend.app.models.schemas import (
    ContradictionItem,
    FactStatus,
    MemoryHealthReport,
    NodeKind,
)

logger = logging.getLogger("echotrace.engine.contradiction")


def detect_contradictions(session_id: str = "default") -> List[ContradictionItem]:
    """
    Scans active VALID facts within a session to detect conflicting claims
    on identical entities and property names.
    """
    session_data = graph_client.get_session_graph(session_id)
    nodes = session_data.get("nodes", [])

    active_facts = [
        n
        for n in nodes
        if n.get("kind") in [NodeKind.FACT.value, NodeKind.FACT]
        and n.get("status") == FactStatus.VALID.value
    ]

    contradictions: List[ContradictionItem] = []
    seen_pairs = set()

    for i in range(len(active_facts)):
        f1 = active_facts[i]
        for j in range(i + 1, len(active_facts)):
            f2 = active_facts[j]

            entity_match = (
                str(f1.get("entity", "")).strip().lower()
                == str(f2.get("entity", "")).strip().lower()
            )
            prop_match = (
                str(f1.get("property_name", "")).strip().lower()
                == str(f2.get("property_name", "")).strip().lower()
            )
            val_different = (
                str(f1.get("property_value", "")).strip().lower()
                != str(f2.get("property_value", "")).strip().lower()
            )

            if entity_match and prop_match and val_different:
                pair_key = tuple(sorted([f1["id"], f2["id"]]))
                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    contradictions.append(
                        ContradictionItem(
                            entity=f1.get("entity", "Unknown"),
                            property_name=f1.get("property_name", "attribute"),
                            fact_a_id=f1["id"],
                            fact_a_value=f1.get("property_value", ""),
                            fact_a_agent=f1.get("source_agent_id"),
                            fact_b_id=f2["id"],
                            fact_b_value=f2.get("property_value", ""),
                            fact_b_agent=f2.get("source_agent_id"),
                            detected_at=datetime.now(timezone.utc),
                            severity="HIGH",
                        )
                    )

    return contradictions


def generate_memory_health_report(session_id: str = "default") -> MemoryHealthReport:
    """
    Computes a comprehensive audit report of the agent system's memory and decision state.
    """
    session_data = graph_client.get_session_graph(session_id)
    nodes = session_data.get("nodes", [])
    edges = session_data.get("edges", [])

    total_facts = 0
    valid_facts = 0
    superseded_facts = 0
    invalidated_facts = 0

    total_decisions = 0
    stale_decisions = 0

    total_artifacts = 0
    stale_artifacts = 0

    facts_with_evidence = set()

    for node in nodes:
        kind = node.get("kind")
        if kind in [NodeKind.FACT.value, NodeKind.FACT]:
            total_facts += 1
            status = node.get("status")
            if status == FactStatus.VALID.value:
                valid_facts += 1
            elif status == FactStatus.SUPERSEDED.value:
                superseded_facts += 1
            elif status == FactStatus.INVALIDATED.value:
                invalidated_facts += 1

        elif kind in [NodeKind.DECISION.value, NodeKind.DECISION]:
            total_decisions += 1
            if node.get("is_stale", False):
                stale_decisions += 1

        elif kind in [NodeKind.ARTIFACT.value, NodeKind.ARTIFACT]:
            total_artifacts += 1
            if node.get("is_stale", False):
                stale_artifacts += 1

    # Check evidence coverage
    for edge in edges:
        if edge.get("edge_type") == "SUPPORTED_BY":
            facts_with_evidence.add(edge.get("source_id"))

    evidence_coverage = (
        (len(facts_with_evidence) / total_facts * 100.0) if total_facts > 0 else 100.0
    )

    contradictions = detect_contradictions(session_id)

    # Compute aggregate health score (0.0 to 100.0)
    penalties = 0.0
    if total_decisions > 0:
        penalties += (stale_decisions / total_decisions) * 35.0
    if total_artifacts > 0:
        penalties += (stale_artifacts / total_artifacts) * 25.0
    penalties += len(contradictions) * 20.0
    if evidence_coverage < 80.0:
        penalties += (80.0 - evidence_coverage) * 0.25

    health_score = max(0.0, min(100.0, round(100.0 - penalties, 1)))

    return MemoryHealthReport(
        session_id=session_id,
        total_facts=total_facts,
        valid_facts=valid_facts,
        superseded_facts=superseded_facts,
        invalidated_facts=invalidated_facts,
        total_decisions=total_decisions,
        stale_decisions=stale_decisions,
        total_artifacts=total_artifacts,
        stale_artifacts=stale_artifacts,
        evidence_coverage_pct=round(evidence_coverage, 1),
        active_contradictions=contradictions,
        health_score=health_score,
    )
