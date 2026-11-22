"""Replay frozen SQL and scripted drafts through unchanged pinned production code."""
import argparse
import asyncio
from collections import Counter
from copy import deepcopy
from datetime import date
from decimal import Decimal
from html import unescape
from io import BytesIO
import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import time
import traceback
import sys

from freeze import COMMIT, FOLLOWUP, ROOT, digest, git, source, source_root, write

sys.path.insert(0, str(source_root() / "src"))
from docx import Document
from fastapi import HTTPException
from core.agents.dashboard.agent import DashboardDocumentAgent
from core.agents.dashboard.models import DashboardDocument
from core.agents.dashboard.render import display_context, formatted, render_dashboard
from core.agents.dashboard import render
from core.agents.report.agent import ReportAgent
from core.agents.report.http import report_response
from core.agents.report.sales_performance import validate_report
from core.agents.sql.agent import AnalyticsPermissionDenied, SQLAnalyticsAgent
from core.models.agents import AgentRequest, Evidence, VerifiedIdentity


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def check(assertions, name, passed):
    assertions[name] = bool(passed)


def request(question, report_type=None, *, permissions=("analytics:read", "documents:read"),
            roles=("employee",), anonymous=False):
    return AgentRequest(question=question,
        identity=None if anonymous else VerifiedIdentity(subject="evaluation", permissions=set(permissions), document_roles=set(roles)),
        metadata={"report_type": report_type} if report_type else {})


def output(kind, measure=None, dimension=None, id="main"):
    return {"id": id, "kind": kind, "measures": [measure] if measure else [], "dimension": dimension}


def sql_payload(item):
    return {"query_status": "executed", "ok": True, "rows": deepcopy(item["rows"]),
            "sql": item["sql"], "parameters": item["parameters"], "metadata": {}}


def set_tiles(payload, *tiles):
    payload["metadata"]["dashboard_outputs"] = tiles


