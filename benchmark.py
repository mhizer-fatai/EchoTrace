"""
EchoTrace Quantitative Performance and ROI Benchmark Suite

Measures:
1. Multi-hop Graph Traversal Latency (HydraDB OpenCypher / DAG Engine)
2. Token Cost & Latency: Full Pipeline Restart vs Selective Topological Auto-Heal
3. Memory Health Audit & Contradiction Detection Throughput
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from backend.app.graph.client import InMemoryGraphStore
from backend.app.engine.blast_radius import calculate_blast_radius
from backend.app.engine.contradiction import generate_memory_health_report
from backend.app.engine.invalidator import invalidate_fact
from backend.app.engine.healer import heal_subgraph
from backend.app.models.schemas import (
    AgentNode,
    ArtifactNode,
    DecisionNode,
    EdgeType,
    FactNode,
    FactStatus,
    GraphEdge,
    InvalidateFactRequest,
)


def generate_synthetic_multiagent_dag(
    store: InMemoryGraphStore,
    session_id: str,
    depth: int = 10,
    fanout: int = 3,
) -> Dict[str, Any]:
    """
    Generates a realistic multi-tier agent decision DAG with branch dependencies.
    """
    now = datetime.now(timezone.utc)
    nodes_created = 0
    edges_created = 0

    # 1. Root Agent
    root_agent = AgentNode(
        id="bench_root_agent",
        label="Root Orchestrator",
        agent_name="BenchOrchestrator",
        role="System Coordinator",
        session_id=session_id,
        created_at=now,
        valid_from=now,
    )
    store.add_node(root_agent)
    nodes_created += 1

    # 2. Upstream Fact (The Root Premise)
    root_fact = FactNode(
        id="bench_root_fact",
        label="GlobalConfig: AuthStrategy = JWT_v1",
        entity="GlobalConfig",
        property_name="AuthStrategy",
        property_value="JWT_v1",
        status=FactStatus.VALID,
        source_agent_id="bench_root_agent",
        session_id=session_id,
        created_at=now,
        valid_from=now,
    )
    store.add_node(root_fact)
    nodes_created += 1

    store.add_edge(GraphEdge(
        id="bench_edge_ag_fact",
        source_id="bench_root_agent",
        target_id="bench_root_fact",
        edge_type=EdgeType.PRODUCED,
        created_at=now,
    ))
    edges_created += 1

    # 3. Independent Healthy Facts (Not affected by root fact)
    for i in range(5):
        h_fact = FactNode(
            id=f"bench_healthy_fact_{i}",
            label=f"ServiceConfig_{i}: Region = us-east-1",
            entity=f"ServiceConfig_{i}",
            property_name="Region",
            property_value="us-east-1",
            status=FactStatus.VALID,
            source_agent_id="bench_root_agent",
            session_id=session_id,
            created_at=now,
            valid_from=now,
        )
        store.add_node(h_fact)
        nodes_created += 1

    # 4. Multi-Tier Downstream Decisions
    # Contaminated branch: depends on bench_root_fact
    prev_contam_id = "bench_root_fact"
    for d in range(1, depth + 1):
        for f in range(fanout):
            node_id = f"bench_dec_contam_d{d}_f{f}"
            dec_node = DecisionNode(
                id=node_id,
                label=f"Decision Layer {d}.{f} (Auth Integration)",
                agent_id="bench_root_agent",
                action_type="ConfigureEndpoint",
                rationale=f"Relying on upstream premise layer {d-1}",
                session_id=session_id,
                created_at=now,
                valid_from=now,
            )
            store.add_node(dec_node)
            nodes_created += 1

            store.add_edge(GraphEdge(
                id=f"bench_edge_contam_d{d}_f{f}",
                source_id=node_id,
                target_id=prev_contam_id,
                edge_type=EdgeType.DEPENDS_ON,
                created_at=now,
            ))
            edges_created += 1

        prev_contam_id = f"bench_dec_contam_d{d}_f0"

    # Independent branch: depends on healthy facts
    for d in range(1, depth + 1):
        for f in range(fanout):
            node_id = f"bench_dec_healthy_d{d}_f{f}"
            dec_node = DecisionNode(
                id=node_id,
                label=f"Decision Layer {d}.{f} (Database Integration)",
                agent_id="bench_root_agent",
                action_type="ConfigureDB",
                rationale="Relying on healthy database config",
                session_id=session_id,
                created_at=now,
                valid_from=now,
            )
            store.add_node(dec_node)
            nodes_created += 1

            store.add_edge(GraphEdge(
                id=f"bench_edge_healthy_d{d}_f{f}",
                source_id=node_id,
                target_id="bench_healthy_fact_0",
                edge_type=EdgeType.DEPENDS_ON,
                created_at=now,
            ))
            edges_created += 1

    return {
        "nodes_created": nodes_created,
        "edges_created": edges_created,
        "root_fact_id": "bench_root_fact",
    }


def run_benchmark():
    session_id = "bench_session"
    from backend.app.graph.client import graph_client
    graph_client.clear_session(session_id)

    print("================================================================================")
    print("           ECHOTRACE MULTI-AGENT PERFORMANCE & ROI BENCHMARK                    ")
    print("================================================================================")

    # 1. Pipeline Generation
    depth = 8
    fanout = 3
    t_start = time.perf_counter()
    stats = generate_synthetic_multiagent_dag(graph_client, session_id, depth=depth, fanout=fanout)
    gen_time_ms = (time.perf_counter() - t_start) * 1000.0

    print(f"Topology Generated: {stats['nodes_created']} nodes, {stats['edges_created']} edges (Depth: {depth}, Fanout: {fanout})")
    print(f"Graph Construction Time: {gen_time_ms:.2f} ms")
    print("--------------------------------------------------------------------------------")

    # 2. Blast Radius Traversal Benchmark
    traversal_times = []
    for _ in range(50):
        t0 = time.perf_counter()
        report = calculate_blast_radius("bench_root_fact", session_id=session_id)
        traversal_times.append((time.perf_counter() - t0) * 1000.0)

    avg_traversal_ms = sum(traversal_times) / len(traversal_times)
    min_traversal_ms = min(traversal_times)
    affected_count = len(report.affected_nodes)

    print(f"Blast Radius Traversal Latency (50 iterations):")
    print(f"  • Average: {avg_traversal_ms:.3f} ms")
    print(f"  • Fastest: {min_traversal_ms:.3f} ms")
    print(f"  • Affected Nodes Found: {affected_count} / {stats['nodes_created']} total nodes")
    print("--------------------------------------------------------------------------------")

    # 3. Fact Invalidation Benchmark
    inv_req = InvalidateFactRequest(
        fact_id="bench_root_fact",
        reason="JWT_v1 deprecated due to security CVE-2026-9182",
        replacement_value="JWT_v2_ED25519",
        evidence_uri="https://security.auth.org/advisory/2026",
        auto_heal=False,
    )
    t0 = time.perf_counter()
    inv_res = invalidate_fact(inv_req, session_id=session_id)
    inv_time_ms = (time.perf_counter() - t0) * 1000.0

    print(f"Atomic Fact Invalidation & State Supersession:")
    print(f"  • Invalidation Execution Time: {inv_time_ms:.2f} ms")
    print(f"  • Superseded Fact Created: {inv_res['new_fact_id']}")
    print(f"  • Downstream Nodes Marked Stale: {len(inv_res['blast_radius']['affected_nodes'])}")
    print("--------------------------------------------------------------------------------")

    # 4. Topological Auto-Heal vs Full Pipeline Restart ROI Comparison
    # Estimating 1,200 tokens per node LLM generation cost
    avg_tokens_per_node = 1200
    avg_sec_per_node_execution = 0.85

    # Full Pipeline Restart:
    full_restart_nodes = stats['nodes_created'] - 6 # excludes agents and facts
    full_restart_tokens = full_restart_nodes * avg_tokens_per_node
    full_restart_time_sec = full_restart_nodes * avg_sec_per_node_execution

    # EchoTrace Selective Auto-Heal:
    t0 = time.perf_counter()
    heal_res = heal_subgraph(session_id)
    heal_engine_time_ms = (time.perf_counter() - t0) * 1000.0

    selective_healed_nodes = len(heal_res.re_executed_nodes)
    selective_tokens = selective_healed_nodes * avg_tokens_per_node
    selective_time_sec = (selective_healed_nodes * avg_sec_per_node_execution) + (heal_engine_time_ms / 1000.0)

    token_savings_pct = ((full_restart_tokens - selective_tokens) / full_restart_tokens) * 100.0
    time_savings_pct = ((full_restart_time_sec - selective_time_sec) / full_restart_time_sec) * 100.0
    speedup_multiplier = full_restart_time_sec / max(0.001, selective_time_sec)

    print("ROI COMPARISON: FULL PIPELINE RESTART vs. ECHOTRACE SELECTIVE AUTO-HEAL")
    print("+------------------------------+-------------------------+-------------------------+")
    print("| Metric                       | Full Pipeline Restart   | EchoTrace Auto-Heal     |")
    print("+------------------------------+-------------------------+-------------------------+")
    print(f"| Re-Executed Nodes            | {full_restart_nodes:>19} nodes | {selective_healed_nodes:>19} nodes |")
    print(f"| Estimated LLM Tokens         | {full_restart_tokens:>18,} tokens | {selective_tokens:>18,} tokens |")
    print(f"| Estimated Recovery Latency   | {full_restart_time_sec:>20.2f} s | {selective_time_sec:>20.2f} s |")
    print(f"| Graph Resolution Overhead    | {0.0:>21.2f} ms | {heal_engine_time_ms:>20.2f} ms |")
    print("+------------------------------+-------------------------+-------------------------+")
    print(f"SUMMARY GAINS: {token_savings_pct:.1f}% Token Cost Reduction | {speedup_multiplier:.1f}x Faster Pipeline Recovery")
    print("================================================================================\n")

    return {
        "token_savings_pct": token_savings_pct,
        "speedup_multiplier": speedup_multiplier,
        "avg_traversal_ms": avg_traversal_ms,
    }


if __name__ == "__main__":
    run_benchmark()
