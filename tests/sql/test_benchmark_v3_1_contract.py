"""Regression checks for v3.1/v3.2 scoring; never runs the held-out SQL Agent."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "artifacts/sql-agent-bussiness/40-case-v3"
HERE = ROOT / "artifacts/sql-agent-bussiness/40-case-v3-1"


def read(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def digest(data):
    return hashlib.sha256(json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


CASES = read("cases_v3_1_draft.json")
GOLD = read("gold_sql_v3_1_draft.json")
RESULTS = read("gold_results_v3_1_provisional.json")
ORIGINAL_CASES = json.loads((OLD / "cases_v3_draft.json").read_text(encoding="utf-8"))
ORIGINAL_GOLD = json.loads((OLD / "gold_sql_v3_draft.json").read_text(encoding="utf-8"))
BY_ID = {item["id"]: item for item in CASES["cases"]}
GOLD_BY_ID = {item["id"]: item for item in GOLD["cases"]}
RESULT_BY_ID = {item["id"]: item for item in RESULTS["cases"]}
spec = importlib.util.spec_from_file_location("benchmark_scorer_v3", OLD / "scorer_v3.py")
assert spec is not None and spec.loader is not None
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)
spec_v31 = importlib.util.spec_from_file_location(
    "benchmark_scorer_v3_1", HERE / "scorer_v3_1.py"
)
assert spec_v31 is not None and spec_v31.loader is not None
scorer_v31 = importlib.util.module_from_spec(spec_v31)
spec_v31.loader.exec_module(scorer_v31)
audit = scorer_v31._audit
spec_mutations = importlib.util.spec_from_file_location(
    "mutation_runner_v3_1", HERE / "run_mutation_probes_v3_1.py"
)
assert spec_mutations is not None and spec_mutations.loader is not None
mutation_runner = importlib.util.module_from_spec(spec_mutations)
spec_mutations.loader.exec_module(mutation_runner)


class V31ContractTests(unittest.TestCase):
    def test_review_page_can_restore_committed_approvals_after_browser_reset(self):
        page = (HERE / "SEMANTIC_REVIEW_V3_1.html").read_text(encoding="utf-8")
        self.assertIn('id="restoreRecordedReviews"', page)
        self.assertIn('"review_v3_1_reviewer_1_Lenhan231_complete.json"', page)
        self.assertIn('"review_v3_1_reviewer_2_user_reported_complete.json"', page)
        self.assertIn("async function restoreRecordedReviews()", page)
        self.assertIn("await importReview({ name: filename, text: async () => text }, role)", page)
        self.assertIn("40/40 APPROVE mỗi reviewer", page)
        self.assertIn("Adjudication và freeze vẫn đang chờ", page)

    def test_recovered_reviewer_approval_is_linked_and_does_not_freeze_cohort(self):
        manifest = read("FREEZE_MANIFEST_V3_1_DRAFT.json")
        review_path = HERE / "review_v3_1_reviewer_1_Lenhan231_complete.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review2_path = HERE / "review_v3_1_reviewer_2_user_reported_complete.json"
        review2 = json.loads(review2_path.read_text(encoding="utf-8"))
        self.assertEqual(review["review_format"], "sql-agent-benchmark-semantic-review")
        self.assertEqual(review["benchmark_version"], "v3.1")
        self.assertEqual(review["reviewer"]["id"], "Lenhan231")
        self.assertEqual(review["reviewer"]["role"], "reviewer_1")
        self.assertEqual(len(review["case_reviews"]), 40)
        self.assertEqual(set(review["case_reviews"]), set(BY_ID))
        self.assertEqual({r["decision"] for r in review["case_reviews"].values()}, {"APPROVE"})
        self.assertEqual(review2["reviewer"]["role"], "reviewer_2")
        self.assertEqual(review2["recording"]["source"], "explicit_user_report_after_reviewer_browser_state_reset")
        self.assertEqual(set(review2["case_reviews"]), set(BY_ID))
        self.assertEqual({r["decision"] for r in review2["case_reviews"].values()}, {"APPROVE"})
        self.assertEqual(
            review["artifact_sha256"],
            manifest["artifacts_sha256"],
        )
        self.assertEqual(review2["artifact_sha256"], manifest["artifacts_sha256"])
        self.assertEqual(
            manifest["review"]["reviewer_1"]["record_sha256"],
            hashlib.sha256(review_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            manifest["review"]["reviewer_2"]["record_sha256"],
            hashlib.sha256(review2_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(manifest["review"]["review_records_logged"], 2)
        self.assertEqual(manifest["review"]["independent_human_reviewers_approved"], 2)
        self.assertEqual(manifest["review"]["reviewer_2"]["approved_cases"], 40)
        self.assertEqual(manifest["review"]["adjudication"], "PENDING")
        self.assertEqual(manifest["freeze_status"], "DRAFT_NOT_FROZEN")
        self.assertFalse(manifest["ready_for_formal_freeze"])
        self.assertFalse(manifest["ready_for_40_case_sql_agent_run"])

    def test_distribution_references_hash_and_human_gate(self):
        self.assertEqual(len(CASES["cases"]), 40)
        self.assertEqual(len(GOLD["cases"]), 30)
        self.assertEqual(len(RESULTS["cases"]), 30)
        self.assertEqual(CASES["status"], "DRAFT_PENDING_HUMAN_REVIEW")
        self.assertEqual(GOLD["review_status"], "PENDING_TWO_INDEPENDENT_REVIEWERS")
        self.assertEqual(GOLD["independent_review_approvals"], 0)
        self.assertFalse(GOLD["human_approval_claimed"])
        self.assertFalse(RESULTS["heldout_agent_executed"])
        self.assertEqual(RESULTS["independent_review_approvals"], 0)
        manifest = read("FREEZE_MANIFEST_V3_1_DRAFT.json")
        self.assertEqual(manifest["protocol_version"], "3.2.0")
        self.assertEqual(manifest["scorer_version"], "3.2.0")
        self.assertEqual(manifest["revised_case_set_sha256"], digest(CASES))
        for relative_path, expected_sha256 in manifest["scoring_artifacts_sha256"].items():
            self.assertEqual(
                hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest(),
                expected_sha256,
                relative_path,
            )
        self.assertEqual(digest(CASES), GOLD["case_set_sha256"])
        self.assertEqual(digest(CASES), RESULTS["case_set_sha256"])
        self.assertEqual(digest([
            {"id": g["id"], "sql": g["sql"], "parameters": g["parameters"]}
            for g in GOLD["cases"]
        ]), RESULTS["gold_sql_definition_sha256"])
        self.assertEqual(
            hashlib.sha256((HERE / "gold_sql_v3_1_draft.json").read_bytes()).hexdigest(),
            RESULTS["gold_sql_draft_file_sha256"],
        )
        self.assertEqual(
            hashlib.sha256((HERE / "cases_v3_1_draft.json").read_bytes()).hexdigest(),
            RESULTS["revised_artifact_hashes"]["cases_v3_1_draft_sha256"],
        )

    def test_all_stored_gold_rows_match_revised_contract(self):
        self.assertEqual(sum(i["row_count"] for i in RESULTS["cases"]), 404)
        self.assertEqual(set(GOLD_BY_ID), set(RESULT_BY_ID))
        for ident, case in BY_ID.items():
            self.assertEqual(case["review_status"], "PENDING_TWO_INDEPENDENT_REVIEWERS")
            if case["expected_behavior"] != "execute":
                self.assertNotIn(ident, GOLD_BY_ID)
                continue
            self.assertIn(ident, RESULT_BY_ID)
            r, g = RESULT_BY_ID[ident], GOLD_BY_ID[ident]
            self.assertEqual(r["sql"], g["sql"])
            self.assertEqual(r["parameters"], g["parameters"])
            self.assertEqual(r["columns"], case["output_contract"]["columns"])
            self.assertEqual(r["row_count"], len(r["rows"]))
            self.assertTrue(all(list(row) == r["columns"] for row in r["rows"]))
            self.assertEqual(r["result_sha256"], digest({"columns": r["columns"], "rows": r["rows"]}))

    def test_unrequested_columns_removed_without_changing_questions(self):
        exclusions = {
            "B40-002": "completed_shipment_count",
            "B40-021": "observed_product_count",
            "B40-024": "observed_products",
        }
        old_by_id = {c["id"]: c for c in ORIGINAL_CASES["cases"]}
        for ident, col in exclusions.items():
            self.assertEqual(BY_ID[ident]["question"], old_by_id[ident]["question"])
            self.assertNotIn(col, BY_ID[ident]["output_contract"]["columns"])
            self.assertNotIn(col, GOLD_BY_ID[ident]["sql"])
            self.assertNotIn(col, RESULT_BY_ID[ident]["columns"])

    def test_stale_metadata_is_repaired(self):
        self.assertIn("Hai Phong", BY_ID["B40-006"]["required_metric_or_intent"])
        self.assertIn("25-34", BY_ID["B40-006"]["required_metric_or_intent"])
        self.assertIn("commerce.geography.city", BY_ID["B40-006"]["required_columns"])
        self.assertNotIn("commerce.geography.region", BY_ID["B40-006"]["required_columns"])
        self.assertIn("no year grouping", BY_ID["B40-017"]["required_metric_or_intent"])
        self.assertIn("top two", BY_ID["B40-029"]["required_metric_or_intent"])
        self.assertEqual(BY_ID["B40-029"]["top_n"], 2)

    def test_only_explicit_rankings_are_order_sensitive(self):
        expected = {"B40-011", "B40-012", "B40-013", "B40-014",
                    "B40-015", "B40-029", "B40-030"}
        actual = {c["id"] for c in CASES["cases"]
                  if c["expected_behavior"] == "execute" and c["output_contract"]["ordered"]}
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 7)
        self.assertEqual(sum(c["output_contract"]["ordered"] for c in ORIGINAL_CASES["cases"]
                             if c["expected_behavior"] == "execute"), 26)

    def test_aliases_have_no_collisions(self):
        for case in CASES["cases"]:
            if case["expected_behavior"] != "execute":
                continue
            seen = {c.casefold() for c in case["output_contract"]["columns"]}
            for canonical, alts in case["column_aliases"].items():
                self.assertIn(canonical, case["output_contract"]["columns"])
                for alias in alts:
                    self.assertNotIn(alias.casefold(), seen)
                    seen.add(alias.casefold())

    def test_shuffled_unranked_case_passes_and_explicit_rank_fails(self):
        for ident, expected in (("B40-001", True), ("B40-012", False)):
            row = RESULT_BY_ID[ident]
            compared = scorer.compare_business_results(
                BY_ID[ident], row["rows"],
                {"columns": row["columns"], "rows": list(reversed(row["rows"]))},
            )
            self.assertEqual(compared["business_rows_match"], expected)

    def test_unordered_rows_do_not_remove_top_n_ranking_obligation(self):
        unordered_ranked = [
            c for c in CASES["cases"]
            if c["expected_behavior"] == "execute"
            and not c["output_contract"]["ordered"] and c.get("ranking")
        ]
        self.assertEqual(len(unordered_ranked), 19)
        required = {c["id"] for c in unordered_ranked if c.get("top_n")}
        self.assertEqual(required, {"B40-005"})
        for case in unordered_ranked:
            gold_sql = GOLD_BY_ID[case["id"]]["sql"]
            result = audit.audit_ranking_contract(case, gold_sql)
            self.assertEqual(
                result["decision"], "PASS" if case["id"] == "B40-005" else "NOT_REQUIRED",
                case["id"],
            )

    def test_top_n_ranking_and_tie_break_are_checked_even_when_rows_are_unordered(self):
        case = {
            "id": "SYNTHETIC-TOP-N",
            "top_n": 2,
            "output_contract": {"ordered": False},
            "ranking": [
                {"field": "metric", "direction": "desc"},
                {"field": "name", "direction": "asc"},
            ],
        }
        valid = "SELECT name, SUM(value) AS metric FROM t GROUP BY name ORDER BY metric DESC, name ASC LIMIT 2"
        self.assertEqual(audit.audit_ranking_contract(case, valid)["decision"], "PASS")
        wrong_tie = valid.replace("name ASC", "name DESC")
        self.assertEqual(audit.audit_ranking_contract(case, wrong_tie)["decision"], "FAIL")
        wrong_limit = valid.replace("LIMIT 2", "LIMIT 3")
        self.assertEqual(audit.audit_ranking_contract(case, wrong_limit)["decision"], "FAIL")
        missing_order = "SELECT name, SUM(value) AS metric FROM t GROUP BY name LIMIT 2"
        self.assertEqual(audit.audit_ranking_contract(case, missing_order)["decision"], "FAIL")

    def test_v31_scorer_rejects_wrong_top_n_order_even_when_audit_record_claims_pass(self):
        case = BY_ID["B40-029"]
        gold_result = RESULT_BY_ID[case["id"]]
        wrong_sql = GOLD_BY_ID[case["id"]]["sql"].replace(
            "returned_units DESC", "returned_units ASC", 1
        )
        observation = {
            "id": case["id"], "status": "executed", "sql_semantic_valid": True,
            "sql": wrong_sql, "parameters": gold_result["parameters"],
            "columns": gold_result["columns"], "rows": gold_result["rows"],
        }
        record = audit.create_audit_record(
            case=case, case_set_sha256=digest(CASES), observation=observation,
            auditor_id="reviewer-3", auditor_version="manual-1", decision="PASS",
            evidence=["synthetic conflict fixture: independent record is overridden by deterministic ranking failure"],
        )
        result = scorer_v31.score(
            CASES, RESULTS,
            {"cases": [observation], "independent_semantic_audits": [record]},
        )
        audit_result = result["semantic_audits"][case["id"]]
        self.assertEqual(audit_result["ranking_check"]["decision"], "FAIL")
        self.assertEqual(audit_result["decision"], "FAIL")
        self.assertEqual(result["metrics"]["supported_business_end_to_end_accuracy"]["numerator"], 0)

    def test_wrong_selected_top_one_row_fails_when_output_row_order_is_unordered(self):
        row = RESULT_BY_ID["B40-005"]
        self.assertTrue(row["rows"])
        wrong = [dict(row["rows"][0])]
        wrong[0]["month"] = "2024-06-01"
        compared = scorer.compare_business_results(
            BY_ID["B40-005"], row["rows"],
            {"columns": row["columns"], "rows": wrong},
        )
        self.assertFalse(compared["business_rows_match"])

    def test_v31_scorer_ignores_agent_semantic_boolean_without_linked_audit(self):
        case = {
            "id": "SYNTHETIC-1", "expected_behavior": "execute",
            "output_contract": {"columns": ["value"], "ordered": False},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        cases_doc = {"cases": [case]}
        observation = {
            "id": case["id"], "status": "executed", "sql_semantic_valid": True,
            "sql": "SELECT 1 AS value", "parameters": [],
            "columns": ["value"], "rows": [{"value": 1}],
        }
        result = scorer_v31.score(
            cases_doc, {"cases": [{"id": case["id"], "rows": [{"value": 1}]}]},
            {"cases": [observation]},
        )
        self.assertEqual(result["metrics"]["sql_semantic_accuracy"]["value"], 0.0)
        self.assertEqual(result["metrics"]["sql_semantic_accuracy"]["denominator"], 1)
        self.assertEqual(result["metrics"]["independent_semantic_audit_coverage"]["numerator"], 0)
        self.assertEqual(result["metrics"]["supported_business_end_to_end_accuracy"]["numerator"], 0)

    def test_v31_scorer_accepts_only_audit_linked_to_case_sql_and_parameters(self):
        case = {
            "id": "SYNTHETIC-2", "expected_behavior": "execute",
            "output_contract": {"columns": ["value"], "ordered": False},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        cases_doc = {"cases": [case]}
        observation = {
            "id": case["id"], "status": "executed", "sql_semantic_valid": False,
            "sql": "SELECT $1 AS value", "parameters": [7],
            "columns": ["value"], "rows": [{"value": 7}],
        }
        record = audit.create_audit_record(
            case=case, case_set_sha256=audit.canonical_sha256(cases_doc),
            observation=observation, auditor_id="reviewer-1", auditor_version="manual-1",
            decision="PASS", evidence=["required projection and result were independently reviewed"],
        )
        document = {
            "cases": [observation], "independent_semantic_audits": [record],
        }
        reference = {"cases": [{"id": case["id"], "rows": [{"value": 7}]}]}
        passed = scorer_v31.score(cases_doc, reference, document)
        self.assertEqual(passed["metrics"]["sql_semantic_accuracy"]["numerator"], 1)
        self.assertEqual(passed["metrics"]["supported_business_end_to_end_accuracy"]["numerator"], 1)

        tampered = json.loads(json.dumps(document))
        tampered["cases"][0]["parameters"] = [8]
        rejected = scorer_v31.score(cases_doc, reference, tampered)
        self.assertEqual(rejected["semantic_audits"][case["id"]]["decision"], "INDETERMINATE")
        self.assertEqual(rejected["metrics"]["sql_semantic_accuracy"]["denominator"], 1)
        self.assertEqual(rejected["metrics"]["sql_semantic_accuracy"]["numerator"], 0)

        tampered_sql = json.loads(json.dumps(document))
        tampered_sql["cases"][0]["sql"] = "SELECT 8 AS value"
        sql_hash_rejected = scorer_v31.score(cases_doc, reference, tampered_sql)
        self.assertIn(
            "sql_hash_mismatch",
            sql_hash_rejected["semantic_audits"][case["id"]]["reason_codes"],
        )

        changed_case = json.loads(json.dumps(cases_doc))
        changed_case["cases"][0]["required_filters"] = ["value = 7"]
        contract_rejected = scorer_v31.score(changed_case, reference, document)
        self.assertIn(
            "case_contract_hash_mismatch",
            contract_rejected["semantic_audits"][case["id"]]["reason_codes"],
        )

    def test_review_required_and_indeterminate_are_not_counted_as_audit_passes(self):
        case = {
            "id": "SYNTHETIC-3", "expected_behavior": "execute",
            "output_contract": {"columns": ["value"], "ordered": False},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        cases_doc = {"cases": [case]}
        observation = {
            "id": case["id"], "status": "executed", "sql_semantic_valid": True,
            "sql": "SELECT 1 AS value", "parameters": [],
            "columns": ["value"], "rows": [{"value": 1}],
        }
        record = audit.create_audit_record(
            case=case, case_set_sha256=audit.canonical_sha256(cases_doc),
            observation=observation, auditor_id="reviewer-1", auditor_version="manual-1",
            decision="REVIEW_REQUIRED", evidence=["join meaning requires a domain reviewer"],
        )
        result = scorer_v31.score(
            cases_doc, {"cases": [{"id": case["id"], "rows": [{"value": 1}]}]},
            {"cases": [observation], "independent_semantic_audits": [record]},
        )
        self.assertEqual(result["semantic_audits"][case["id"]]["decision"], "REVIEW_REQUIRED")
        self.assertEqual(result["metrics"]["semantic_audit_unresolved"]["count"], 1)
        self.assertEqual(result["metrics"]["sql_semantic_accuracy"]["value"], 0.0)
        self.assertEqual(
            result["metrics"]["independent_semantic_audit_accuracy"]["status"],
            "NOT MEASURABLE",
        )

    def test_failed_independent_filter_audit_blocks_end_to_end_even_when_agent_claims_valid(self):
        case = {
            "id": "SYNTHETIC-FILTER", "expected_behavior": "execute",
            "required_filters": ["order_status = delivered"],
            "output_contract": {"columns": ["order_count"], "ordered": False},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        cases_doc = {"cases": [case]}
        observation = {
            "id": case["id"], "status": "executed", "sql_semantic_valid": True,
            "sql": "SELECT COUNT(*) AS order_count FROM commerce.orders",
            "parameters": [], "columns": ["order_count"], "rows": [{"order_count": 2}],
        }
        record = audit.create_audit_record(
            case=case, case_set_sha256=audit.canonical_sha256(cases_doc),
            observation=observation, auditor_id="reviewer-2", auditor_version="manual-1",
            decision="FAIL", evidence=["required delivered-order predicate is absent"],
        )
        result = scorer_v31.score(
            cases_doc, {"cases": [{"id": case["id"], "rows": [{"order_count": 2}]}]},
            {"cases": [observation], "independent_semantic_audits": [record]},
        )
        self.assertEqual(result["metrics"]["sql_semantic_accuracy"], {
            "numerator": 0, "denominator": 1, "value": 0.0, "status": "MEASURABLE",
        })
        self.assertEqual(result["metrics"]["business_result_accuracy"]["value"], 1.0)
        self.assertEqual(result["metrics"]["supported_business_end_to_end_accuracy"]["numerator"], 0)

    def test_failure_taxonomy_and_not_run_denominators_are_separate(self):
        supported = {
            "id": "SYNTHETIC-S", "expected_behavior": "execute",
            "output_contract": {"columns": ["value"], "ordered": False},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        unsupported = {
            "id": "SYNTHETIC-U", "expected_behavior": "clarify",
            "output_contract": {"columns": [], "ordered": False},
        }
        not_run = {**supported, "id": "SYNTHETIC-NR"}
        cases_doc = {"cases": [supported, unsupported, not_run]}
        result = scorer_v31.score(
            cases_doc, {"cases": []},
            {"cases": [
                {"id": "SYNTHETIC-S", "status": "failed", "error_type": "SQLValidationError"},
                {"id": "SYNTHETIC-U", "status": "clarification_required", "answer": "Unavailable fields.",
                 "clarification_options": [], "sql": None, "execution_events": []},
                {"id": "SYNTHETIC-NR", "status": "NOT RUN"},
            ]},
        )
        self.assertEqual(result["metrics"]["false_clarification_abstention"]["numerator"], 0)
        self.assertEqual(result["metrics"]["supported_noncompletion"], {
            "numerator": 1, "denominator": 1, "value": 1.0,
        })
        self.assertEqual(result["metrics"]["validation_blocked_supported"], {
            "numerator": 1, "denominator": 1, "value": 1.0,
        })
        self.assertEqual(result["metrics"]["valid_clarification_abstention"], {
            "numerator": 1, "denominator": 1, "value": 1.0,
        })
        self.assertIn("SYNTHETIC-NR", result["not_run_case_ids"])

    def test_provider_failure_is_not_semantic_refusal_and_invalid_clarification_is_not_abstention(self):
        case = {
            "id": "SYNTHETIC-P", "expected_behavior": "execute",
            "output_contract": {"columns": ["value"], "ordered": False},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        unsupported = {"id": "SYNTHETIC-U", "expected_behavior": "clarify",
                       "output_contract": {"columns": [], "ordered": False}}
        result = scorer_v31.score(
            {"cases": [case, unsupported]}, {"cases": []},
            {"cases": [
                {"id": case["id"], "status": "failed", "error_type": "ProviderTimeout"},
                {"id": unsupported["id"], "status": "clarification_required",
                 "answer": "Which option?", "clarification_options": ["", {"label": "bad"}],
                 "sql": None, "execution_events": []},
            ]},
        )
        self.assertEqual(result["metrics"]["provider_network_failure_count"]["count"], 1)
        self.assertEqual(result["metrics"]["false_clarification_abstention"]["numerator"], 0)
        self.assertEqual(result["metrics"]["valid_clarification_abstention"]["numerator"], 0)

    def test_v32_column_order_and_approved_aliases_preserve_business_values(self):
        for case_id in ("B40-001", "B40-004"):
            case = BY_ID[case_id]
            gold = RESULT_BY_ID[case_id]
            if case_id == "B40-001":
                actual_columns = list(reversed(gold["columns"]))
                actual_rows = [{key: row[key] for key in actual_columns} for row in gold["rows"]]
            else:
                actual_columns = ["aov", "month"]
                actual_rows = [
                    {"aov": row["average_order_value"], "month": row["month"]}
                    for row in gold["rows"]
                ]
            compared = scorer_v31.compare_business_results(
                case, gold["rows"], {"columns": actual_columns, "rows": actual_rows},
            )
            with self.subTest(case_id=case_id):
                self.assertEqual(compared["business_result_decision"], "PASS")
                self.assertEqual(compared["output_contract_decision"], "PASS")
                self.assertFalse(compared["strict_schema_match"])

    def test_v32_all_30_execute_gold_results_match_the_revised_contract(self):
        self.assertEqual(len(GOLD_BY_ID), 30)
        for case_id, case in BY_ID.items():
            if case["expected_behavior"] != "execute":
                continue
            gold = RESULT_BY_ID[case_id]
            compared = scorer_v31.compare_business_results(
                case,
                gold["rows"],
                {
                    "sql": gold["sql"], "columns": gold["columns"],
                    "rows": gold["rows"],
                },
                reference_sql=gold["sql"],
            )
            with self.subTest(case_id=case_id):
                self.assertEqual(compared["business_result_decision"], "PASS")
                self.assertEqual(compared["output_contract_decision"], "PASS")

    def test_v32_identical_resolved_projection_lineage_maps_an_unapproved_alias(self):
        case = {
            "id": "SYNTHETIC-LINEAGE", "expected_behavior": "execute",
            "output_contract": {"columns": ["customer_id", "revenue"], "ordered": False},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        reference_sql = (
            "SELECT o.customer_id AS customer_id, SUM(o.amount) AS revenue "
            "FROM commerce.sales AS o GROUP BY o.customer_id"
        )
        observation_sql = (
            "SELECT s.customer_id AS acct, SUM(s.amount) AS net "
            "FROM commerce.sales AS s GROUP BY s.customer_id"
        )
        compared = scorer_v31.compare_business_results(
            case,
            [{"customer_id": 7, "revenue": "12.50"}],
            {
                "sql": observation_sql,
                "columns": ["acct", "net"],
                "rows": [{"acct": 7, "net": "12.50"}],
            },
            reference_sql=reference_sql,
        )
        self.assertEqual(compared["business_result_decision"], "PASS")
        self.assertEqual(compared["canonical_column_mapping"], {
            "acct": "customer_id", "net": "revenue",
        })

    def test_v32_ambiguous_projection_lineage_requires_review_instead_of_fuzzy_pass(self):
        case = {
            "id": "SYNTHETIC-AMBIGUOUS", "expected_behavior": "execute",
            "output_contract": {"columns": ["left_value", "right_value"], "ordered": False},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        reference_sql = "SELECT t.value AS left_value, t.value AS right_value FROM t"
        observation_sql = "SELECT t.value AS mystery FROM t"
        compared = scorer_v31.compare_business_results(
            case,
            [{"left_value": 1, "right_value": 1}],
            {"sql": observation_sql, "columns": ["mystery"], "rows": [{"mystery": 1}]},
            reference_sql=reference_sql,
        )
        self.assertEqual(compared["business_result_decision"], "REVIEW_REQUIRED")
        self.assertIn(
            "ambiguous_sql_projection_lineage",
            compared["business_result_reason_codes"],
        )

    def test_v32_count_star_does_not_claim_projection_lineage_without_a_source_column(self):
        self.assertEqual(
            audit.projection_signatures("SELECT COUNT(*) AS count_a FROM commerce.orders"),
            [("count_a", None)],
        )

    def test_v32_extra_column_fails_output_contract_without_changing_business_accuracy(self):
        case = {
            "id": "SYNTHETIC-EXTRA", "expected_behavior": "execute",
            "output_contract": {"columns": ["value"], "ordered": False},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        compared = scorer_v31.compare_business_results(
            case, [{"value": 8}],
            {"columns": ["value", "trace_id"], "rows": [{"value": 8, "trace_id": "x"}]},
        )
        self.assertEqual(compared["business_result_decision"], "PASS")
        self.assertEqual(compared["output_contract_decision"], "FAIL")
        self.assertIn("unexpected_extra_columns", compared["output_contract_reason_codes"])

        approved = {
            **case,
            "allowed_provenance_columns": {"source_tag": "gold-reference"},
        }
        provenance = scorer_v31.compare_business_results(
            approved, [{"value": 8}],
            {"columns": ["value", "source_tag"], "rows": [{
                "value": 8, "source_tag": "gold-reference",
            }]},
        )
        self.assertEqual(provenance["business_result_decision"], "PASS")
        self.assertEqual(provenance["output_contract_decision"], "PASS")

    def test_v32_row_limits_are_output_contract_requirements(self):
        case = {
            "id": "SYNTHETIC-LIMIT", "expected_behavior": "execute", "top_n": 1,
            "output_contract": {"columns": ["value"], "ordered": False, "max_rows": 2},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        compared = scorer_v31.compare_business_results(
            case, [{"value": 1}],
            {"columns": ["value"], "rows": [{"value": 1}, {"value": 2}]},
        )
        self.assertEqual(compared["output_contract_decision"], "FAIL")
        self.assertIn("top_n_rows_exceeded", compared["output_contract_reason_codes"])

    def test_v32_multiset_matching_handles_overlapping_decimal_tolerances_and_duplicates(self):
        case = {
            "id": "SYNTHETIC-TOLERANCE", "expected_behavior": "execute",
            "output_contract": {"columns": ["metric"], "ordered": False},
            "column_aliases": {}, "numeric_tolerance": {"absolute": "0.10", "relative": 0},
        }
        compared = scorer_v31.compare_business_results(
            case,
            [{"metric": "10.0"}, {"metric": "10.1"}],
            {"columns": ["metric"], "rows": [{"metric": "10.05"}, {"metric": "9.95"}]},
        )
        self.assertEqual(compared["business_result_decision"], "PASS")
        self.assertEqual(compared["row_matching"]["matched_rows"], 2)

        duplicate_case = {**case, "numeric_tolerance": {"absolute": 0, "relative": 0}}
        duplicates = scorer_v31.compare_business_results(
            duplicate_case,
            [{"metric": "2.00"}, {"metric": "2.00"}],
            {"columns": ["metric"], "rows": [{"metric": "2"}, {"metric": "2"}]},
        )
        self.assertEqual(duplicates["business_result_decision"], "PASS")
        nulls = scorer_v31.compare_business_results(
            duplicate_case, [{"metric": None}],
            {"columns": ["metric"], "rows": [{"metric": None}]},
        )
        self.assertEqual(nulls["business_result_decision"], "PASS")
        null_vs_zero = scorer_v31.compare_business_results(
            duplicate_case, [{"metric": None}],
            {"columns": ["metric"], "rows": [{"metric": 0}]},
        )
        self.assertEqual(null_vs_zero["business_result_decision"], "FAIL")

    def test_v32_missing_and_extra_rows_fail_business_accuracy(self):
        case = {
            "id": "SYNTHETIC-ROWS", "expected_behavior": "execute",
            "output_contract": {"columns": ["value"], "ordered": False},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        expected = [{"value": 1}, {"value": 2}]
        missing = scorer_v31.compare_business_results(
            case, expected, {"columns": ["value"], "rows": [{"value": 1}]},
        )
        extra = scorer_v31.compare_business_results(
            case, expected, {"columns": ["value"], "rows": [{"value": 1}, {"value": 2}, {"value": 3}]},
        )
        self.assertEqual(missing["business_result_decision"], "FAIL")
        self.assertEqual(extra["business_result_decision"], "FAIL")

    def test_v32_ordered_rows_separate_content_accuracy_from_order_contract(self):
        case = {
            "id": "SYNTHETIC-ORDER", "expected_behavior": "execute",
            "output_contract": {"columns": ["id", "value"], "ordered": True},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        compared = scorer_v31.compare_business_results(
            case,
            [{"id": 1, "value": "a"}, {"id": 2, "value": "b"}],
            {"columns": ["value", "id"], "rows": [{"value": "b", "id": 2}, {"value": "a", "id": 1}]},
        )
        self.assertEqual(compared["business_result_decision"], "PASS")
        self.assertEqual(compared["output_contract_decision"], "FAIL")
        self.assertIn("ordered_output_mismatch", compared["output_contract_reason_codes"])

    def test_v32_business_key_duplicate_or_null_is_not_counted_as_correct(self):
        case = {
            "id": "SYNTHETIC-KEY", "expected_behavior": "execute",
            "business_key_columns": ["customer_id"],
            "output_contract": {"columns": ["customer_id", "orders"], "ordered": False},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        expected = [{"customer_id": 1, "orders": 2}, {"customer_id": 2, "orders": 1}]
        duplicate = scorer_v31.compare_business_results(
            case, expected,
            {"columns": ["customer_id", "orders"], "rows": [
                {"customer_id": 1, "orders": 2}, {"customer_id": 1, "orders": 1},
            ]},
        )
        null_key = scorer_v31.compare_business_results(
            case, expected,
            {"columns": ["customer_id", "orders"], "rows": [
                {"customer_id": None, "orders": 2}, {"customer_id": 2, "orders": 1},
            ]},
        )
        self.assertEqual(duplicate["business_result_decision"], "FAIL")
        self.assertEqual(null_key["business_result_decision"], "FAIL")

    def test_v32_missing_reference_rows_is_review_required_not_an_empty_gold_pass(self):
        case = {
            "id": "SYNTHETIC-NO-GOLD", "expected_behavior": "execute",
            "output_contract": {"columns": ["value"], "ordered": False},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        compared = scorer_v31.compare_business_results(
            case, None,
            {"columns": ["value"], "rows": []},
        )
        self.assertEqual(compared["business_result_decision"], "REVIEW_REQUIRED")
        self.assertIn("invalid_reference_row_shape", compared["business_result_reason_codes"])

    def test_v32_extra_output_changes_contract_metric_but_not_business_metric(self):
        case = {
            "id": "SYNTHETIC-METRICS", "expected_behavior": "execute",
            "output_contract": {"columns": ["value"], "ordered": False},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        observation = {
            "id": case["id"], "status": "executed", "sql_semantic_valid": True,
            "sql": "SELECT value, 'trace' AS trace_id FROM data", "parameters": [],
            "columns": ["value", "trace_id"], "rows": [{"value": 9, "trace_id": "trace"}],
        }
        reference_sql = "SELECT value FROM data"
        cases_doc = {"cases": [case]}
        record = audit.create_audit_record(
            case=case, case_set_sha256=digest(cases_doc), observation=observation,
            auditor_id="synthetic-reviewer", auditor_version="fixture-v1", decision="PASS",
            evidence=["Synthetic fixture: approved semantic audit decision."],
        )
        scores = scorer_v31.score(
            cases_doc,
            {"cases": [{"id": case["id"], "sql": reference_sql, "rows": [{"value": 9}]}]},
            {"cases": [observation], "independent_semantic_audits": [record]},
        )
        self.assertEqual(scores["metrics"]["business_result_accuracy"]["value"], 1.0)
        self.assertEqual(scores["metrics"]["output_contract_compliance"]["value"], 0.0)
        self.assertEqual(scores["metrics"]["supported_business_end_to_end_accuracy"]["value"], 0.0)

    def test_independent_audit_export_links_evidence_and_refuses_stale_or_incomplete_input(self):
        case = {
            "id": "SYNTHETIC-EXPORT", "expected_behavior": "execute",
            "output_contract": {"columns": ["value"], "ordered": False},
            "column_aliases": {}, "numeric_tolerance": {},
        }
        cases_doc = {"cases": [case]}
        observation = {
            "id": case["id"], "sql": "SELECT 4 AS value", "parameters": [4],
            "columns": ["value"], "rows": [{"value": 4}],
        }
        decisions_doc = {
            "format_version": audit.AUDIT_DECISIONS_FORMAT_VERSION,
            "case_set_sha256": digest(cases_doc),
            "auditor_id": "reviewer-test", "auditor_version": "manual-checklist-1",
            "decisions": [{
                "case_id": case["id"], "decision": "PASS",
                "evidence": ["Projection and result rows were independently checked."],
            }],
        }
        exported = audit.export_audit_records(
            cases_doc, {"cases": [observation]}, decisions_doc,
            recorded_at_utc="2026-11-21T00:00:00+00:00",
        )
        record = exported["independent_semantic_audits"][0]
        self.assertEqual(record["sql_sha256"], hashlib.sha256(observation["sql"].encode()).hexdigest())
        self.assertEqual(record["parameters_sha256"], audit.canonical_sha256([4]))
        self.assertEqual(record["case_contract_sha256"], audit.canonical_sha256(case))
        self.assertEqual(record["case_set_sha256"], digest(cases_doc))
        self.assertEqual(record["auditor_id"], "reviewer-test")
        self.assertEqual(exported["semantic_audit_export"]["authenticated"], False)
        self.assertEqual(exported["semantic_audit_export"]["unreviewed_observed_sql_case_ids"], [])

        stale = {**decisions_doc, "case_set_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "case-set hash"):
            audit.export_audit_records(cases_doc, {"cases": [observation]}, stale)
        incomplete = {**decisions_doc, "decisions": [{
            "case_id": case["id"], "decision": "PASS", "evidence": [],
        }]}
        with self.assertRaisesRegex(ValueError, "evidence"):
            audit.export_audit_records(cases_doc, {"cases": [observation]}, incomplete)
        duplicate = {**decisions_doc, "decisions": [
            decisions_doc["decisions"][0], decisions_doc["decisions"][0],
        ]}
        with self.assertRaisesRegex(ValueError, "unique case IDs"):
            audit.export_audit_records(cases_doc, {"cases": [observation]}, duplicate)

    def test_audit_export_cli_creates_new_file_and_never_overwrites_existing_evidence(self):
        case = {
            "id": "SYNTHETIC-CLI", "expected_behavior": "execute",
            "output_contract": {"columns": ["value"], "ordered": False},
        }
        cases_doc = {"cases": [case]}
        experiment_doc = {"cases": [{
            "id": case["id"], "sql": "SELECT 2 AS value", "parameters": [],
            "columns": ["value"], "rows": [{"value": 2}],
        }]}
        decisions_doc = {
            "format_version": audit.AUDIT_DECISIONS_FORMAT_VERSION,
            "case_set_sha256": digest(cases_doc),
            "auditor_id": "reviewer-cli", "auditor_version": "manual-1",
            "decisions": [{"case_id": case["id"], "decision": "PASS",
                           "evidence": ["Reviewed the synthetic SQL fixture."]}],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "--cases": root / "cases.json",
                "--experiment": root / "experiment.json",
                "--decisions": root / "decisions.json",
                "--output": root / "export.json",
            }
            paths["--cases"].write_text(json.dumps(cases_doc), encoding="utf-8")
            paths["--experiment"].write_text(json.dumps(experiment_doc), encoding="utf-8")
            paths["--decisions"].write_text(json.dumps(decisions_doc), encoding="utf-8")
            argv = ["semantic_audit_v3_1.py"]
            for flag, value in paths.items():
                argv.extend([flag, str(value)])
            with patch("sys.argv", argv):
                self.assertEqual(audit._export_cli(), 0)
            original = paths["--output"].read_bytes()
            with patch("sys.argv", argv), patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit) as raised:
                audit._export_cli()
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(paths["--output"].read_bytes(), original)

    def test_independent_fail_audits_keep_semantic_mutations_out_of_end_to_end_passes(self):
        mutations = {
            "aggregation": "SELECT COUNT(*) AS value FROM data",
            "grouping": "SELECT group_a, SUM(value) AS value FROM data GROUP BY group_a",
            "join": "SELECT a.value AS value FROM table_a AS a JOIN table_b AS b ON a.id = b.id",
            "snapshot": "SELECT quantity AS value FROM inventory WHERE snapshot_date = DATE '2026-01-01'",
            "null": "SELECT COALESCE(value, 0) AS value FROM data",
            "alias": "SELECT other_value AS value FROM data",
        }
        for mutation_name, sql in mutations.items():
            with self.subTest(mutation=mutation_name):
                case = {
                    "id": f"SYNTHETIC-{mutation_name.upper()}", "expected_behavior": "execute",
                    "output_contract": {"columns": ["value"], "ordered": False},
                    "column_aliases": {}, "numeric_tolerance": {},
                }
                cases_doc = {"cases": [case]}
                observation = {
                    "id": case["id"], "status": "executed", "sql_semantic_valid": True,
                    "sql": sql, "parameters": [], "columns": ["value"], "rows": [{"value": 1}],
                }
                record = audit.create_audit_record(
                    case=case, case_set_sha256=digest(cases_doc), observation=observation,
                    auditor_id="synthetic-reviewer", auditor_version="fixture-v1", decision="FAIL",
                    evidence=[f"Synthetic independent review: {mutation_name} changes the requested semantics."],
                )
                scores = scorer_v31.score(
                    cases_doc,
                    {"cases": [{"id": case["id"], "rows": [{"value": 1}]}]},
                    {"cases": [observation], "independent_semantic_audits": [record]},
                )
                self.assertEqual(scores["semantic_audits"][case["id"]]["decision"], "FAIL")
                self.assertEqual(scores["metrics"]["supported_business_end_to_end_accuracy"]["numerator"], 0)
                self.assertEqual(scores["metrics"]["business_result_accuracy"]["numerator"], 1)

    def test_all_v3_mutations_construct_against_v31_gold_definitions(self):
        gold_by_id = GOLD_BY_ID
        specs = mutation_runner._RUNNER.mutation_catalog()
        self.assertEqual(len(specs), 28)
        for spec in specs:
            with self.subTest(mutation=spec["id"]):
                variant = mutation_runner._RUNNER.construct_mutation(gold_by_id, spec)
                gold = gold_by_id[spec["case_id"]]
                self.assertTrue(variant["construction_verified"])
                self.assertTrue(
                    variant["sql"] != gold["sql"] or variant["parameters"] != gold["parameters"]
                )

    def test_synonym_alias_passes_business_match_but_not_strict_alias_diagnostic(self):
        row = RESULT_BY_ID["B40-004"]
        altered = [{"month": r["month"], "aov": r["average_order_value"]} for r in row["rows"]]
        compared = scorer.compare_business_results(
            BY_ID["B40-004"], row["rows"],
            {"columns": ["month", "aov"], "rows": altered},
        )
        self.assertTrue(compared["business_rows_match"])
        self.assertFalse(compared["strict_schema_match"])

    def test_wrong_values_and_missing_required_columns_fail(self):
        row = RESULT_BY_ID["B40-021"]
        incorrect = [dict(x) for x in row["rows"]]
        incorrect[0]["stockout_product_count"] = 97
        compared = scorer.compare_business_results(
            BY_ID["B40-021"], row["rows"], {"columns": row["columns"], "rows": incorrect},
        )
        self.assertFalse(compared["business_rows_match"])
        missing = scorer.compare_business_results(
            BY_ID["B40-021"], row["rows"],
            {"columns": ["category"], "rows": [{"category": r["category"]} for r in row["rows"]]},
        )
        self.assertFalse(missing["business_rows_match"])

    def test_old_gold_artifacts_preserved_for_independent_review(self):
        original_by_id = {x["id"]: x for x in ORIGINAL_GOLD["cases"]}
        for ident in set(GOLD_BY_ID) - {"B40-002", "B40-021", "B40-024"}:
            self.assertEqual(GOLD_BY_ID[ident]["sql"], original_by_id[ident]["sql"])
            self.assertEqual(GOLD_BY_ID[ident]["parameters"], original_by_id[ident]["parameters"])


    def test_archived_v3_checklist_provenance(self):
        # The v3 manifest identifies pre-review bytes, not the edited checklist.
        # The historical snapshot is stored in the v3.1 evidence directory.
        old_manifest = json.loads(
            (OLD / "FREEZE_MANIFEST.json").read_text(encoding="utf-8")
        )
        key = "artifacts/sql-agent-bussiness/40-case-v3/REVIEW_CHECKLIST.md"
        expected = old_manifest["artifact_hashes_excluding_this_manifest"][key]
        historical = HERE / "historical" / "REVIEW_CHECKLIST_at_v3_manifest.md"
        current = OLD / "REVIEW_CHECKLIST.md"
        actual_historical = hashlib.sha256(historical.read_bytes()).hexdigest()
        actual_current = hashlib.sha256(current.read_bytes()).hexdigest()
        self.assertEqual(actual_historical, expected)
        self.assertNotEqual(actual_current, expected)
        self.assertIn(
            "AI_ASSISTED_SEMANTIC_REVIEW_2026-11-21.md",
            current.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