async def dashboard(case, evidence):
    item = evidence["sql"][case["evidence"]]
    name = case["scenario"]
    question, scope = item["question"], ""
    p = sql_payload(item) if item["supported"] else {
        "query_status": "unsupported", "ok": False, "rows": [],
        "answer": "Warehouse inventory and supplier lead time are unsupported."}
    if name in {"table", "scope_delivery", "scope_product", "empty"}:
        question += " Show a table."
        p.setdefault("metadata", {})
        set_tiles(p, output("table"))
    if name == "bar":
        question += " Show a bar chart."
    if name == "line":
        question += " Use a line chart."
    if name == "donut":
        question += " Show the top-five ranking as a donut chart."
    scopes = {
        "scope_delivery": "2025 only, delivered orders only",
        "scope_product": "between 2025-04-01 and 2025-06-30, delivered orders, grouped by product_id",
        "scope_category": "Category Apparel only, grouped by product_id",
        "stale_snapshot": "snapshot 2026-11-13",
    }
    scope = scopes.get(name, "")
    if scope:
        p["metadata"]["filters"] = [scope]
    if name == "changed_row":
        p["rows"][0]["revenue"] = "13299822.25"
    if name == "stale_snapshot":
        p["parameters"] = ["2026-10-31"]
    if name == "empty":
        p["rows"] = []
    if name == "failed_rows":
        p.update(query_status="rejected", rows=[{"stock_on_hand": 987654}], answer="Source query rejected.")
    if name == "invalid_field":
        set_tiles(p, output("bar", "undefined_metric", "product_id"))
    if name == "grouped_kpi":
        set_tiles(p, output("kpi", "units_sold"))
    if name == "kpi_table":
        set_tiles(p, output("kpi", "revenue"), output("table", id="table"))
    if name in {"kpi_chart_table", "inconsistent_kpi"}:
        second = deepcopy(p)
        if name == "kpi_chart_table":
            set_tiles(p, output("line", "revenue", "month"), output("table", id="table"))
            second["sql"] = "SELECT SUM(s.revenue) AS revenue FROM commerce.sales s LIMIT 1"
            second["rows"] = [{"revenue": "30"}]
        else:
            set_tiles(p, output("table"))
            second["rows"][0]["revenue"] = "13299999.25"
        set_tiles(second, output("kpi", "revenue"))
        response = {"datasets": [{"question": question, "payload": p},
                                 {"question": "Total revenue for the same scope", "payload": second}]}
    else:
        response = p
    sql = SimpleNamespace(run_payload=AsyncMock(return_value=response))
    document = await DashboardDocumentAgent(sql).build(request(question), question, scope)
    checks = {}
    check(checks, "schema", DashboardDocument.model_validate_json(document.model_dump_json()).id == document.id)
    rendered_charts = []
    original_chart = render.build_chart

    def capture(payload, prompt):
        chart = original_chart(payload, prompt)
        rendered_charts.append(chart)
        return chart

    with patch.object(render, "build_chart", side_effect=capture):
        html = render_dashboard(document)
    charts = [chart.model_dump(mode="json") for chart in rendered_charts]
    tiles = document.tile_status
    rows = document.results[0].payload.get("rows", [])
    series_checked = 0
    for chart in charts:
        for series in chart["series"]:
            field = series["name"].lower().replace(" ", "_")
            dimension = chart["x_label"].lower().replace(" ", "_")
            numeric_label = dimension in {"product_id", "customer_id"}
            labels = [Decimal(label) if numeric_label else label for label in chart["categories"]]
            lookup = {Decimal(str(row[dimension])) if numeric_label else str(row[dimension]): row[field]
                      for row in item["rows"] if dimension in row and field in row}
            check(checks, f"chart_values_{series_checked}", len(labels) == len(lookup) and set(labels) == set(lookup)
                  and [Decimal(str(x)) for x in series["values"]] == [Decimal(str(lookup[key])) for key in labels])
            series_checked += 1
    status = document.status
    detected = status != "complete"
    if name in {"empty", "unsupported", "failed_rows"}:
        expected = {"empty": "empty", "unsupported": "failed", "failed_rows": "failed"}[name]
        check(checks, "safe_result_status", document.results[0].status == expected)
        check(checks, "no_rendered_fake_value", '<p class="kpi">' not in html and "<svg" not in html and "987654" not in html)
        if name == "empty":
            check(checks, "empty_is_explicit", "not a zero value" in html
                  or "Không có dữ liệu phù hợp. Giá trị chưa xác định." in html)
        if name == "unsupported":
            check(checks, "unsupported_is_explicit", "unsupported" in html)
        detected = name == "failed_rows" and detected
    else:
        check(checks, "row_exact_match", rows == item["rows"])
        check(checks, "bound_parameter_fidelity", document.results[0].payload["parameters"] == item["parameters"])
        if charts:
            check(checks, "svg_and_series_present", "<svg" in html and series_checked > 0)
    if scope:
        child = sql.run_payload.await_args.args[0]
        check(checks, "scope_forwarded", f"Required dashboard date/filter scope: {scope}" in child.question and child.metadata["_dashboard_scope"] == scope)
        check(checks, "scope_retained", document.scope == scope and scope in document.results[0].question)
    if name in {"revenue", "kpi_table", "kpi_chart_table", "inconsistent_kpi"}:
        expected = Decimal("30") if name == "kpi_chart_table" else Decimal(str(item["rows"][0]["revenue"]))
        kpi_values = re.findall(r'<p class="kpi">(.*?)</p>', html)
        kpi_source = document.results[-1].payload
        observed = Decimal(str(kpi_source["rows"][0]["revenue"]))
        units, currency = display_context(kpi_source)
        rendered = formatted(expected, unit=units.get("revenue"), currency=currency)
        check(checks, "kpi_matches_oracle", observed == expected and [rendered] == kpi_values)
        if name == "kpi_table":
            check(checks, "table_matches_kpi", f">{rendered}</td>" in html)
        if name == "kpi_chart_table":
            check(checks, "chart_sums_to_kpi", bool(charts) and sum(Decimal(str(x)) for x in charts[0]["series"][0]["values"]) == observed)
    if name in {"table", "scope_delivery", "scope_product", "kpi_chart_table"}:
        bodies = re.findall(r"<tbody>(.*?)</tbody>", html.split("<footer>", 1)[0], re.S)
        cells = [re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
                 for row in re.findall(r"<tr>(.*?)</tr>", bodies[-1], re.S)] if bodies else []
        if name == "kpi_chart_table":
            cells = [row[-1:] for row in cells]
        expected = [[Decimal(str(row[key])) for key in (["revenue"] if name == "kpi_chart_table" else list(row))]
                    for row in item["rows"]]
        try:
            observed = [[Decimal(unescape(cell).replace(",", "").strip()) for cell in row] for row in cells]
        except ArithmeticError:
            observed = []
        check(checks, "table_numeric_exact_match", observed == expected)
    if case["expect"] == "accept" and name not in {"empty", "unsupported"}:
        check(checks, "complete", status == "complete")
    if case["expect"] == "reject":
        check(checks, "invalid_detected", detected)
    path = ROOT / "results" / "dashboard" / (case["id"] + ".html")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    raw = {"document": document.model_dump(mode="json"), "charts": charts,
           "forwarded_question": sql.run_payload.await_args.args[0].question, "source_response": response}
    semantic = {"question": question, "expectation": case["expect"], "candidate": {
        "charts": charts, "tiles": [tile.model_dump() for tile in document.tiles], "tile_status": tiles},
        "evidence": [{"id": case["evidence"], "rows": item["rows"], "sql": item.get("sql")}]}
    if FOLLOWUP and name == "kpi_chart_table":
        semantic["candidate"].update(rendered_table_revenue=observed, rendered_kpi=kpi_values)
    return checks, not detected, raw, semantic


