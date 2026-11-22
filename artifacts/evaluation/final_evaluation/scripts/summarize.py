"""Generate aggregate metrics and the thesis report from saved observations."""
from collections import defaultdict
import json
import math
import re
from statistics import median, mean

from freeze import PACKAGE, ROOT, COMMIT, FOLLOWUP, write


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def proportion(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "rate": round(numerator / denominator, 6) if denominator else None}


def show(value):
    count = f'{value["numerator"]}/{value["denominator"]}'
    return f'{count} ({value["rate"]:.1%})' if value["rate"] is not None else count + " (N/A)"


def latency(values):
    values = sorted(value for value in values if value is not None)
    return {"n": len(values), "p50_ms": round(median(values), 2) if values else None,
            "p95_ms": round(values[math.ceil(len(values) * .95)-1], 2) if values else None}


def checks(records, predicate):
    values = [flag for item in records for key, flag in item["checks"].items() if predicate(key)]
    return proportion(sum(values), len(values))


def aggregate(records):
    observed = [item for item in records if item["status"] != "blocked"]
    valid = [item for item in observed if item["expect"] == "accept"]
    invalid = [item for item in observed if item["expect"] == "reject"]
    groups = defaultdict(list)
    for item in records:
        groups[item["category"]].append(item)
    return {"planned": len(records), "blocked": len(records)-len(observed),
            "accuracy": proportion(sum(item["status"] == "pass" for item in observed), len(observed)),
            "invalid_detection": proportion(sum(item["accepted"] is False for item in invalid), len(invalid)),
            "false_rejection": proportion(sum(item["accepted"] is False for item in valid), len(valid)),
            "numerical_exact_match": checks(observed, lambda name: name in
                {"row_exact_match", "kpi_matches_oracle", "numerical_exact", "table_numeric_exact_match"} or name.startswith("chart_values_")),
            "template_compliance": checks([item for item in valid if item["category"] == "template"],
                lambda name: name in {"template_compliant", "sales_json_schema"}),
            "categories": {key: proportion(sum(row["status"] == "pass" for row in rows), sum(row["status"] != "blocked" for row in rows))
                           for key, rows in groups.items()},
            "latency": latency([item["latency_ms"] for item in observed])}


def semantics(records, judgments):
    eligible = [item for item in records if item["semantic"]]
    scored = [judgments[item["id"]] for item in eligible if judgments.get(item["id"], {}).get("status") == "scored"]
    dims = sorted({dimension for item in eligible for dimension in item["semantic"]})
    usage = [item["usage"] for item in scored if item.get("usage")]
    return {"coverage": proportion(len(scored), len(eligible)), "blocked_or_unscored": len(eligible)-len(scored),
            "latency": latency([item["latency_ms"] for item in scored]),
            "usage_observed": len(usage), "total_tokens": sum(item["total_tokens"] for item in usage),
            "dimensions": {dimension: dimension_result(eligible, scored, dimension) for dimension in dims}}


def dimension_result(eligible, scored, dimension):
    values = [item["scores"][dimension]["score"] for item in scored if dimension in item["scores"]]
    return {"eligible": sum(dimension in item["semantic"] for item in eligible), "scored": len(values),
            "mean": round(mean(values), 3) if values else None,
            "full_credit": proportion(values.count(2), len(values)),
            "partial_credit": values.count(1), "zero_credit": values.count(0)}


