from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class NodeKind(str, Enum):
    AGENT = "AGENT"
    FACT = "FACT"
    EVIDENCE = "EVIDENCE"
    DECISION = "DECISION"
    TOOL_CALL = "TOOL_CALL"
    ARTIFACT = "ARTIFACT"
    MESSAGE = "MESSAGE"


class FactStatus(str, Enum):
    VALID = "VALID"
    INVALIDATED = "INVALIDATED"
    SUPERSEDED = "SUPERSEDED"
    STALE = "STALE"


class EdgeType(str, Enum):
    PRODUCED = "PRODUCED"
    DEPENDS_ON = "DEPENDS_ON"
    SUPERSEDED_BY = "SUPERSEDED_BY"
    TRIGGERED = "TRIGGERED"
    SUPPORTED_BY = "SUPPORTED_BY"
    INVALIDATED_BY = "INVALIDATED_BY"


class BaseGraphNode(BaseModel):
    id: str
    kind: NodeKind
    label: str
    session_id: str = "default"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_to: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FactNode(BaseGraphNode):
    kind: NodeKind = NodeKind.FACT
    entity: str
    property_name: str
    property_value: str
    status: FactStatus = FactStatus.VALID
    confidence: float = 1.0
    source_agent_id: Optional[str] = None


class DecisionNode(BaseGraphNode):
    kind: NodeKind = NodeKind.DECISION
    agent_id: str
    action_type: str
    rationale: str
    is_stale: bool = False
    executor_url: Optional[str] = None


class AgentNode(BaseGraphNode):
    kind: NodeKind = NodeKind.AGENT
    agent_name: str
    role: str
    framework: str = "custom"


class EvidenceNode(BaseGraphNode):
    kind: NodeKind = NodeKind.EVIDENCE
    source_uri: str
    content_snippet: str
    verified: bool = True


class MessageNode(BaseGraphNode):
    kind: NodeKind = NodeKind.MESSAGE
    user_id: str
    source_session_id: str
    message_index: int
    role: str
    content: str


class ArtifactNode(BaseGraphNode):
    kind: NodeKind = NodeKind.ARTIFACT
    artifact_name: str
    content: str
    artifact_type: str = "code"
    is_stale: bool = False
    executor_url: Optional[str] = None


class ToolCallNode(BaseGraphNode):
    kind: NodeKind = NodeKind.TOOL_CALL
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    output: Optional[str] = None


class GraphEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphSnapshot(BaseModel):
    session_id: str
    timestamp: datetime
    nodes: List[Dict[str, Any]]
    edges: List[GraphEdge]


class InvalidateFactRequest(BaseModel):
    fact_id: str
    reason: str
    replacement_value: Optional[str] = None
    evidence_uri: Optional[str] = None
    auto_heal: bool = False


class BlastRadiusReport(BaseModel):
    invalidated_fact_id: str
    invalidated_fact_text: str
    affected_nodes_count: int
    affected_decisions_count: int
    affected_artifacts_count: int
    affected_nodes: List[Dict[str, Any]]
    contamination_paths: List[List[str]]
    remediation_order: List[str]


class ContradictionItem(BaseModel):
    entity: str
    property_name: str
    fact_a_id: str
    fact_a_value: str
    fact_a_agent: Optional[str]
    fact_b_id: str
    fact_b_value: str
    fact_b_agent: Optional[str]
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    severity: str = "HIGH"


class MemoryHealthReport(BaseModel):
    session_id: str
    total_facts: int
    valid_facts: int
    superseded_facts: int
    invalidated_facts: int
    total_decisions: int
    stale_decisions: int
    total_artifacts: int
    stale_artifacts: int
    evidence_coverage_pct: float
    active_contradictions: List[ContradictionItem]
    health_score: float


class IngestFactRequest(BaseModel):
    session_id: str = "default"
    entity: str
    property_name: str
    property_value: str
    agent_id: Optional[str] = None
    confidence: float = 1.0
    evidence_source: Optional[str] = None
    evidence_snippet: Optional[str] = None


class IngestAgentRequest(BaseModel):
    session_id: str = "default"
    agent_id: str
    name: str
    role: str
    framework: str = "custom"


class IngestDecisionRequest(BaseModel):
    session_id: str = "default"
    agent_id: str
    action_type: str
    rationale: str
    depends_on_node_ids: List[str] = Field(default_factory=list)
    executor_url: str


class IngestArtifactRequest(BaseModel):
    session_id: str = "default"
    artifact_name: str
    content: str
    artifact_type: str = "code"
    depends_on_node_ids: List[str] = Field(default_factory=list)
    executor_url: str


class ConversationMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[datetime] = None


class MemoryClaim(BaseModel):
    property_name: str
    property_value: str
    message_index: int
    confidence: float = 1.0


class IngestConversationRequest(BaseModel):
    user_id: str
    session_id: str
    messages: List[ConversationMessage]
    memories: List[MemoryClaim] = Field(default_factory=list)


class IngestConversationResponse(BaseModel):
    user_id: str
    session_id: str
    messages_ingested: int
    memories_created: List[str]
    memories_superseded: List[str]


class StudioChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = Field(default=None, max_length=100)


class MemoryQueryRequest(BaseModel):
    user_id: str
    question: str
    include_history: bool = True
    # Optional structured hints for multi-hop / temporal queries. When left
    # unset, query_memory derives them from the question text itself.
    as_of: Optional[str] = None  # ISO datetime for "what was true as of <time>"
    target_property: Optional[str] = None  # multi-hop: property to look up


class MemoryCitation(BaseModel):
    fact_id: str
    session_id: str
    message_index: int
    quote: str
    value: str
    status: str
    recorded_at: str


class MemoryQueryResponse(BaseModel):
    status: str
    answer: Optional[str] = None
    property_name: Optional[str] = None
    evidence: List[MemoryCitation] = Field(default_factory=list)
    history: List[MemoryCitation] = Field(default_factory=list)
    # Multi-hop / temporal context (when present, the answer was synthesized by
    # walking the timeline rather than reading a single fact).
    anchor_property_name: Optional[str] = None
    anchor_value: Optional[str] = None
    as_of: Optional[str] = None


class ExecutorResponse(BaseModel):
    success: bool
    rationale: Optional[str] = None
    content: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AutoHealResponse(BaseModel):
    success: bool
    session_id: str
    re_executed_nodes: List[str]
    updated_artifacts: List[Dict[str, Any]]
    message: str
