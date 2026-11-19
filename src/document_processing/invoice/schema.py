"""Invoice field definitions and merging shared by extraction providers."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator


SCHEMA_VERSION = "invoice.v1"
SCHEMA = {
    "invoice_no": None,
    "date": None,
    "seller": None,
    "buyer": None,
    "items": [{
        "description": None,
        "quantity": None,
        "unit": None,
        "unit_price": None,
        "amount": None,
    }],
    "subtotal": None,
    "tax_amount": None,
    "total_amount": None,
}


class InvoiceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: StrictStr | None = None
    quantity: StrictStr | None = None
    unit: StrictStr | None = None
    unit_price: StrictStr | None = None
    amount: StrictStr | None = None

    @field_validator("quantity", "unit_price", "amount", mode="before")
    @classmethod
    def numeric_values_to_text(cls, value: Any) -> Any:
        return _numeric_text(value)


class InvoiceFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_no: StrictStr | None = None
    date: StrictStr | None = None
    seller: StrictStr | None = None
    buyer: StrictStr | None = None
    items: list[InvoiceItem] = []
    subtotal: StrictStr | None = None
    tax_amount: StrictStr | None = None
    total_amount: StrictStr | None = None

    @field_validator("subtotal", "tax_amount", "total_amount", mode="before")
    @classmethod
    def numeric_values_to_text(cls, value: Any) -> Any:
        return _numeric_text(value)


def _numeric_text(value: Any) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str) and re.search(r"[+=×*]", value):
        return None
    return value


def merge_invoice_fields(
    parsed_jobs: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Merge ordered extraction results and report conflicting scalar values."""
    fields = InvoiceFields().model_dump(mode="json")
    conflicts: dict[str, list[str]] = {}
    scalar_fields = (
        "invoice_no", "date", "seller", "buyer", "subtotal", "tax_amount", "total_amount",
    )
    items: list[dict[str, Any]] = []
    owner_by_field = {
        "invoice_no": {"header", "document"}, "date": {"header", "document"},
        "seller": {"header", "document"}, "buyer": {"header", "document"},
        "subtotal": {"header", "document", "table"},
        "tax_amount": {"header", "document", "table"},
        "total_amount": {"header", "document", "table"},
    }
    for field in scalar_fields:
        candidates_by_kind = {
            kind: [
                str(result[field]).strip()
                for job, result in parsed_jobs
                if job["kind"] == kind and job["kind"] in owner_by_field[field]
                and result.get(field) is not None
                and str(result[field]).strip()
            ]
            for kind in ("header", "document", "table")
        }
        candidates = next(
            (values for values in candidates_by_kind.values() if values),
            [],
        )
        unique = list(dict.fromkeys(candidates))
        if len(unique) == 1:
            fields[field] = unique[0]
        elif len(unique) > 1:
            conflicts[field] = unique

    for job, result in parsed_jobs:
        if job["kind"] in {"table", "document"}:
            items.extend(item for item in result.get("items", []) if isinstance(item, dict))
    fields["items"] = items
    return InvoiceFields.model_validate(fields).model_dump(mode="json"), conflicts
