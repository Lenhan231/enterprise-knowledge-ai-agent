"""Centralized LLM instructions; preserve rendered wording and whitespace."""


FINANCIAL_EXTRACTION_PROMPT = """Extract explicitly reported financial metrics from one page of a public company report.
Company: {company}
Report year: {document_year}
PDF page: {page_number}

Return only a JSON object with exactly this shape:
{{"metrics":[{{"metric_name":"total_consolidated_revenue|net_revenue|profit_before_tax|profit_after_tax|total_assets","metric_value":"verbatim numeric token","unit":"reported unit","fiscal_year":2024,"source_quote":"verbatim supporting text from this page"}}]}}

Rules: extract at most one value for each of the five allowed metrics. When a report year is provided, extract only the value for that fiscal year; ignore comparison years even if the page shows them. Use an empty metrics array only when the requested year or metric is not explicitly supported on this page. Do not calculate, convert units, infer missing values, or use knowledge outside the page. For a parser table, copy the exact source_quote row from the serialized table rows below; do not rebuild or reorder cells. For narrative text, copy an exact contiguous substring from the page text. The fiscal_year must be explicitly shown on this page and must match the report year when provided. Do not return markdown or additional keys.

Parser-detected table data (preserve exact cell strings):
{tables}

Page content:
{text}"""