def inventory_inputs(name, evidence):
    source = evidence["sql"]["P04"]
    stock = [{"snapshot_date": "2026-11-13", **row} for row in source["rows"]]
    question = "Inventory risk report: top 5 products by stock on hand at snapshot 2026-11-13."
    mapping = {"metrics": ["stock_on_hand"], "dimensions": ["product_id", "product_name"], "representation": "product",
               "time": {"mode": "snapshot", "start": "2026-11-13", "end": "2026-11-13"},
               "ranking": {"metric": "stock_on_hand", "direction": "desc", "limit": 5}}
    if name == "ratio_value":
        question = "Inventory risk report: stored product fill rate at snapshot 2026-11-13."
        mapping["metrics"] = ["stored_fill_rate"]
        mapping.pop("ranking")
        stock = [{"snapshot_date": "2026-11-13", "product_id": 11, "product_name": "fixture",
                  "stored_fill_rate": evidence["ratio"]["value"]}]
    plan = {"purpose": "Inventory observations", "tasks": [{"id": "stock", "question": question, "mapping": mapping}],
            "sections": [{"heading": "Inventory Overview", "tasks": ["stock"]}]}
    if name in {"unsupported", "partial_table", "partial_docx"}:
        question += " Also include supplier lead time."
        plan["unsupported_requirements"] = ["Supplier lead time is unavailable from the approved source."]
        if name == "unsupported":
            question = "Inventory risk report: show warehouse-level inventory and supplier lead time for 2026-11-13."
            plan = {"purpose": "Unsupported supplier lead time", "unsupported_requirements": plan["unsupported_requirements"]}
    if name in {"inventory_empty", "failed_delivery"}:
        stock = []
    if name == "wrong_snapshot":
        stock[0]["snapshot_date"] = "2026-10-31"
    if name == "missing_metric":
        stock[0].pop("stock_on_hand")
    return question, plan, stock


def policy_evidence(evidence, index):
    if "knowledge" in evidence:
        item = evidence["knowledge"]["cases"][index]
        return Evidence(citation_id=item["id"], source_type="document", source=item["passages"][0]["document"],
                        content=evidence["policy"][index], metadata={"document_id": "VSC-OPS-POL-001",
                            "knowledge_case": item["id"], "chunk_indices": [passage["chunk_index"] for passage in item["passages"]]})
    return Evidence(citation_id="POLICY", source_type="document", source=evidence["policy_source"],
                    content=evidence["policy"][index], metadata={"document_id": "VSC-OPS-POL-001"})


