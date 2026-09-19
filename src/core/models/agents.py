from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

class Intent(str, Enum):
    KNOWLEDGE = 'knowledge'
    ANALYTICS = "analytics"
    DASHBOARD = "dashboard"
    HYBRID = "hybrid"
    

class AgentRequest(BaseModel):
    question: str
    user_id: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class Evidence(BaseModel):
    source_type: str
    source: str
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class AgentResult(BaseModel):
    answer: str
    agent: str
    evidence: list[Evidence] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)