def main():
    cohorts = {group: load(f"results/{group}/cases.json") for group in ("dashboard", "report")}
    judge = load("judge/judgments.json")
    by_id = {item["id"]: item for item in judge["records"]}
    results = {}
    for group, records in cohorts.items():
        results[group] = {"deterministic": aggregate(records), "semantic": semantics(records, by_id)}
        results[group]["failed_cases"] = [item["id"] for item in records if item["status"] == "fail"]
        results[group]["blocked_cases"] = [item["id"] for item in records if item["status"] == "blocked"]
        write(f"results/{group}/metrics.json", results[group])
    write("results/aggregate.json", results)
    names = {"dashboard": "Dashboard", "report": "Report"}
    metrics = {"accuracy": "Deterministic case accuracy", "invalid_detection": "Invalid detection",
               "false_rejection": "False rejection", "numerical_exact_match": "Numerical assertion exact-match",
               "template_compliance": "Valid template compliance"}
    lines = [
        "# Final evaluation for the December 2, 2026 capstone defense", "",
        f"Production application revision `{COMMIT}`. The evaluation used frozen inputs and unchanged production code.", "",
        "## Chapter IV · Methodology", "",
        "The Dashboard cohort used 20 cases, four per objective. The Report cohort used 40 cases across Sales Performance and "
        "Inventory Risk. It included 10 numerical, eight citation, six template, six missing-data, six RBAC, and four delivery cases. "
        "Valid controls included expected abstention and partial delivery. Invalid cases changed one input or contract element at a time. "
        "The replay measured downstream validation, rendering, and delivery using scripted inputs at the SQL, retrieval, and draft boundaries.", "",
        "Nhân’s five-case SQL pilot was the business evidence source. Supported gold rows, SQL, and parameters were checked against its "
        "independently executed frozen reference. Nhân’s later 40-case SQL preparation remained pending human review at the pinned revision. "
        "The provisional rows were excluded. Two Dashboard evidence sets and the Report percentage fixture used labeled synthetic inputs. "
        "Report document checks used two excerpts from the repository’s VietStyle operating policy. Huy’s unpublished benchmark was excluded "
        "at the user’s direction. No upstream SQL or Knowledge benchmark was rerun.", "",
        "Dashboard replay exercised the production document builder, reconciliation, chart building, and HTML rendering. Report replay used the "
        "public template generation entry point, strict Sales JSON validator, Inventory Risk renderer, and HTTP response handler. The RBAC tests "
        "used local identities and instrumented source boundaries. The semantic pass used the existing authenticated Modal GPT-OSS-120B "
        "deployment, vLLM on one A100 80 GB GPU, with temperature 0.01, default reasoning, up to six transient retries, and a 4,000-token cap. "
        "Judgments used the frozen 0–2 per-dimension rubric and schema-checked evidence IDs. Objective failures retain their deterministic result.", "",
        "## Chapter IV · Results", "",
        "| Metric | Dashboard | Report |", "|---|---:|---:|",
    ]
    for key, label in metrics.items():
        lines.append(f"| {label} | " + " | ".join(show(results[name]["deterministic"][key]) for name in names) + " |")
    lines.append("| Deterministic cases blocked | " + " | ".join(str(results[name]["deterministic"]["blocked"]) for name in names) + " |")
    lines.append("| Modal coverage | " + " | ".join(show(results[name]["semantic"]["coverage"]) for name in names) + " |")
    lines += ["", "Accuracy counts cases satisfying every applicable objective check and the expected acceptance outcome. Invalid detection "
              "counts invalid controls that production rejected, clarified, or withheld. False rejection counts valid controls that production "
              "failed to accept as intended. Numerical exact-match counts individual applicable row, chart-series, KPI, and typed-fact "
              "assertions. Valid template compliance counts valid template controls. Blocked cases are listed separately.", "",
              "| Agent | Primary case category | Deterministic pass |", "|---|---|---:|"]
    for group, name in names.items():
        for category, value in results[group]["deterministic"]["categories"].items():
            lines.append(f"| {name} | {category.upper() if category in {'kpi', 'rbac'} else category.capitalize()} | {show(value)} |")
    lines += ["", "### Automated semantic scores", "",
              "| Agent | Dimension | Scored / eligible | Mean / 2 | Full credit | Score 1 | Score 0 |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for group, name in names.items():
        for dimension, value in results[group]["semantic"]["dimensions"].items():
            lines.append(f"| {name} | {dimension.replace('_', ' ').capitalize()} | {value['scored']}/{value['eligible']} | "
                         f"{value['mean'] if value['mean'] is not None else 'N/A'} | {show(value['full_credit'])} | "
                         f"{value['partial_credit']} | {value['zero_credit']} |")
    lines += ["", "| Agent | Downstream cases | p50 / p95 ms | Scored Modal cases | Modal p50 / p95 ms | Reported tokens |",
              "|---|---:|---:|---:|---:|---:|"]
    for group, name in names.items():
        d = results[group]["deterministic"]["latency"]
        s = results[group]["semantic"]
        m = s["latency"]
        lines.append(f"| {name} | {d['n']} | {d['p50_ms']} / {d['p95_ms']} | {m['n']} | "
                     f"{m['p50_ms']} / {m['p95_ms']} | {s['total_tokens']:,} over {s['usage_observed']} calls |")
    smoke = load("judge/smoke.json")
    lines += ["", f"The synthetic Modal smoke request took **{smoke['latency_ms']:,.0f} ms** and its outcome was **{smoke['status']}**. "
              "Modal request timings include network, possible cold start, and retries. Modal scales to zero after 60 seconds of inactivity. "
              "Downstream latency excludes Modal and upstream service work.", "", "### Failure analysis", ""]
    explanations = {
        "D04": "A replayed revenue row of 13,299,822.25 passed through as a KPI. The independently verified oracle was 13,299,821.25.",
        "D12": "The Dashboard forwarded the November 13, 2026 scope and still accepted a source payload whose bound date was October 31, 2026.",
        "D16": "The table displayed 13,299,821.25 while a KPI from a second result for the same scope displayed 13,299,999.25. Both tiles completed.",
        "R15": "The writer said a missing product should count as zero inventory. The cited policy explicitly says it must not. The report completed.",
        "R16": "The writer said stock quantities should be summed across dates. The cited policy explicitly forbids that operation. The report completed.",
    }
    if FOLLOWUP:
        explanations.update({
            "R15": "The report completed with a claim that goods held for quality inspection count as sellable. Huy’s reviewed T021 passage VN#482 explicitly excludes them.",
            "R16": "The report completed with a claim that a low-stock signal automatically creates a purchase order. Huy’s reviewed T039 passage VN#398 limits the signal to replenishment review.",
        })
    for group, records in cohorts.items():
        for item in records:
            if item["status"] == "pass":
                continue
            id = item["id"]
            message = explanations.get(id) or f"{item['status'].capitalize()}. See the raw observation and case assertions."
            judgment = by_id.get(id, {})
            if judgment.get("status") == "scored":
                score = judgment["scores"].get("citation_support")
                if score:
                    message += f" Modal citation support was {score['score']}/2."
            lines.append(f"- **{id}** {message} [Raw observation](results/{group}/{id}.raw.json)")
    if by_id.get("D14", {}).get("scores", {}).get("chart_suitability", {}).get("score") == 1:
        if FOLLOWUP:
            lines += ["", "**Judge input limitation in D14.** The structured judge input included the table’s revenue values "
                      "but omitted its rendered month column. Modal deducted credit for the missing month. The delivered HTML "
                      "contains January and February 2025 alongside the two revenue values. [Rendered dashboard](results/dashboard/D14.html)"]
        else:
            lines += ["", "**Judge input limitation in D14.** Modal reported that the table lacked revenue. Its input contained "
                      "tile metadata and chart series. The independent HTML check found table values of 10 and 20 and verified "
                      "that they agreed with the KPI of 30. The deterministic pass stands. [Rendered dashboard](results/dashboard/D14.html)"]
    if not FOLLOWUP and by_id.get("R11", {}).get("scores", {}).get("citation_support", {}).get("score") == 1:
        lines += ["", "**Evidence alias limitation in R11.** Modal found the policy claim supported by S2. It deducted credit "
                  "because the report’s SQL and fact identifiers were absent from the judge evidence map, which supplied "
                  "the same data through P04. The citation score includes that input limitation. [Raw observation](results/report/R11.raw.json)"]
    if FOLLOWUP and by_id.get("R16", {}).get("scores", {}).get("citation_support", {}).get("score") == 1:
        lines += ["", "**Rubric inconsistency in R16.** Modal’s rationale identified the direct contradiction in S2, "
                  "but its 1/2 score also credited the supported SQL table. The rubric reserves 1/2 for partial support "
                  "without a direct contradiction. The reported Modal score is the raw judgment, and the deterministic "
                  "case remains a failure. [Judgment records](judge/judgments.json)"]
    production_log = ROOT / "results/production_tests.log"
    if production_log.exists():
        production_tests = re.search(r"Ran (\d+) tests[^\n]*\n\s*\nOK(?: \(skipped=(\d+)\))?",
                                     production_log.read_text(encoding="utf-8-sig"))
        if production_tests:
            total, skipped = int(production_tests[1]), int(production_tests[2] or 0)
            lines += ["", f"The focused production suite passed {total-skipped} tests and skipped {skipped} opt-in PostgreSQL cases. "
                      "[Production test log](results/production_tests.log)"]
    lines += ["", "## Chapter VI · Conclusions and limitations", "",
              "The Dashboard successfully preserved and rendered the frozen data in the valid controls. Deliberate discrepancies in the replayed "
              "source boundary exposed three places where a successful source status took precedence over the independent oracle. These tests "
              "show the downstream trust boundary. They do not measure how often the live SQL Agent emits those discrepancies.", "",
              "The Report rejected changed quantitative claims, malformed templates, and out-of-scope evidence requests in the isolated cases. "
              "The citation checks verified reference IDs, but two contradictory qualitative claims passed production validation. Their "
              "contradictions are directly visible in the frozen policy excerpts. Modal scores provide a separate review of the outputs.", "",
              "The cohorts are small, purposively selected, and reuse upstream evidence across controls and mutations. Some fixtures use "
              "synthetic inputs. Sales Performance and Inventory Risk expose different output contracts. DOCX was parsed structurally. "
              "The evaluation does not measure live retrieval, database permission enforcement, unrestricted generation, or Word visual layout. "
              "Report and Dashboard correctness rates are conditional on replay. Dashboard judge inputs included the expected handling of "
              "controlled requests, so chart suitability used an unblinded, rubric-guided review. "
              "Automated judge agreement is not independent verification.", "",
              "Reproduction steps are in the [README](README.md). Per-case records, raw artifacts and judge responses are retained under "
              "[results](results/) and [judge](judge/).", ""]
    if FOLLOWUP:
        knowledge = load("datasets/evidence.json")["knowledge"]
        lines[0] = "# Dashboard and Report follow-up with Huy’s Knowledge v3 evidence"
        lines[8] = (
            "Dashboard and Report numerical evidence continued to use Nhân’s independently verified frozen SQL pilot to "
            "preserve the fixture basis across rounds. The labeled synthetic controls also carried forward. "
            "Inventory Risk citation cases replayed Huy’s human-reviewed grade-2 excerpts for T021 and T039. "
            "The published answer scores below are upstream context. The reviewed excerpts supply the grounding oracle."
        )
        baseline = json.loads((PACKAGE / "judge/judgments.json").read_text(encoding="utf-8"))["records"]
        saved = {(item["id"], item.get("input_sha256"), item.get("started_utc")) for item in baseline}
        reused = sum((item["id"], item.get("input_sha256"), item.get("started_utc")) in saved for item in by_id.values())
        upstream = [
            "## Published Knowledge evidence", "",
            f"Huy’s `Huy-eval-v3` commit `{knowledge['commit']}`. The test-set hash "
            "matches the human-reviewed lock and the published score file matches its run manifest.", "",
            "| Knowledge run | Cases | Published accuracy | Wrong seal rate | Wrongly withheld rate |",
            "|---|---:|---:|---:|---:|",
        ]
        for row in knowledge["published_scores"]:
            upstream.append(f"| {row['run']} | {row['items']} | {row['accuracy']:.1%} | "
                            f"{row['wrong_seal_rate']:.1%} | {row['wrongly_withheld_rate']:.1%} |")
        upstream += ["", "T021 uses VN chunks 482 and 431. T039 uses VN chunks 629 and 398. These cases "
                     "anchor positive, contradictory, unknown-citation, and uncited Report fixtures. Huy’s scorer marked both answers correct in both "
                     "published runs. T039 was sealed in `test-prod-mminilm` and unverified in `test-prod`. "
                     "The downstream oracle is the reviewed passage in each case. Knowledge generation and scoring were not rerun.",
                     "", f"The follow-up reused {reused} archived Modal judgments with matching input, settings, rubric, and client hashes. "
                     "The semantic timing table includes retained observations. Dashboard D14 now includes the observed table values in its judge input, "
                     "and Report policy cases include emitted database citation IDs and their fact-ID mappings.", ""]
        index = lines.index("## Chapter IV · Results")
        lines[index:index] = upstream
        lines[-2] = ("Reproduction steps are in the [README](../README.md). The "
                     "[November 21 baseline](../FINAL_REPORT.md) used an earlier application revision and earlier policy fixtures. "
                     "The differences cannot be attributed solely to the Knowledge evidence update.")
    (ROOT / "FINAL_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
