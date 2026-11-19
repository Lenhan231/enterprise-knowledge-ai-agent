"""Editable presentation over an unchanged, server-generated sales report."""
from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from core.dashboards.models import StrictModel, now
from core.reports.sales_performance import load_contract, validate_report, validate_monthly_decisions
from core.reports.sales_context import SalesContext, build_insights

SECTION_IDS = tuple(load_contract()['sections'])
WIDGET_IDS = tuple(w['id'] for w in load_contract()['dashboard']['widgets'])


class ReportPresentation(StrictModel):
    section_order: list[str] = Field(default_factory=lambda: list(SECTION_IDS), min_length=1, max_length=5)
    hidden_sections: list[str] = Field(default_factory=list, max_length=5)
    chart_types: dict[str, Literal['line', 'bar', 'kpi_row', 'table']] = Field(default_factory=lambda: {'line_breakdown': 'kpi_row'})
    text_edits: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode='after')
    def valid_layout(self):
        if len(set(self.section_order)) != len(self.section_order) or set(self.section_order) != set(SECTION_IDS):
            raise ValueError('Section order must contain each report section once')
        if len(set(self.hidden_sections)) != len(self.hidden_sections) or not set(self.hidden_sections) < set(SECTION_IDS):
            raise ValueError('Keep at least one report section')
        if not set(self.chart_types) <= set(WIDGET_IDS):
            raise ValueError('Unknown report widget')
        if not set(self.text_edits) <= set(SECTION_IDS) or any(len(v) > 6000 for v in self.text_edits.values()):
            raise ValueError('Invalid edited report text')
        return self


class ReportEdit(StrictModel):
    revision: int = Field(strict=True, ge=1)
    title: str = Field(min_length=1, max_length=160)
    presentation: ReportPresentation


class ReportDocument(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()), pattern=r'^[a-f0-9-]{36}$')
    revision: int = Field(default=1, strict=True, ge=1)
    title: str = Field(default='Sales Performance Report', min_length=1, max_length=160)
    updated_at: datetime = Field(default_factory=now)
    report: dict
    monthly_decisions: list[dict] = Field(default_factory=list)
    sales_context: SalesContext = Field(default_factory=SalesContext)
    insights: dict = Field(default_factory=dict)
    status: Literal['complete', 'partial'] = 'partial'
    presentation: ReportPresentation = Field(default_factory=ReportPresentation)

    @model_validator(mode='after')
    def valid_report(self):
        validate_report(self.report)
        validate_monthly_decisions(self.report, self.monthly_decisions)
        self.insights = build_insights(self.report, self.monthly_decisions, self.sales_context)
        if 'presentation' not in self.model_fields_set:
            from core.reports.presentation import default_chart_types
            self.presentation.chart_types = default_chart_types(self.report)
        return self
