# EchoTrace

EchoTrace is a cross-session memory, provenance, and recovery service for AI agents. It retrieves the current answer from conversation history, cites the source session and message, preserves facts that were later overwritten, and abstains when no evidence exists. When memory drives agent work, EchoTrace also identifies affected decisions and artifacts and calls their registered executors in dependency order.

Built for **Hack Hydra Track 03: Memory and Context Retrieval**.

## Problem

AI agents lose context across conversations and can continue acting on facts after those facts change. Similarity search may find related text, but it does not reliably identify the current value, explain which session supports it, preserve what was superseded, or show which decisions and outputs depend on it.

EchoTrace turns conversation history into temporal, source-backed memory. It returns the current answer with evidence, keeps older values as history, abstains when evidence is missing, and traces changed memory into affected agent work.

## Why HydraDB

HydraDB is the durable source of truth for EchoTrace's memory graph. It stores messages, facts, supersession links, decisions, artifacts, and their relationships, then supports the graph reads and reverse dependency traversal used for retrieval and blast-radius analysis. Without HydraDB, EchoTrace would lose durable cross-session provenance and the relationship structure needed to explain what changed and what that change affects.

## Tech Stack

- HydraDB with OpenCypher over Bolt for durable graph storage and traversal
- FastAPI, Pydantic, and Uvicorn for the backend API
- Python SDK with Requests for workflow instrumentation and memory ingestion
- NetworkX for the isolated development fallback and local dependency ordering
- HTML, CSS, Tailwind CSS, and JavaScript Canvas for the dashboard and graph explorer
- Docker Compose for the reproducible local deployment

## Capabilities

- Durable graph storage in HydraDB over Bolt/OpenCypher
- Cross-session conversation memory and evidence-backed retrieval
- Chronological supersession with current and historical values
- Explicit abstention when no supporting memory exists
- Explicit fact, evidence, decision, and artifact provenance
- Multi-hop blast-radius calculation
- Fact invalidation and temporal supersession
- Real decision and artifact re-execution through HTTP webhooks
- Failure-safe execution that leaves failed nodes stale
- Historical graph snapshots and contradiction reporting
- Python instrumentation SDK and operational dashboard

## Architecture

```text
Agent application -> EchoTrace SDK -> FastAPI -> HydraDB
                                         |
                                         +-> registered HTTP executors
```

HydraDB is authoritative whenever it is connected. The NetworkX store is an explicit development fallback and is not durable.

## Run With Docker

```bash
docker compose up --build
```

Prerequisite: Docker Desktop or Docker Engine with the Compose plugin. Compose creates the local HydraDB directories and development authentication token automatically.

Open `http://localhost:8000`. Click **Launch App** to load the built-in cross-session memory graph, or use the session field to load data ingested by a real agent application.
If port 8000 is occupied, set `ECHOTRACE_PUBLISHED_PORT` before starting Compose.

Compose follows HydraDB v0.1.1's single-node local-storage contract. Durable files are written under `hydradb-data/store`, disposable cache files under `hydradb-data/cache`, and readiness is checked through the admin endpoint on port `9090`.

EchoTrace maps its readable string node IDs to deterministic 63-bit HydraDB vertex IDs. The original IDs remain available as `echotrace_id`, while HydraDB's native integer IDs drive adjacency and traversal.

Relevant environment variables:

| Variable | Purpose | Default |
| --- | --- | --- |
| `HYDRADB_BOLT_URI` | HydraDB Bolt endpoint | `bolt://127.0.0.1:7687` |
| `HYDRADB_AUTH_TOKEN` | HydraDB authentication token | local development token |
| `USE_IN_MEMORY_FALLBACK` | Permit non-durable startup without HydraDB | `false` |
| `EXECUTOR_ALLOWED_HOSTS` | Comma-separated webhook host allowlist | empty |
| `EXECUTOR_TIMEOUT_SECONDS` | Per-node execution timeout | `30` |
| `EXECUTOR_BEARER_TOKEN` | Optional shared bearer credential | empty |

Set `USE_IN_MEMORY_FALLBACK=false` outside local development. At least one host must be present in `EXECUTOR_ALLOWED_HOSTS` before stale nodes can be executed.

HydraDB is required by default. Set `USE_IN_MEMORY_FALLBACK=true` only for local development without a running HydraDB instance.

## Instrument A Workflow

Install the SDK locally:

```bash
pip install -e ./sdk
```

```python
from echotrace import EchoTrace

tracer = EchoTrace(endpoint="http://localhost:8000", session_id="sprint_42")


@tracer.agent(name="Researcher", role="API Specialist")
def research_api():
    return tracer.log_fact(
        entity="PaymentsAPI",
        property_name="version",
        property_value="v2",
        confidence=0.98,
        evidence_source="https://docs.example.com/payments/v2",
    )


@tracer.agent(name="Planner", role="System Architect")
def plan_architecture(api_fact_id):
    return tracer.log_decision(
        action_type="GatewaySelection",
        rationale="Selected the active PaymentsAPI specification.",
        executor_url="https://agents.example.com/executors/planner",
        depends_on=[api_fact_id],
    )
```

Every decision and artifact requires an `executor_url`. The URL is stored as workflow metadata; executor credentials remain in the EchoTrace server environment.
The SDK's `depends_on` argument accepts fact, decision, or artifact node IDs, allowing arbitrary multi-stage dependency chains.

## Cross-Session Memory

Conversation messages can be ingested directly. Common first-person memory updates are extracted deterministically; applications can also provide structured memory claims for complex language.

