from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def validate_chat_metadata(value: dict[str, Any]) -> dict[str, Any]:
    """Keep client options separate from server-owned orchestration state."""
    reserved = {'identity', 'user_id', 'permissions', 'roles', 'history', 'plan',
                'task_results', 'deadline', 'budget', 'precollected', 'resolved_question'}
    if len(value) > 20 or any(key.startswith('_') or key in reserved for key in value):
        raise ValueError('Metadata contains reserved fields or exceeds 20 fields')
    return value

class Intent(str, Enum):
    KNOWLEDGE = 'knowledge'
    ANALYTICS = "analytics"
    DASHBOARD = "dashboard"
    HYBRID = "hybrid"
    REPORT = "report"
    

class VerifiedIdentity(BaseModel):
    """Server-verified principal; never populate this model from a request body."""

    subject: str
    permissions: frozenset[str] = Field(default_factory=frozenset)
    document_roles: frozenset[str] = Field(default_factory=frozenset)


class AgentRequest(BaseModel):
    question: str
    user_id: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    identity: VerifiedIdentity | None = None

class Evidence(BaseModel):
    citation_id: str | None = None
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
