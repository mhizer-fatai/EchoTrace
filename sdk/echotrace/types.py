from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FactRecord(BaseModel):
    fact_id: str
    entity: str
    property_name: str
    property_value: str
    confidence: float = 1.0


class DecisionRecord(BaseModel):
    decision_id: str
    action_type: str
    rationale: str
    depends_on: List[str] = Field(default_factory=list)


class ArtifactRecord(BaseModel):
    artifact_id: str
    name: str
    content: str