class Writer:
    def __init__(self, plan, scenario):
        self.plan = plan
        self.scenario = scenario
        self.responses = []

    async def generate(self, prompt):
        if "\nFacts: " not in prompt:
            self.responses.append(self.plan)
            return json.dumps(self.plan)
        heading = json.loads(prompt.split("\nHeading: ", 1)[1].splitlines()[0])
        facts = json.loads(prompt.split("\nFacts: ", 1)[1].splitlines()[0])
        documents = json.loads(prompt.split("\nDocuments: ", 1)[1].splitlines()[0])
        name = self.scenario
        fact = deepcopy(facts[0]) if facts else None
        claim = f"[{fact['id']}] [{fact['evidence_id']}]" if fact else ""
        selected = [fact] if fact else []
        if name.startswith("citation_") or name == "authorized_combined":
            identifier = documents[0]["id"] if documents else "S999"
            claim = {
                "citation_wrong_support": "A product missing from a snapshot should be treated as zero inventory.",
                "citation_wrong_support_second": "Stock quantities should be summed across dates.",
                "citation_supported_second": "Stock quantities should never be summed across dates.",
            }.get(name, "A missing product in a snapshot should be treated as missing data.")
            if FOLLOWUP:
                claim = {
                    "citation_wrong_support": "Goods held for quality inspection count as sellable inventory.",
                    "citation_wrong_support_second": "A low-stock signal automatically creates a purchase order.",
                    "citation_supported_second": "A reorder signal triggers replenishment review and does not automatically create a purchase order.",
                }.get(name, "Goods held for quality inspection do not count as sellable inventory.")
            claim += "" if name == "citation_uncited" else f" [{identifier if name != 'citation_unknown' else 'S999'}]"
            selected = []
        if name.startswith("fact_"):
            key, value = {"fact_value": ("value", "999999"), "fact_unit": ("unit", "USD"),
                          "fact_period": ("snapshot_date", "2026-10-31"),
                          "fact_entity": ("dimensions", {"product_id": "999999", "product_name": "other"})}[name]
            fact[key] = value
        if name == "wrong_heading":
            heading = "Unexpected heading"
        draft = {"sections": {heading: claim}, "claims": selected}
        self.responses.append(draft)
        return json.dumps(draft)


def markdown_template(bad=False):
    marker = "{{report:Other}}" if bad else "{{report:Inventory Overview}}"
    return ("# Inventory Overview\n\nRetained instructions.\n\n" + marker +
            "\n\n| snapshot_date | product_id | product_name | stock_on_hand |\n"
            "| --- | --- | --- | --- |\n| {{report:rows}} | | | |\n").encode()


async def delivery(result, payload, media):
    try:
        response = report_response(result, payload, media)
    except HTTPException as error:
        return {"status_code": error.status_code, "detail": error.detail}, b""
    if hasattr(response, "body"):
        data = response.body
    else:
        data = b"".join([part if isinstance(part, bytes) else part.encode() async for part in response.body_iterator])
    return {"status_code": response.status_code, "headers": dict(response.headers)}, data


def docx_text(payload):
    document = Document(BytesIO(payload))
    return {"headings": [p.text for p in document.paragraphs if p.style.name.startswith("Heading")],
            "paragraphs": [p.text for p in document.paragraphs],
            "tables": [[[cell.text for cell in row.cells] for row in table.rows] for table in document.tables]}


