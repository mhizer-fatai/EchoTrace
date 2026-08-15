from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.config import settings
from backend.app.demo.multi_agent_sim import MultiAgentWorkflowSimulator
from backend.app.demo.scenarios import load_api_deprecation_scenario, load_contradiction_scenario
from backend.app.engine.blast_radius import calculate_blast_radius
from backend.app.engine.contradiction import generate_memory_health_report
from backend.app.engine.healer import heal_subgraph
from backend.app.engine.invalidator import invalidate_fact
from backend.app.graph.client import graph_client
from backend.app.models.schemas import (
    AutoHealResponse,
    BlastRadiusReport,
    FactNode,
    DecisionNode,
    ArtifactNode,
    EdgeType,
    GraphEdge,
    IngestArtifactRequest,
    IngestDecisionRequest,
    IngestFactRequest,
    InvalidateFactRequest,
    MemoryHealthReport,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("echotrace.main")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="EchoTrace — AI Agent Memory & Decision Provenance Engine powered by HydraDB",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    # Pre-populate default demonstration session
    load_api_deprecation_scenario("default")
    logger.info("Default demonstration graph loaded successfully.")


# API Endpoints

@app.get("/api/health")
def get_health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "hydradb_connected": graph_client.connected_to_hydradb,
        "engine_mode": "HydraDB Bolt" if graph_client.connected_to_hydradb else "Internal Graph Engine",
    }


@app.get("/api/graph/{session_id}")
def get_graph(
    session_id: str,
    snapshot_time: Optional[str] = Query(None, description="ISO timestamp for temporal historical query"),
) -> Dict[str, Any]:
    parsed_time = None
    if snapshot_time:
        try:
            parsed_time = datetime.fromisoformat(snapshot_time)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ISO timestamp format for snapshot_time.")

    return graph_client.get_session_graph(session_id, snapshot_time=parsed_time)


@app.get("/api/blast-radius/{session_id}/{fact_id}", response_model=BlastRadiusReport)
def get_blast_radius(session_id: str, fact_id: str):
    try:
        return calculate_blast_radius(fact_id, session_id=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/facts/invalidate")
def post_invalidate_fact(request: InvalidateFactRequest, session_id: str = "default") -> Dict[str, Any]:
    try:
        result = invalidate_fact(request, session_id=session_id)
        if request.auto_heal:
            remediation_order = result["blast_radius"].get("remediation_order", [])
            heal_result = heal_subgraph(session_id, remediation_order=remediation_order)
            result["auto_heal_result"] = heal_result.model_dump()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/subgraph/heal", response_model=AutoHealResponse)
def post_heal_subgraph(session_id: str = "default") -> AutoHealResponse:
    return heal_subgraph(session_id=session_id)


@app.get("/api/memory-health/{session_id}", response_model=MemoryHealthReport)
def get_memory_health(session_id: str):
    return generate_memory_health_report(session_id=session_id)


@app.post("/api/demo/load-scenario")
def post_load_scenario(
    scenario_type: str = Query("api_deprecation", enum=["api_deprecation", "contradiction", "empty"]),
    session_id: str = Query("default"),
) -> Dict[str, Any]:
    if scenario_type == "api_deprecation":
        return load_api_deprecation_scenario(session_id)
    elif scenario_type == "contradiction":
        return load_contradiction_scenario(session_id)
    elif scenario_type == "empty":
        graph_client.clear_session(session_id)
        return {"nodes": [], "edges": []}
    raise HTTPException(status_code=400, detail="Unknown scenario type.")


@app.post("/api/demo/run-sim")
def post_run_simulation(session_id: str = "live_simulation") -> Dict[str, Any]:
    sim = MultiAgentWorkflowSimulator(session_id=session_id)
    return sim.run_full_lifecycle()


# SDK Ingestion Endpoints

@app.post("/api/ingest/fact")
def post_ingest_fact(req: IngestFactRequest) -> Dict[str, Any]:
    import uuid
    fact_id = f"fact_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    fact = FactNode(
        id=fact_id,
        label=f"{req.entity}: {req.property_name}",
        entity=req.entity,
        property_name=req.property_name,
        property_value=req.property_value,
        source_agent_id=req.agent_id,
        confidence=req.confidence,
        session_id=req.session_id,
        created_at=now,
        valid_from=now,
    )
    graph_client.add_node(fact)

    if req.agent_id:
        graph_client.add_edge(GraphEdge(
            id=f"edge_ag_{req.agent_id}_{fact_id}",
            source_id=req.agent_id,
            target_id=fact_id,
            edge_type=EdgeType.PRODUCED,
            created_at=now,
        ))

    return {"status": "created", "fact_id": fact_id}


@app.post("/api/ingest/decision")
def post_ingest_decision(req: IngestDecisionRequest) -> Dict[str, Any]:
    import uuid
    dec_id = f"dec_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    decision = DecisionNode(
        id=dec_id,
        label=f"Decision: {req.action_type}",
        agent_id=req.agent_id,
        action_type=req.action_type,
        rationale=req.rationale,
        session_id=req.session_id,
        created_at=now,
        valid_from=now,
    )
    graph_client.add_node(decision)

    graph_client.add_edge(GraphEdge(
        id=f"edge_ag_dec_{req.agent_id}_{dec_id}",
        source_id=req.agent_id,
        target_id=dec_id,
        edge_type=EdgeType.PRODUCED,
        created_at=now,
    ))

    for fact_id in req.depends_on_fact_ids:
        graph_client.add_edge(GraphEdge(
            id=f"edge_dep_{dec_id}_{fact_id}",
            source_id=dec_id,
            target_id=fact_id,
            edge_type=EdgeType.DEPENDS_ON,
            created_at=now,
        ))

    return {"status": "created", "decision_id": dec_id}


@app.post("/api/ingest/artifact")
def post_ingest_artifact(req: IngestArtifactRequest) -> Dict[str, Any]:
    import uuid
    art_id = f"art_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    art = ArtifactNode(
        id=art_id,
        label=f"Artifact: {req.artifact_name}",
        artifact_name=req.artifact_name,
        content=req.content,
        artifact_type=req.artifact_type,
        session_id=req.session_id,
        created_at=now,
        valid_from=now,
    )
    graph_client.add_node(art)

    graph_client.add_edge(GraphEdge(
        id=f"edge_art_dec_{art_id}_{req.decision_id}",
        source_id=art_id,
        target_id=req.decision_id,
        edge_type=EdgeType.DEPENDS_ON,
        created_at=now,
    ))

    return {"status": "created", "artifact_id": art_id}


# Mount Frontend Static Directory
frontend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
if os.path.exists(frontend_path):
    css_path = os.path.join(frontend_path, "css")
    js_path = os.path.join(frontend_path, "js")
    if os.path.exists(css_path):
        app.mount("/css", StaticFiles(directory=css_path), name="css")
    if os.path.exists(js_path):
        app.mount("/js", StaticFiles(directory=js_path), name="js")
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(frontend_path, "index.html"))

