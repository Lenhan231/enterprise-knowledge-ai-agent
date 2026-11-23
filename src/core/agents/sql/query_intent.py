"""Validated business intent and server-owned clarification state for SQL requests."""
from __future__ import annotations

from datetime import date
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.agents.sql.metric_ontology import METRIC_ONTOLOGY


IntentSlot = Literal[
    'operation', 'metric', 'dimension', 'filters', 'time_scope', 'ranking',
    'source_scope', 'geographic_basis', 'geographic_coverage',
]
SourceProvenance = Literal['user', 'inferred', 'ontology_required']


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class IntentDateRange(_StrictModel):
    start: date
    end_exclusive: date

    @model_validator(mode='after')
    def validate_range(self):
        if self.end_exclusive <= self.start:
            raise ValueError('A time range must have a later exclusive end date.')
        return self


class IntentTimeScope(_StrictModel):
    mode: Literal['range', 'comparison', 'snapshot', 'latest', 'history', 'all', 'unknown']
    ranges: list[IntentDateRange] = Field(default_factory=list, max_length=4)

    @model_validator(mode='after')
    def validate_periods(self):
        if self.mode in {'range', 'comparison', 'snapshot'} and not self.ranges:
            raise ValueError('This time scope requires explicit date boundaries.')
        if self.mode not in {'range', 'comparison'} and len(self.ranges) > 1:
            raise ValueError('Only range comparisons may contain several periods.')
        return self


class IntentFilter(_StrictModel):
    field: str = Field(pattern=r'^(?:commerce\.)?[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){0,2}$')
    operator: Literal['eq', 'ne', 'lt', 'lte', 'gt', 'gte', 'in', 'is_null', 'is_not_null']
    value: str | int | float | bool | list[str | int | float | bool] | None = None
    provenance: Literal['user', 'inferred', 'ontology_required'] = 'user'


class IntentSource(_StrictModel):
    name: str = Field(pattern=r'^commerce\.[a-z][a-z0-9_]*$')
    provenance: SourceProvenance


class IntentRanking(_StrictModel):
    metric: str = Field(pattern=r'^[a-z][a-z0-9_]*$')
    direction: Literal['asc', 'desc']
    limit: int | None = Field(default=None, ge=1, le=200)

    @field_validator('metric')
    @classmethod
    def canonical_metric(cls, value):
        if value not in METRIC_ONTOLOGY:
            raise ValueError('Ranking metrics must use a canonical ontology ID.')
        return value


class QueryIntent(_StrictModel):
    original_question: str = Field(min_length=1, max_length=2000)
    operation: Literal['aggregate', 'list', 'compare', 'rank', 'trend', 'unknown']
    metrics: list[str] = Field(default_factory=list, max_length=16)
    unverified_metric_request: str | None = Field(default=None, min_length=1, max_length=300)
    dimensions: list[str] = Field(default_factory=list, max_length=10)
    filters: list[IntentFilter] = Field(default_factory=list, max_length=12)
    time_scope: IntentTimeScope | None = None
    time_grain: Literal['day', 'week', 'month', 'quarter', 'year'] | None = None
    requested_sources: list[IntentSource] = Field(default_factory=list, max_length=16)
    explicit_source_restriction: bool = False
    geographic_basis: Literal['order_destination', 'customer_profile', 'unknown'] | None = None
    geographic_coverage: Literal['all', 'filtered', 'unspecified'] | None = None
    ranking: IntentRanking | None = None
    unresolved_slots: list[IntentSlot] = Field(default_factory=list, max_length=12)

    @field_validator('metrics')
    @classmethod
    def canonical_metrics(cls, values):
        if any(value not in METRIC_ONTOLOGY for value in values):
            raise ValueError('Metrics must use canonical ontology IDs.')
        if len(set(values)) != len(values):
            raise ValueError('Metrics must be unique.')
        return values

    @field_validator('dimensions')
    @classmethod
    def unique_dimensions(cls, values):
        if len(set(values)) != len(values):
            raise ValueError('Dimensions must be unique.')
        if any(not value or not re.fullmatch(
                r'(?:commerce\.)?[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){0,2}', value)
               for value in values):
            raise ValueError('Dimensions must be identifiers, not expressions.')
        return values

    @model_validator(mode='after')
    def validate_intent(self):
        if len({source.name for source in self.requested_sources}) != len(self.requested_sources):
            raise ValueError('Requested sources must be unique.')
        if len(set(self.unresolved_slots)) != len(self.unresolved_slots):
            raise ValueError('Unresolved slots must be unique.')
        if self.ranking and self.metrics and self.ranking.metric not in self.metrics:
            raise ValueError('A ranking metric must be among the requested metrics.')
        if self.metrics and self.unverified_metric_request:
            raise ValueError('A request cannot mix canonical metrics with an unverified metric description.')
        return self


