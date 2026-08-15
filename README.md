# EchoTrace — AI Agent Memory & Decision Provenance Engine

**EchoTrace** is an infrastructure engine for AI agents that builds a temporal dependency graph of an agent system's memory, decisions, and generated artifacts using **HydraDB**.

Instead of storing unlinked flat text or vector embeddings, EchoTrace preserves the deterministic causal chain of how facts influence decisions and generate actions over time. When an upstream assumption breaks, EchoTrace computes the downstream blast radius in milliseconds and enables selective, targeted re-execution.

---

## The Problem

In multi-agent workflows (e.g. Research -> Planning -> Coding -> Testing), agents pass information and assumptions to one another:

```text
Research Agent ("API v1 is active")
       ↓
Planning Agent ("Design for API v1")
       ↓
Coding Agent (generates payments_client.py with v1)
       ↓
Testing Agent (generates test_payments.py for v1)
```

When an upstream premise is later invalidated (*"API v1 was deprecated two weeks ago"*), standard vector memory systems cannot determine:
1. Which agent introduced the assumption?
2. Which downstream decisions relied on it?
3. Which generated code files or database updates were contaminated?
4. What exact subset of the workflow needs to be re-run?

---

## The EchoTrace Solution

EchoTrace models agent workflows as a directed acyclic temporal graph in **HydraDB**:

```text
(:Agent) --[:PRODUCED]--> (:Fact {valid_from, valid_to, status})
                             |
                      [:DEPENDS_ON]
                             |
                             v
                        (:Decision) --[:TRIGGERED]--> (:Artifact)
```

### Core Capabilities

1. **Deterministic Decision Provenance:** Explicitly links agent decisions to the supporting facts and evidence sources that justified them.
2. **Cascade Invalidation & Blast Radius Analysis:** Automatically traverses the reverse dependency graph to identify all corrupted downstream decisions and artifacts when a belief changes.
3. **Selective Subgraph Auto-Healing:** Re-prompts and re-executes only the contaminated nodes in topological order, leaving healthy branches untouched.
4. **Time-Travel Memory State Reconstruction:** Reconstructs the exact state of what the agent system believed and what was active at any point in history.
5. **Memory Health & Contradiction Monitor:** Audits the graph for stale dependencies, evidence coverage, and conflicting beliefs held across different agents.

---

## Quick Start

### 1. Installation

```bash
git clone https://github.com/mhizer-fatai/EchoTrace.git
cd EchoTrace
pip install -r requirements.txt
```

### 2. Run EchoTrace Server & Dashboard

```bash
python run.py
```
Open your browser at **http://localhost:8000** to access the interactive Developer Dashboard.

---

## Connecting to HydraDB

EchoTrace connects to HydraDB using the **Neo4j Bolt 5.x protocol** (port `7687`) and OpenCypher.

To run with a live HydraDB container:

```bash
# Pull official HydraDB release
docker pull ghcr.io/hydra-db/hydradb:latest

# Start HydraDB node
docker run --rm \
  -p 7687:7687 -p 8443:8443 \
  -v "$PWD/hydradb-data:/data" \
  -e CLOUD_PROVIDER=local \
  -e LOCAL_PATH=/data/store \
  -e GRAPH_NAMESPACE=default \
  -e GRAPH_ID=default \
  -e GRAPH_ALLOW_PLAINTEXT=true \
  ghcr.io/hydra-db/hydradb:latest
```

EchoTrace automatically detects and connects to `bolt://127.0.0.1:7687`. If running standalone, EchoTrace automatically activates its internal in-memory graph engine with identical OpenCypher query semantics.

---

## Developer SDK Usage

Instrument your multi-agent system in 3 lines of code:

```python
from sdk.echotrace import EchoTrace

tracer = EchoTrace(endpoint="http://localhost:8000", session_id="sprint_42")

@tracer.agent(name="Researcher", role="API Specialist")
def research_api():
    fact_id = tracer.log_fact(
        entity="PaymentsAPI",
        property_name="version",
        property_value="v1",
        confidence=0.98,
        evidence_source="https://docs.payments.com/v1"
    )
    return fact_id

@tracer.agent(name="Planner", role="System Architect")
def plan_architecture(api_fact_id):
    decision_id = tracer.log_decision(
        action_type="GatewaySelection",
        rationale="Selected PaymentsAPI based on active v1 spec.",
        depends_on=[api_fact_id]
    )
    return decision_id
```

---

## Running the Test Suite

```bash
pytest tests/ -v
```

All unit tests verify:
* Multi-hop downstream blast radius calculation.
* Fact invalidation and supersession edges.
* Temporal historical snapshot queries.
* Memory health scoring and contradiction detection.
* SDK decorators and context tracking.

---

## Architecture Overview

```text
+-------------------------------------------------------------+
|                     EchoTrace Dashboard                     |
|  Interactive DAG Visualizer . Blast Radius . Time Travel    |
+------------------------------+------------------------------+
                               | REST / WebSocket
+------------------------------v------------------------------+
|                      FastAPI Backend                        |
|                                                             |
|  * Engine Invalidator & Blast Radius Calculator             |
|  * Contradiction & Memory Health Evaluator                  |
|  * Topological Subgraph Auto-Healer                         |
+------------------------------+------------------------------+
                               | OpenCypher / Bolt
+------------------------------v------------------------------+
|                         HydraDB                             |
|                                                             |
|  * Object-Store Durable Graph Storage                       |
|  * Snapshot-Consistent Temporal Traversal                   |
|  * Fast Multi-Hop GraphBLAS Sparse Path Matrix Evaluation   |
+-------------------------------------------------------------+
```
