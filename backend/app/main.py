from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.config import settings
from backend.app.engine.blast_radius import calculate_blast_radius
from backend.app.engine.contradiction import generate_memory_health_report
from backend.app.engine.demo import ingest_demo_message, replay_scale_story, reset_demo_story, seed_memory_story
from backend.app.engine.healer import heal_subgraph
from backend.app.engine.invalidator import invalidate_fact
from backend.app.engine.memory import ingest_conversation, query_memory
from backend.app.engine.watchdog import store_watchdog
from backend.app.graph.client import graph_client
from backend.app.models.schemas import (
    AutoHealResponse,
    AgentNode,
    BlastRadiusReport,
    FactNode,
    DecisionNode,
    ArtifactNode,
    EdgeType,
    GraphEdge,
    IngestAgentRequest,
    IngestArtifactRequest,
    IngestDecisionRequest,
    IngestFactRequest,
    InvalidateFactRequest,
    IngestConversationRequest,
    IngestConversationResponse,
    DemoChatRequest,
    MemoryQueryRequest,
    MemoryQueryResponse,
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
    if not store_watchdog.is_alive():
        store_watchdog.start()


# API Endpoints

@app.get("/api/health")
def get_health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "hydradb_connected": graph_client.connected_to_hydradb,
        "engine_mode": "HydraDB Bolt" if graph_client.connected_to_hydradb else "Internal Graph Engine",
        "hydradb_degraded": graph_client.store_degraded,
        "hydradb_degraded_reason": graph_client.degraded_reason,
        "store_last_probe": store_watchdog.last_probe_at,
        "store_last_recovery": store_watchdog.last_recovery_at,
        "store_recovery_count": store_watchdog.recovery_count,
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


@app.post("/api/memory/conversations", response_model=IngestConversationResponse)
def post_ingest_conversation(request: IngestConversationRequest) -> IngestConversationResponse:
    try:
        return ingest_conversation(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/memory/query", response_model=MemoryQueryResponse)
def post_query_memory(request: MemoryQueryRequest) -> MemoryQueryResponse:
    return query_memory(request)


@app.post("/api/demo/memory-story")
def post_seed_memory_story() -> Dict[str, Any]:
    return seed_memory_story()


@app.post("/api/demo/chat")
def post_demo_chat(request: DemoChatRequest) -> Dict[str, Any]:
    try:
        return ingest_demo_message(request.content, session_id=request.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/demo/replay")
def post_replay_demo() -> Dict[str, Any]:
    return replay_scale_story()


@app.post("/api/demo/reset")
def post_reset_demo() -> Dict[str, Any]:
    return reset_demo_story()


# SDK Ingestion Endpoints

@app.post("/api/ingest/agent")
def post_ingest_agent(req: IngestAgentRequest) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    graph_client.add_node(AgentNode(
        id=req.agent_id,
        label=req.name,
        agent_name=req.name,
        role=req.role,
        framework=req.framework,
        session_id=req.session_id,
        created_at=now,
        valid_from=now,
    ))
    return {"status": "registered", "agent_id": req.agent_id}


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

    if req.evidence_source:
        from backend.app.models.schemas import EvidenceNode
        evidence_id = f"ev_{uuid.uuid4().hex[:8]}"
        graph_client.add_node(EvidenceNode(
            id=evidence_id,
            label=f"Evidence: {req.evidence_source}",
            source_uri=req.evidence_source,
            content_snippet=req.evidence_snippet or "",
            session_id=req.session_id,
            created_at=now,
            valid_from=now,
        ))
        graph_client.add_edge(GraphEdge(
            id=f"edge_ev_{fact_id}_{evidence_id}",
            source_id=fact_id,
            target_id=evidence_id,
            edge_type=EdgeType.SUPPORTED_BY,
            created_at=now,
        ))

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
        executor_url=req.executor_url,
    )
    graph_client.add_node(decision)

    graph_client.add_edge(GraphEdge(
        id=f"edge_ag_dec_{req.agent_id}_{dec_id}",
        source_id=req.agent_id,
        target_id=dec_id,
        edge_type=EdgeType.PRODUCED,
        created_at=now,
    ))

    for dependency_id in req.depends_on_node_ids:
        graph_client.add_edge(GraphEdge(
            id=f"edge_dep_{dec_id}_{dependency_id}",
            source_id=dec_id,
            target_id=dependency_id,
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
        executor_url=req.executor_url,
    )
    graph_client.add_node(art)

    for dependency_id in req.depends_on_node_ids:
        graph_client.add_edge(GraphEdge(
            id=f"edge_art_dep_{art_id}_{dependency_id}",
            source_id=art_id,
            target_id=dependency_id,
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
