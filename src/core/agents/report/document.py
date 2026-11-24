"""Editable presentation over an unchanged, server-generated sales report."""
from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from core.agents.dashboard.models import StrictModel, now
from core.agents.report.sales_performance import load_contract, validate_report, validate_monthly_decisions
from core.agents.report.sales_context import SalesContext, build_insights
from core.agents.report.inventory_operations import InventoryContext, SECTION_TITLES as INVENTORY_SECTIONS
from core.agents.report.labels import COMBINED_REPORT, LABELS, uses_vietnamese_labels

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


class InventoryPresentation(StrictModel):
    section_order: list[str] = Field(default_factory=lambda: list(INVENTORY_SECTIONS))
    hidden_sections: list[str] = Field(default_factory=list)
    chart_types: dict[str, str] = Field(default_factory=dict)
    text_edits: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode='after')
    def immutable_layout(self):
        if self.section_order != list(INVENTORY_SECTIONS) or self.hidden_sections or self.chart_types or self.text_edits:
            raise ValueError('Inventory sections, widgets and evidence are immutable')
        return self


class ReportEdit(StrictModel):
    revision: int = Field(strict=True, ge=1)
    title: str = Field(min_length=1, max_length=160)
    presentation: ReportPresentation | InventoryPresentation


class ReportDocument(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()), pattern=r'^[a-f0-9-]{36}$')
    revision: int = Field(default=1, strict=True, ge=1)
    title: str = Field(default='Sales Performance Report', min_length=1, max_length=160)
    updated_at: datetime = Field(default_factory=now)
    report: dict
    monthly_decisions: list[dict] = Field(default_factory=list)
    sales_context: SalesContext = Field(default_factory=SalesContext)
    inventory_context: InventoryContext = Field(default_factory=InventoryContext)
    insights: dict = Field(default_factory=dict)
    status: Literal['complete', 'partial'] = 'partial'
    presentation: ReportPresentation | InventoryPresentation = Field(default_factory=ReportPresentation)

    def _inventory_insights(self, report):
        from core.agents.report.inventory_operations import validate_report as validate_inventory, policy_notes
        from core.agents.report.presentation import inventory_insights

        validate_inventory(report)
        context = self.inventory_context.model_dump(mode='json')
        report['data_quality']['limitations'] = [note for note in report['data_quality']['limitations']
            if not note.startswith(('Policy Evidence:', 'Policy source ['))] + policy_notes(context)
        return inventory_insights(report)

    @model_validator(mode='after')
    def valid_report(self):
        kind = self.report.get('report_type')
        if kind == 'inventory_operations':
            self.insights = self._inventory_insights(self.report)
            if 'title' not in self.model_fields_set:
                self.title = LABELS['inventory_operations'] if uses_vietnamese_labels(self.report) else 'Inventory & Operations Report'
            if self.monthly_decisions:
                raise ValueError('Inventory rules use a single selected snapshot')
            if 'presentation' not in self.model_fields_set:
                self.presentation = InventoryPresentation()
            if not isinstance(self.presentation, InventoryPresentation):
                raise ValueError('Inventory presentation must preserve the contract')
            return self
        if not isinstance(self.presentation, ReportPresentation):
            raise ValueError('Sales reports require a sales presentation')
        combined = kind == COMBINED_REPORT
        sales = self.report
        if combined:
            reports = self.report.get('reports')
            if (set(self.report) != {'report_type', 'reports'} or not isinstance(reports, dict)
                    or set(reports) != {'inventory_operations', 'sales_performance'}
                    or any(not isinstance(part, dict) or part.get('report_type') != key for key, part in reports.items())):
                raise ValueError('A combined report requires one inventory part and one sales part')
            sales, inventory = reports['sales_performance'], reports['inventory_operations']

        validate_report(sales)
        validate_monthly_decisions(sales, self.monthly_decisions)
        sales_insights = build_insights(sales, self.monthly_decisions, self.sales_context)
        if combined:
            inventory_insights = self._inventory_insights(inventory)
            if sales['request']['period'] != inventory['request']['period'] or uses_vietnamese_labels(sales) != uses_vietnamese_labels(inventory):
                raise ValueError('Combined report parts must share the period and language')
            self.insights = {'inventory_operations': inventory_insights, 'sales_performance': sales_insights}
        else:
            self.insights = sales_insights
        if 'title' not in self.model_fields_set:
            if uses_vietnamese_labels(sales):
                self.title = LABELS[kind]
            elif combined:
                self.title = 'Inventory and Sales Performance Report'
        if 'presentation' not in self.model_fields_set:
            from core.agents.report.presentation import default_chart_types
            self.presentation.chart_types = default_chart_types(sales)
        return self
