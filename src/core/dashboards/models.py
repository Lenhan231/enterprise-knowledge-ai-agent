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
    question: str = Field(min_length=1, max_length=800)


class TileSpec(StrictModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,31}$')
    title: str = Field(min_length=1, max_length=120)
    kind: Literal['kpi', 'bar', 'line', 'donut', 'table', 'summary']
    query_id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,31}$')
    measures: list[str] = Field(default_factory=list, max_length=4)
    dimension: str | None = Field(default=None, max_length=128)
    span: int = Field(default=1, ge=1, le=2)


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


class DashboardDocument(DashboardPlan):
    id: str = Field(default_factory=lambda: uuid4().hex, pattern=r'^[a-f0-9]{32}$')
    description: str = Field(min_length=1, max_length=2000)
    scope: str = Field(default='', max_length=600)
    revision: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    data_updated_at: datetime = Field(default_factory=now)
    results: list[QueryResult] = Field(default_factory=list, max_length=4)
    status: Literal['complete', 'partial', 'failed'] = 'complete'


class BuildRequest(StrictModel):
    description: str = Field(min_length=1, max_length=2000)
    scope: str = Field(default='', max_length=600)


class DashboardEdit(StrictModel):
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    scope: str = Field(default='', max_length=600)
    tiles: list[TileSpec] = Field(min_length=1, max_length=8)


class RefreshRequest(StrictModel):
    revision: int = Field(ge=1)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    scope: str | None = Field(default=None, max_length=600)
