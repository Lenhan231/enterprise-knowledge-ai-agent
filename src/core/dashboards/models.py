from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def now():
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)


class QuerySpec(StrictModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,31}$')
    question: str = Field(min_length=1, max_length=2000)


class TileSpec(StrictModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,31}$')
    title: str = Field(min_length=1, max_length=120)
    kind: Literal['kpi', 'bar', 'line', 'donut', 'table', 'summary']
    query_id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,31}$')
    measures: list[str] = Field(default_factory=list, max_length=4)
    dimension: str | None = Field(default=None, max_length=128)
    span: int = Field(default=1, ge=1, le=2)


class DashboardOutput(StrictModel):
    query: int = Field(strict=True, ge=0, le=1)
    kind: Literal['kpi', 'bar', 'line', 'donut', 'table', 'summary']
    dimension: str | None = Field(default=None, max_length=128)
    measures: list[str] = Field(default_factory=list, max_length=4)
    group_by: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode='after')
    def check_fields(self):
        if any(not name or len(name) > 128 for name in [*self.measures, *self.group_by]):
            raise ValueError('Output fields must be bounded returned column names')
        if len(set(self.measures)) != len(self.measures) or len(set(self.group_by)) != len(self.group_by):
            raise ValueError('Output fields must be unique')
        return self


class DashboardPlan(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    queries: list[QuerySpec] = Field(min_length=1, max_length=4)
    tiles: list[TileSpec] = Field(min_length=1, max_length=8)

    @model_validator(mode='after')
    def check_references(self):
        ids = {query.id for query in self.queries}
        if len(ids) != len(self.queries) or len({tile.id for tile in self.tiles}) != len(self.tiles):
            raise ValueError('Query and tile identifiers must be unique')
        if any(tile.query_id not in ids for tile in self.tiles):
            raise ValueError('Every tile must reference a planned query')
        if len({query.question for query in self.queries}) != len(self.queries):
            raise ValueError('Reuse a dataset instead of duplicating its query')
        return self


class QueryResult(StrictModel):
    id: str
    question: str
    status: Literal['complete', 'empty', 'failed', 'clarification_required']
    payload: dict[str, Any] = Field(default_factory=dict)
    message: str = ''


class ClarificationTurn(StrictModel):
    question: str = Field(min_length=1, max_length=1200)
    reply: str = Field(min_length=1, max_length=2000)


class DashboardDocument(DashboardPlan):
    id: str = Field(default_factory=lambda: uuid4().hex, pattern=r'^[a-f0-9]{32}$')
    description: str = Field(min_length=1, max_length=2000)
    scope: str = Field(default='', max_length=600)
    clarifications: list[ClarificationTurn] = Field(default_factory=list, max_length=3)
    revision: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    data_updated_at: datetime = Field(default_factory=now)
    results: list[QueryResult] = Field(default_factory=list, max_length=4)
    tile_status: dict[str, dict[str, str]] = Field(default_factory=dict)
    status: Literal['complete', 'partial', 'failed'] = 'complete'


class BuildRequest(StrictModel):
    description: str = Field(min_length=1, max_length=2000)
    scope: str = Field(default='', max_length=600)
    conversation_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


class DashboardEdit(StrictModel):
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    scope: str = Field(default='', max_length=600)
    tiles: list[TileSpec] = Field(min_length=1, max_length=8)


class RefreshRequest(StrictModel):
    revision: int = Field(ge=1)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    scope: str | None = Field(default=None, max_length=600)


class PendingDashboard(StrictModel):
    description: str = Field(min_length=1, max_length=2000)
    scope: str = Field(default='', max_length=600)
    question: str = Field(default='', max_length=1200)
    clarifications: list[ClarificationTurn] = Field(default_factory=list, max_length=3)
    operation: Literal['create', 'rebuild', 'refresh', 'edit'] = 'create'
    target_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    revision: int | None = Field(default=None, ge=1)
    edit: DashboardEdit | None = None
    presentation_tile_id: str | None = Field(default=None, pattern=r'^[a-z][a-z0-9_-]{0,31}$')
    presentation_choices: dict[str, Literal['line', 'bar', 'donut', 'table']] = Field(default_factory=dict, max_length=8)
    presentation_document: DashboardDocument | None = None
