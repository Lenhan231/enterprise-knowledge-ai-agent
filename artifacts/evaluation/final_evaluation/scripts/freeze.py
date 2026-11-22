"""Build the frozen downstream cases from the published SQL pilot and source policy."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[2]
FOLLOWUP = os.getenv("EKAI_EVAL_FOLLOWUP") == "1"
ROOT = PACKAGE / "followup-huy-v3" if FOLLOWUP else PACKAGE
COMMIT = "a2f57e67e45b965cda4e901d3e2647861655e4c5" if FOLLOWUP else "60eafaee964a6de48a0c8d13925e3207d5116588"
HUY = "f290f553af13f976cfd60862e013604892aabe71"
HUY_ROOT = "artifacts/evaluation/vietstyle-v3/"
SQL = "artifacts/sql-agent-bussiness/cases.json"
REFERENCE = "artifacts/sql-agent-bussiness/runs/pilot5-origin-main-e6f3b909/reference.json"
UNAPPROVED = "artifacts/sql-agent-bussiness/40-case-preparation/FREEZE_MANIFEST.json"
POLICY = "artifacts/datasets/vietstyle-operations-vi-v1/VietStyle_Enterprise_Operating_Policy_v1.0_VN.md"
POLICY_LINES = [
    "Không coi thiếu sản phẩm trong snapshot là tồn bằng không.",
    "Không cộng số lượng qua ngày; mỗi hàng là trạng thái/chỉ số tại ngày đó.",
]


def write(path, data):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    temp.replace(path)


def git(*args):
    return subprocess.check_output(["git", "-C", str(REPO), *args])


def source(path, commit=COMMIT):
    return git("show", f"{commit}:{path}")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_root():
    return Path(os.environ["EKAI_EVAL_SOURCE"]).resolve()


DASH = [
    ("fidelity", "P01", "revenue", "accept", []),
    ("fidelity", "P02", "table", "accept", []),
    ("fidelity", "P04", "bar", "accept", []),
    ("fidelity", "P01", "changed_row", "reject", []),
    ("chart", "P02", "bar", "accept", ["chart_suitability"]),
    ("chart", "SYN-TREND", "line", "accept", ["chart_suitability"]),
    ("chart", "P04", "line", "reject", ["chart_suitability"]),
    ("chart", "P03", "donut", "reject", ["chart_suitability"]),
    ("filters", "P02", "scope_delivery", "accept", []),
    ("filters", "P03", "scope_product", "accept", []),
    ("filters", "SYN-CATEGORY", "scope_category", "accept", ["chart_suitability"]),
    ("filters", "P04", "stale_snapshot", "reject", []),
    ("kpi", "P01", "kpi_table", "accept", []),
    ("kpi", "SYN-TREND", "kpi_chart_table", "accept", ["chart_suitability"]),
    ("kpi", "P03", "grouped_kpi", "reject", []),
    ("kpi", "P01", "inconsistent_kpi", "reject", []),
    ("failure", "P04", "empty", "accept", []),
    ("failure", "P05", "unsupported", "accept", []),
    ("failure", "P05", "failed_rows", "reject", []),
    ("failure", "P03", "invalid_field", "reject", []),
]

REPORT = [
    ("numerical", "sales", "sales_value", "accept"),
    ("numerical", "sales", "sales_scope", "accept"),
    ("numerical", "sales", "sales_unit", "reject"),
    ("numerical", "sales", "sales_nonfinite", "reject"),
    ("numerical", "inventory", "stock_value", "accept"),
    ("numerical", "inventory", "ratio_value", "accept"),
    ("numerical", "inventory", "fact_value", "reject"),
    ("numerical", "inventory", "fact_unit", "reject"),
    ("numerical", "inventory", "fact_period", "reject"),
    ("numerical", "inventory", "fact_entity", "reject"),
    ("citation", "inventory", "citation_supported", "accept"),
    ("citation", "inventory", "citation_supported_second", "accept"),
    ("citation", "inventory", "citation_unknown", "reject"),
    ("citation", "inventory", "citation_uncited", "reject"),
    ("citation", "inventory", "citation_wrong_support", "reject"),
    ("citation", "inventory", "citation_wrong_support_second", "reject"),
    ("citation", "sales", "sales_citation", "accept"),
    ("citation", "sales", "sales_missing_citation", "reject"),
    ("template", "inventory", "marked_template", "accept"),
    ("template", "inventory", "generated_table", "accept"),
    ("template", "inventory", "bad_placeholder", "reject"),
    ("template", "inventory", "wrong_heading", "reject"),
    ("template", "sales", "sales_template", "accept"),
    ("template", "sales", "sales_removed_section", "reject"),
    ("missing", "inventory", "inventory_empty", "accept"),
    ("missing", "inventory", "unsupported", "accept"),
    ("missing", "inventory", "partial_table", "accept"),
    ("missing", "inventory", "wrong_snapshot", "reject"),
    ("missing", "inventory", "missing_metric", "reject"),
    ("missing", "sales", "sales_unavailable", "accept"),
    ("rbac", "inventory", "anonymous", "reject"),
    ("rbac", "inventory", "no_document_scope", "reject"),
    ("rbac", "inventory", "no_analytics_scope", "reject"),
    ("rbac", "inventory", "authorized_combined", "accept"),
    ("rbac", "sales", "sales_no_documents", "accept"),
    ("rbac", "sales", "sales_no_analytics", "reject"),
    ("delivery", "inventory", "markdown", "accept"),
    ("delivery", "inventory", "partial_docx", "accept"),
    ("delivery", "inventory", "failed_delivery", "accept"),
    ("delivery", "sales", "sales_json", "accept"),
]

SEMANTIC = {
    "sales_value": ["factual_consistency"], "stock_value": ["factual_consistency"],
    "ratio_value": ["factual_consistency"], "sales_citation": ["citation_support"],
    "partial_table": ["report_completeness"], "inventory_empty": ["report_completeness"],
    "unsupported": ["report_completeness"], "generated_table": ["report_completeness"],
    "sales_unavailable": ["report_completeness"], "partial_docx": ["report_completeness"],
    "markdown": ["report_completeness"], "sales_json": ["report_completeness"],
    "authorized_combined": ["citation_support"],
    **{name: ["citation_support", "factual_consistency"] for name in (
        "citation_supported", "citation_supported_second", "citation_wrong_support",
        "citation_wrong_support_second")},
}


def knowledge_evidence():
    paths = ("MANIFEST.json", "test-v3.json", "REVIEW-test.md", "runs/MANIFEST.json",
             "runs/modal/test-versions-scores.json")
    blobs = {name: source(HUY_ROOT + name, HUY) for name in paths}
    assert digest(blobs["test-v3.json"]) == json.loads(blobs["MANIFEST.json"])["locked"]["test-v3.json"]
    score_path = paths[-1]
    run_record = json.loads(blobs["runs/MANIFEST.json"])["files"][score_path.removeprefix("runs/")]
    assert run_record == {"sha256": digest(blobs[score_path]), "bytes": len(blobs[score_path])}
    review = blobs["REVIEW-test.md"].decode()
    items = {item["id"]: item for item in json.loads(blobs["test-v3.json"])["items"]}
    scores = json.loads(blobs[score_path])
    selected = []
    for id in ("T021", "T039"):
        item = items[id]
        reviewed = review.split("### " + id + " ", 1)[1].split("\n### ", 1)[0]
        excerpts = dict((int(index), text) for index, text in re.findall(r"^- gold VN#(\d+): _(.*)_\s*$", reviewed, re.M))
        labels = [label for label in item["gold"] if label["grade"] == 2 and not label.get("source")
                  and label["document"].endswith("_VN.pdf")]
        assert item["expected_outcome"] == "answer" and len(labels) == 2
        selected.append({**{key: item[key] for key in ("id", "question", "role", "reference_answer", "expected_outcome")},
                         "passages": [{**label, "content": excerpts[label["chunk_index"]]} for label in labels]})
    frozen_runs = [{**{key: row[key] for key in ("run", "items", "accuracy", "wrong_seal_rate", "wrongly_withheld_rate")},
                    "selected_case_results": {item["id"]: row["per_item"][item["id"]] for item in selected}}
                   for row in scores if row["run"] in {"test-prod", "test-prod-mminilm"}]
    assert len(frozen_runs) == 2 and all(row["items"] == 60 for row in frozen_runs)
    manifest = {HUY_ROOT + path: {"commit": HUY, "sha256": digest(blob)}
                for path, blob in blobs.items()}
    return {"commit": HUY, "cases": selected, "published_scores": frozen_runs,
            "dataset_sha256": digest(blobs["test-v3.json"])}, manifest


def main():
    if FOLLOWUP:
        write("judge/rubric.json", json.loads((PACKAGE / "judge/rubric.json").read_text(encoding="utf-8")))
    files = {name: source(name) for name in (SQL, REFERENCE, POLICY, UNAPPROVED)}
    sql = {case["id"]: case for case in json.loads(files[SQL])["cases"]}
    reference = {case["id"]: case for case in json.loads(files[REFERENCE])["cases"]}
    for id, case in sql.items():
        if case["supported"]:
            assert reference[id]["matches_frozen_gold"] and reference[id]["rows"] == case["gold"]["rows"], id
            assert all(reference[id][key] == case["gold"][key] for key in ("sql", "parameters")), id
    policy_text = files[POLICY].decode()
    assert all(line in policy_text for line in POLICY_LINES)
    payload = {id: {**case["gold"], "question": case["question"], "supported": case["supported"]}
               for id, case in sql.items()}
    payload["SYN-TREND"] = {
        "question": "Show a monthly revenue line chart and table.",
        "sql": "SELECT DATE_TRUNC('month', s.date)::date AS month, SUM(s.revenue) AS revenue "
               "FROM commerce.sales s GROUP BY 1 ORDER BY 1 LIMIT 12",
        "parameters": [], "rows": [{"month": "2025-01-01", "revenue": 10},
                                   {"month": "2025-02-01", "revenue": 20}], "supported": True,
    }
    payload["SYN-CATEGORY"] = {
        "question": "Show a bar chart of stock on hand for category Apparel grouped by product.",
        "sql": "SELECT p.product_id, SUM(i.stock_on_hand) AS stock_on_hand FROM commerce.inventory i "
               "JOIN commerce.products p ON p.product_id=i.product_id WHERE p.category=$1 GROUP BY 1 LIMIT 10",
        "parameters": ["Apparel"], "rows": [{"product_id": 11, "stock_on_hand": 13},
                                           {"product_id": 12, "stock_on_hand": 17}], "supported": True,
    }
    evidence = {"sql": payload, "policy": POLICY_LINES, "ratio": {"value": "0.25", "display": "25%"},
                "policy_source": POLICY}
    if FOLLOWUP:
        knowledge, sources = knowledge_evidence()
        evidence.update(knowledge=knowledge,
                        policy=["\n".join(p["content"] for p in item["passages"]) for item in knowledge["cases"]])
    write("datasets/evidence.json", evidence)
    dash = [{"id": f"D{i:02}", "category": bucket, "evidence": id, "scenario": scenario,
             "expect": expect, "semantic": semantic}
            for i, (bucket, id, scenario, expect, semantic) in enumerate(DASH, 1)]
    report = []
    for i, (bucket, kind, scenario, expect) in enumerate(REPORT, 1):
        ids = ["P01"] if kind == "sales" else ["P04"]
        if scenario == "ratio_value":
            ids = ["RATIO"]
        if scenario in {"unsupported", "partial_table", "partial_docx"}:
            ids.append("P05")
        if kind == "inventory" and (bucket == "citation" or scenario == "authorized_combined"):
            ids.append(("T039" if scenario.endswith("_second") else "T021") if FOLLOWUP else "POLICY")
        report.append({"id": f"R{i:02}", "category": bucket,
                       "type": "sales_performance" if kind == "sales" else "inventory_risk",
                       "evidence": ids, "scenario": scenario, "expect": expect, "semantic": SEMANTIC.get(scenario, [])})
    write("datasets/dashboard_cases.json", dash)
    write("datasets/report_cases.json", report)
    manifest = {path: {"commit": COMMIT, "sha256": digest(data),
                       "last_change": git("log", "-1", "--format=%H", COMMIT, "--", path).decode().strip()}
                for path, data in files.items()}
    provisional = json.loads(files[UNAPPROVED])
    assert provisional["freeze_status"] == "DRAFT" and not provisional["readiness"]["ready_for_40_case_execution"]
    if FOLLOWUP:
        manifest.update(sources)
    write("config/provenance.json", {"application_commit": COMMIT, "sources": manifest,
          "frozen_sha256": {name: digest((ROOT / "datasets" / name).read_bytes()) for name in
                            ("evidence.json", "dashboard_cases.json", "report_cases.json")},
          **({"sql_reference": "published frozen five-case pilot, retained for continuity"} if FOLLOWUP else
             {"sql_expansion_excluded": {"path": UNAPPROVED, "readiness": provisional["status"]}}),
          "knowledge_benchmark": knowledge["commit"] if FOLLOWUP else "out of cohort by user direction",
          "upstream_calls": 0})


if __name__ == "__main__":
    main()
