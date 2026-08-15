import logging
import time
from typing import Any, Dict

from backend.app.demo.scenarios import load_api_deprecation_scenario, load_contradiction_scenario
from backend.app.engine.invalidator import invalidate_fact
from backend.app.engine.healer import heal_subgraph
from backend.app.engine.blast_radius import calculate_blast_radius
from backend.app.engine.contradiction import generate_memory_health_report
from backend.app.graph.client import graph_client
from backend.app.models.schemas import InvalidateFactRequest

logger = logging.getLogger("echotrace.demo.sim")


class MultiAgentWorkflowSimulator:
    """
    Orchestrates and executes simulated multi-agent workflows for interactive demonstration.
    """

    def __init__(self, session_id: str = "live_simulation"):
        self.session_id = session_id

    def run_full_lifecycle(self) -> Dict[str, Any]:
        """
        Executes the entire lifecycle:
        Step 1: Baseline multi-agent graph creation (Healthy State)
        Step 2: Invalidation of an upstream fact ('PaymentsAPI v1' is deprecated -> 'v2')
        Step 3: Downstream blast-radius computation
        Step 4: Selective re-execution and auto-healing
        """
        # Step 1: Initialize baseline graph
        logger.info("Initializing baseline multi-agent graph...")
        initial_graph = load_api_deprecation_scenario(self.session_id)
        initial_health = generate_memory_health_report(self.session_id)

        # Step 2: Inject breaking invalidation
        logger.info("Injecting invalidation for fact_api_v1...")
        invalidation_req = InvalidateFactRequest(
            fact_id="fact_api_v1",
            reason="API v1 was deprecated on Aug 12; v2 with OAuth2 is required.",
            replacement_value="v2",
            evidence_uri="https://api.payments-corp.com/docs/changelog/2026",
            auto_heal=False,
        )
        invalidation_result = invalidate_fact(invalidation_req, self.session_id)

        # Step 3: Compute blast radius
        blast_radius = invalidation_result["blast_radius"]
        corrupted_health = generate_memory_health_report(self.session_id)

        # Step 4: Auto-heal
        logger.info("Executing selective auto-heal...")
        heal_result = heal_subgraph(
            self.session_id, remediation_order=blast_radius.get("remediation_order", [])
        )
        final_health = generate_memory_health_report(self.session_id)
        final_graph = graph_client.get_session_graph(self.session_id)

        return {
            "session_id": self.session_id,
            "initial_node_count": len(initial_graph["nodes"]),
            "affected_downstream_count": blast_radius["affected_nodes_count"],
            "re_executed_nodes": heal_result.re_executed_nodes,
            "final_health_score": final_health.health_score,
            "success": True,
        }