```python
from echotrace import EchoTrace

memory = EchoTrace(endpoint="http://localhost:8000")

memory.ingest_conversation(
    user_id="user_42",
    session_id="session_04",
    messages=[{"role": "user", "content": "My trip is in June."}],
)
memory.ingest_conversation(
    user_id="user_42",
    session_id="session_18",
    messages=[{"role": "user", "content": "I moved my trip to October."}],
)

result = memory.query_memory("user_42", "When is my trip?")
```

The result answers `October`, cites `session_18`, and includes `June` as superseded history. A question without supporting evidence returns `INSUFFICIENT_EVIDENCE` with no generated answer.

## Executor Contract

EchoTrace sends this request to each stale node's executor:

```json
{
  "node": {"id": "decision_123", "kind": "DECISION"},
  "active_facts": [{"id": "fact_456", "status": "VALID"}],
  "completed_dependencies": []
}
```

A decision executor must return:

```json
{
  "success": true,
  "rationale": "New decision based on the current facts",
  "metadata": {"model": "provider/model-name"}
}
```

An artifact executor must return:

```json
{
  "success": true,
  "content": "new artifact content",
  "metadata": {"validation": "passed"}
}
```

Any network error, non-success HTTP status, malformed response, or `success: false` stops execution. The failed node and unprocessed downstream nodes remain stale.

## API

- `POST /api/ingest/agent`
- `POST /api/ingest/fact`
- `POST /api/ingest/decision`
- `POST /api/ingest/artifact`
- `POST /api/memory/conversations`
- `POST /api/memory/query`
- `POST /api/demo/memory-story`
- `POST /api/demo/chat`
- `POST /api/demo/replay`
- `POST /api/demo/reset`
- `POST /api/facts/invalidate?session_id=...`
- `POST /api/subgraph/heal?session_id=...`
- `GET /api/graph/{session_id}`
- `GET /api/blast-radius/{session_id}/{fact_id}`
- `GET /api/memory-health/{session_id}`
- `GET /api/health`

Interactive API documentation is available at `http://localhost:8000/docs`.

## Tests

```bash
python -m pytest tests/ -v
```

The 16-test suite covers cross-session retrieval, temporal supersession, abstention, source citations, the repeatable memory story, an idempotent 30-session replay through real ingestion, HydraDB edge mutations, temporal snapshots, contradiction detection, blast-radius isolation, webhook execution order, executor failures, and SDK agent registration.

## Demo For Reviewers

After starting Compose, open `http://localhost:8000` and click **Launch App**. The studio opens as an interactive chatbot against one fixed user, `demo-user`. Every chat message is a new source session committed to HydraDB through the real `ingest_conversation()` pipeline, and the graph grows live on the right as you talk:

- **Tell it something** — `My trip is in June.` → EchoTrace extracts a fact and draws a message→fact `SUPPORTED_BY` edge.
- **Change your mind** — `I moved my trip to October.` → the June fact is superseded (`SUPERSEDED_BY` edge) and the new fact becomes active.
- **Ask it** — `When is my trip?` → it answers from the current fact with its source citation and the superseded history, or returns `INSUFFICIENT_EVIDENCE` (abstention) when nothing is recorded.
- **Give it a task** — `Plan my trip itinerary.` → a live `Travel Planner` agent → decision → itinerary artifact chain appears, wired `DEPENDS_ON` to the *current* (superseding) fact, so the old fact is visibly not correct anymore.

Hardcoded assistant replies (no LLM) keep the demo deterministic, while every write goes through the real HydraDB pipeline. **New chat** starts a fresh thread as a new session (up to 30), **Replay 30 sessions** ingests a deterministic 30-session corpus through the same path (`scale_01`–`scale_30`, idempotent — existing sessions are skipped, not duplicated), and **Reset story** clears the demo memory.

The API surface for the interactive demo is `POST /api/demo/chat`, `POST /api/demo/replay`, and `POST /api/demo/reset`.

No model API key is required for the application, demo, memory query, or test suite.

## Live HydraDB Verification

The Docker deployment has been verified against `ghcr.io/hydra-db/hydradb:latest` (`v0.1.1`) with this sequence:

1. Start HydraDB and confirm `/readyz`.
2. Confirm EchoTrace reports `HydraDB Bolt` mode.
3. Ingest an agent, fact, decision, artifact, and dependency edges.
4. Read the complete session back through EchoTrace.
5. Restart only EchoTrace and confirm the graph persists.
6. Compute a two-hop reverse dependency blast radius in HydraDB.
7. Supersede the fact and persist stale downstream state.
8. Restart EchoTrace again and confirm the replacement fact and stale state persist.

## Third-Party Attribution

EchoTrace is original hackathon work built with these open-source projects and hosted frontend resources:

- [HydraDB](https://github.com/hydra-db/hydradb), AGPL-3.0, durable graph storage and OpenCypher/Bolt execution
- [FastAPI](https://github.com/fastapi/fastapi), MIT, HTTP API framework
- [Uvicorn](https://github.com/encode/uvicorn), BSD-3-Clause, ASGI server
- [Neo4j Python Driver](https://github.com/neo4j/neo4j-python-driver), Apache-2.0, Bolt client used to communicate with HydraDB
- [NetworkX](https://github.com/networkx/networkx), BSD-3-Clause, isolated development fallback and local ordering utilities
- [Pydantic](https://github.com/pydantic/pydantic), MIT, request and graph-model validation
- [Requests](https://github.com/psf/requests), Apache-2.0, SDK and executor HTTP calls
- [Tailwind CSS browser build](https://tailwindcss.com/), MIT, frontend utility styling loaded from the official CDN
- [Google Fonts and Material Symbols](https://fonts.google.com/), font and icon assets loaded from Google Fonts

LongMemEval and other benchmark datasets are not bundled, modified, or used to claim measured results in this repository.