class ClarificationChoice(_StrictModel):
    number: int = Field(ge=1, le=3)
    label: str = Field(min_length=1, max_length=200)
    slot: IntentSlot
    value: str = Field(min_length=1, max_length=200)


class IntentInterpretation(_StrictModel):
    intent: QueryIntent
    clarification_question: str | None = Field(default=None, max_length=1000)
    allowed_choices: list[ClarificationChoice] = Field(default_factory=list, max_length=3)

    @model_validator(mode='after')
    def require_targeted_clarification(self):
        if self.intent.unresolved_slots and not self.clarification_question:
            raise ValueError('Unresolved intent requires one targeted clarification question.')
        return self


class MonthChange(_StrictModel):
    month: int = Field(ge=1, le=12)


class PendingClarification(_StrictModel):
    original_question: str = Field(min_length=1, max_length=2000)
    intent: QueryIntent
    unresolved_slots: list[IntentSlot] = Field(min_length=1, max_length=12)
    clarification_question: str = Field(min_length=1, max_length=1000)
    allowed_choices: list[ClarificationChoice] = Field(default_factory=list, max_length=3)

    @model_validator(mode='after')
    def keep_intent_and_pending_scope_aligned(self):
        if self.original_question != self.intent.original_question:
            raise ValueError('Pending state must retain the intent original question.')
        if set(self.unresolved_slots) != set(self.intent.unresolved_slots):
            raise ValueError('Pending slots must match the stored intent.')
        return self


class IntentPatch(_StrictModel):
    operation: Literal['aggregate', 'list', 'compare', 'rank', 'trend', 'unknown'] | None = None
    metrics: list[str] | None = Field(default=None, max_length=16)
    dimensions: list[str] | None = Field(default=None, max_length=10)
    filters: list[IntentFilter] | None = Field(default=None, max_length=12)
    time_scope: IntentTimeScope | None = None
    time_grain: Literal['day', 'week', 'month', 'quarter', 'year'] | None = None
    requested_sources: list[IntentSource] | None = Field(default=None, max_length=16)
    explicit_source_restriction: bool | None = None
    geographic_basis: Literal['order_destination', 'customer_profile', 'unknown'] | None = None
    geographic_coverage: Literal['all', 'filtered'] | None = None
    ranking: IntentRanking | None = None


class ClarificationResolution(_StrictModel):
    action: Literal['answer', 'clarify', 'new_request']
    updates: IntentPatch = Field(default_factory=IntentPatch)
    clarified_slots: list[IntentSlot] = Field(default_factory=list, max_length=12)
    explicitly_corrected_slots: list[IntentSlot] = Field(default_factory=list, max_length=12)
    clarification_question: str | None = Field(default=None, max_length=1000)
    allowed_choices: list[ClarificationChoice] = Field(default_factory=list, max_length=3)

    @model_validator(mode='after')
    def validate_resolution_shape(self):
        if self.action == 'clarify' and not self.clarification_question:
            raise ValueError('An unresolved reply requires a targeted clarification.')
        if self.action == 'new_request' and self.updates.model_fields_set:
            raise ValueError('A new request cannot mutate the pending intent.')
        return self
