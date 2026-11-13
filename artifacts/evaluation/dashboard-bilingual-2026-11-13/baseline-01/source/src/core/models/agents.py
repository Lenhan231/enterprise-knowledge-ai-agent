from enum import Enum
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class ChartSeries(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    name: str
    values: list[float | None] = Field(min_length=1, max_length=200)


class ChartSpec(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    type: Literal['line', 'bar', 'donut']
    title: str
    categories: list[str] = Field(min_length=1, max_length=200)
    series: list[ChartSeries] = Field(min_length=1, max_length=4)
    unit: str
    x_label: str
    y_label: str
    temporal: bool = False
    scope: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def check_series(self):
        if any(len(series.values) != len(self.categories) for series in self.series):
            raise ValueError('Chart series must align with every category')
        if self.type == 'donut':
            values = self.series[0].values
            if (len(self.series) != 1 or any(value is None or value < 0 for value in values)
                    or not math.isfinite(sum(values)) or sum(values) <= 0):
                raise ValueError('A donut needs one nonnegative series with a positive total')
        return self