async def report(case, evidence):
    name = case["scenario"]
    sales = case["type"] == "sales_performance"
    checks, steps = {}, []
    permissions, roles, anonymous = ("analytics:read", "documents:read"), ("employee",), name == "anonymous"
    if name in {"no_analytics_scope", "sales_no_analytics"}:
        permissions = ("documents:read",)
    if name in {"no_document_scope", "sales_no_documents"}:
        roles = ()
    if sales:
        question = "Sales performance report for 2025." + (" Group by category." if name == "sales_unavailable" else "")
        revenue = evidence["sql"]["P01"]["rows"][0]["revenue"]

        async def execute(sql, *parameters):
            steps.append({"sql": sql, "parameters": parameters})
            if "WITH totals AS" in sql:
                assert parameters[:2] == (date(2025, 1, 1), date(2026, 1, 1)), parameters
                return [{"company_revenue": Decimal(revenue), "source_count": 352, "partial_period": True}]
            return []
        writer, rows = None, [{"revenue": revenue}]
        mode = "analytics"
        kwargs = {}
    else:
        question, plan, rows = inventory_inputs(name, evidence)
        writer = Writer(plan, name)

        async def execute(sql, *parameters):
            steps.append({"sql": sql, "parameters": parameters})
            if name == "failed_delivery":
                raise ConnectionError("fixture: source unavailable")
            return deepcopy(rows)
        mode = "combined" if case["category"] in {"citation", "rbac"} else "analytics"
        if mode == "combined":
            question += " Include relevant policy."
        kwargs = {"output_format": "docx" if name == "partial_docx" else "markdown",
                  "accept_supported_scope": name in {"partial_table", "partial_docx"}}
        if name in {"marked_template", "bad_placeholder"}:
            kwargs.update(filename="report.md", content=markdown_template(name == "bad_placeholder"))
    index = int(name.endswith("_second"))
    docs = [policy_evidence(evidence, index)]

    async def retrieve(scoped):
        if not scoped.identity or "employee" not in scoped.identity.document_roles:
            raise PermissionError("fixture: evidence denied")
        return docs

    knowledge = SimpleNamespace(retrieve=AsyncMock(side_effect=retrieve))
    repo = SimpleNamespace(execute_approved_query=execute)
    agent = ReportAgent(knowledge, SQLAnalyticsAgent(repo, inventory_only=False), llm=writer)
    denied = name in {"anonymous", "no_document_scope", "no_analytics_scope", "sales_no_analytics"}
    try:
        result, payload, media = await agent.generate_from_template(request(question, case["type"],
            permissions=permissions, roles=roles, anonymous=anonymous), source_mode=mode, **kwargs)
    except (AnalyticsPermissionDenied, ValueError) as error:
        if denied or name == "bad_placeholder":
            check(checks, "expected_rejection", isinstance(error, AnalyticsPermissionDenied) if denied else "placeholder" in str(error).lower())
            check(checks, "no_protected_access", not steps and not knowledge.retrieve.await_count and not (writer and writer.responses))
            raw = {"exception": type(error).__name__, "message": str(error), "repository_calls": steps, "retrieval_calls": knowledge.retrieve.await_count}
            return checks, False, raw, None
        raise
    data = result.model_dump(mode="json")
    status = result.metadata["status"]
    http, response = await delivery(result, payload, media)
    extension = {"application/json": "json", "text/markdown; charset=utf-8": "md",
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx"}[media]
    if payload:
        path = ROOT / "results/report" / (case["id"] + "." + extension)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    body = docx_text(payload) if payload and extension == "docx" else payload.decode() if payload else result.answer
    raw = {"result": data, "rendered": body, "http": http, "media_type": media, "repository_calls": steps,
           "retrieval_calls": knowledge.retrieve.await_count, "scripted_drafts": writer.responses if writer else []}
    accepted = status == "complete"
    if denied:
        check(checks, "expected_rejection", False)
    elif sales:
        document = json.loads(payload)
        metric = next(metric for metric in document["metrics"] if metric["id"] == "company_revenue")
        mutations = {"sales_unit", "sales_nonfinite", "sales_missing_citation", "sales_removed_section"}
        if name in mutations:
            accepted = True
            if name == "sales_unit":
                metric["unit"] = "fictitious-unit"
            elif name == "sales_nonfinite":
                metric["value"] = float("inf")
            elif name == "sales_missing_citation":
                metric["evidence"] = []
            else:
                document["sections"].pop(next(iter(document["sections"])))
            try:
                validate_report(document)
            except ValueError as error:
                raw["validator_error"] = str(error)
                accepted = False
            check(checks, "sales_validator_rejected_mutation", not accepted)
        elif name == "sales_unavailable":
            check(checks, "unavailable_not_zero", metric["value"] is None and status == "partial")
            accepted = checks["unavailable_not_zero"]
        else:
            check(checks, "sales_json_schema", validate_report(document) == document)
            if name in {"sales_value", "sales_scope"}:
                check(checks, "numerical_exact", Decimal(str(metric["value"])) == Decimal(revenue))
            check(checks, "period_exact", document["request"]["period"] == {"start": "2025-01-01", "end_exclusive": "2026-01-01"})
            if name == "sales_citation":
                check(checks, "citation_references_result", bool(metric["evidence"]) and all(
                    item["query_id"] in {e.citation_id for e in result.evidence} and item["source_table"] == "commerce.sales"
                    for item in metric["evidence"]))
            if name == "sales_no_documents":
                check(checks, "no_document_leak", knowledge.retrieve.await_count == 0 and not any(e.source_type == "document" for e in result.evidence)
                      and result.metadata["retrieval_status"] == "access_denied")
            if name == "sales_json":
                check(checks, "http_json_contract", http["status_code"] == 200 and http["headers"]["x-report-status"] == status
                      and json.loads(response) == document)
            accepted = status in {"complete", "partial"}
    elif name in {"inventory_empty", "failed_delivery", "unsupported", "wrong_snapshot", "missing_metric"}:
        expected = {"inventory_empty": ("failed", 422, "no_observations"), "failed_delivery": ("failed", 503, "source_unavailable"),
                    "unsupported": ("unsupported", 422, None), "wrong_snapshot": ("failed", 422, "validation_failed"),
                    "missing_metric": ("failed", 422, "validation_failed")}[name]
        target_status, code, reason = expected
        check(checks, "empty_or_invalid_safe", status == target_status and http["status_code"] == code and not response and not result.evidence)
        check(checks, "failure_reason", reason == result.metadata.get("failure_type"))
        if name == "unsupported":
            check(checks, "unsupported_before_repository", not steps)
        accepted = case["expect"] == "accept" and all(checks.values())
    else:
        display = json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else body
        if name in {"stock_value", "ratio_value"}:
            facts = [fact for fact in result.metadata.get("facts", []) if fact["metric"] in {"stock_on_hand", "stored_fill_rate"}]
            key = "stored_fill_rate" if name == "ratio_value" else "stock_on_hand"
            observed = {(fact["dimensions"]["product_id"], Decimal(fact["value"])) for fact in facts}
            expected = {(str(row["product_id"]), Decimal(str(row[key]))) for row in rows}
            check(checks, "numerical_exact", observed == expected)
            check(checks, "visible_numeric_values", all(f"{row[key]} [F" in display for row in rows)
                  if name == "stock_value" else "25% [F" in display)
        if name in {"marked_template", "generated_table"}:
            check(checks, "template_compliant", "# Inventory Overview" in display and "snapshot_date | product_id | product_name | stock_on_hand" in display
                  and "{{report:" not in display and (name != "marked_template" or "Retained instructions." in display))
        if name in {"partial_table", "partial_docx", "markdown"}:
            partial = name != "markdown"
            check(checks, "delivery_status", status == ("partial" if partial else "complete") and http["status_code"] == 200 and response == payload
                  and http["headers"]["x-report-status"] == status and f".{extension}" in http["headers"]["content-disposition"])
            if partial:
                check(checks, "partial_explained", "Supplier lead time is unavailable" in display)
            if extension == "docx":
                check(checks, "docx_table_and_headings", "Inventory Overview" in body["headings"] and bool(body["tables"])
                      and "{{report:" not in display and "[S1]" in display)
            accepted = all(checks.values())
        if name.startswith("citation_") or name == "authorized_combined":
            check(checks, "document_reference_valid", all(f"[{citation}]" in display for citation in
                  {e.citation_id for e in result.evidence if e.source_type == "document"}) and "[S999]" not in display)
        if name == "authorized_combined":
            check(checks, "authorized_sources_queried", bool(steps) and knowledge.retrieve.await_count == 1
                  and any(e.source_type == "document" for e in result.evidence))
        if name.startswith("citation_wrong_support"):
            # These two claims and prohibitions were adversarially paired when the fixture was designed.
            expected = ("stock quantities should be summed across dates" if index
                        else "a product missing from a snapshot should be treated as zero inventory")
            if FOLLOWUP:
                expected = ("a low-stock signal automatically creates a purchase order" if index
                            else "goods held for quality inspection count as sellable inventory")
            check(checks, "contradictory_fixture_supplied", docs[0].content == evidence["policy"][index]
                  and any(expected in str(draft.get("sections", {})).lower() for draft in writer.responses))
        if case["expect"] == "reject":
            check(checks, "mutation_rejected_by_production", status != "complete")
    check(checks, "expected_acceptance", accepted == (case["expect"] == "accept"))
    cited = [{"id": item.citation_id, "source": item.source, "content": item.content, "metadata": item.metadata}
             for item in result.evidence if item.source_type == "document"]
    if name == "sales_citation":
        cited.extend({"id": item["query_id"], "source": item["source_table"], "filters": item["filters"],
                      "verified_reference": "P01", "rows": evidence["sql"]["P01"]["rows"]}
                     for item in metric["evidence"])
    verified = [{"id": "P01" if sales else ("RATIO" if name == "ratio_value" else "P04"),
                 "rows": evidence["sql"]["P01" if sales else "P04"]["rows"] if name != "ratio_value" else rows}]
    if name == "inventory_empty":
        verified = [{"id": "EMPTY", "rows": [], "scope": "Controlled empty replay for the requested snapshot."}]
    if name in {"unsupported", "partial_table", "partial_docx"}:
        unsupported = {"id": "P05", "content": evidence["sql"]["P05"]["question"],
                       "reference_outcome": "Warehouse inventory and supplier lead time are not available in the published SQL pilot snapshot."}
        verified = [unsupported] if name == "unsupported" else [*verified, unsupported]
    if FOLLOWUP and docs and (name.startswith("citation_") or name == "authorized_combined"):
        for item in result.evidence:
            if item.source_type == "database":
                verified.append({"id": item.citation_id, "reference": "P04", "rows": rows,
                                 "fact_ids": [fact["id"] for fact in result.metadata.get("facts", [])
                                              if fact["evidence_id"] == item.citation_id]})
    semantic = {"question": question, "expectation": status,
        "candidate": ({"status": status, "request": document["request"], "metrics": document["metrics"][:4],
                       "sections": document["sections"], "limitations": document["data_quality"]["limitations"]} if sales else
                      {"status": status, "report": body}),
        "evidence": [*verified, *cited]}
    return checks, accepted, raw, semantic


def verify_inputs():
    manifest = load("config/provenance.json")
    assert git("-C", str(source_root()), "rev-parse", "HEAD").decode().strip() == COMMIT
    assert not git("-C", str(source_root()), "status", "--porcelain", "--untracked-files=no")
    for path, entry in manifest["sources"].items():
        assert digest(source(path, entry["commit"])) == entry["sha256"], path
    for name, checksum in manifest["frozen_sha256"].items():
        assert digest((ROOT / "datasets" / name).read_bytes()) == checksum, name


async def main(group=None):
    verify_inputs()
    evidence = load("datasets/evidence.json")
    for name, callback, n in (("dashboard", dashboard, 20), ("report", report, 40)):
        if group and name != group:
            continue
        cases = load(f"datasets/{name}_cases.json")
        assert len(cases) == n == len({case["id"] for case in cases})
        assert Counter(case["category"] for case in cases) == ({"fidelity": 4, "chart": 4, "filters": 4, "kpi": 4, "failure": 4}
                if name == "dashboard" else {"numerical": 10, "citation": 8, "template": 6, "missing": 6, "rbac": 6, "delivery": 4})
        records = []
        for case in cases:
            started = time.perf_counter()
            try:
                checks, accepted, raw, semantic = await callback(case, evidence)
                condition = accepted == (case["expect"] == "accept")
                status = "pass" if condition and all(checks.values()) else "fail"
            except Exception as error:
                status, checks, accepted, semantic = "blocked", {}, None, None
                raw = {"error": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            write(f"results/{name}/{case['id']}.raw.json", raw)
            records.append({**case, "status": status, "accepted": accepted, "checks": checks, "latency_ms": elapsed,
                            "judge_input": semantic if case["semantic"] else None})
            print(case["id"], status, [key for key, value in checks.items() if not value],
                  raw.get("message", "") if status == "blocked" else "")
        write(f"results/{name}/cases.json", records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=("dashboard", "report"))
    asyncio.run(main(parser.parse_args().group))
