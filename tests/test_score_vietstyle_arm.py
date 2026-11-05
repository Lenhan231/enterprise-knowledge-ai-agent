import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("score_vietstyle_arm", ROOT / "scripts/agents/score_vietstyle_arm.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)

DOC = "VietStyle_Enterprise_Operating_Policy_v1.0_EN.pdf"


def ctx(page, cited=False, doc=DOC):
    return {"document_name": doc, "page_number": page, "cited": cited}


class ScoreVietstyleArmTest(unittest.TestCase):
    def test_key_points_numbers_alternatives_and_case(self):
        answer = "Khoản VND 50,000,001 cần Trưởng Bộ Phận duyệt trong 1 giờ."
        self.assertTrue(score.key_point_hit("50.000.001", answer))
        self.assertTrue(score.key_point_hit("một giờ|1 giờ", answer))
        self.assertTrue(score.key_point_hit("trưởng bộ phận", answer))
        self.assertFalse(score.key_point_hit("5", answer))  # a bare number must match a whole number
        self.assertFalse(score.key_point_hit("Hội đồng Điều hành Vận hành", answer))

    def test_retrieval_and_citation_use_physical_pages_and_vietstyle_only(self):
        case = {"evidence": [12, "PL-B"]}
        row = {"contexts": [ctx(99), ctx(14, cited=True), ctx(14), ctx(53, doc="other.pdf", cited=True), ctx(53)]}
        metrics = score.retrieval_metrics(case, row)
        self.assertEqual((metrics["recall@5"], metrics["full@5"], metrics["mrr"]), (1.0, True, 0.5))
        self.assertLess(metrics["ndcg@10"], 1.0)
        cited = score.citation_metrics(case, row)
        self.assertEqual((cited["citation_precision"], cited["citation_any_correct"]), (0.5, True))
        self.assertEqual(score.retrieval_metrics(case, {"contexts": [ctx(99)]})["full@5"], False)

    def test_refusals_rbac_leak_skips_and_no_citation(self):
        refusal = score.refusals()
        insufficient = next(text for text, kind in refusal.items() if kind == "insufficient")
        rbac = score.score_row({"id": "R01", "type": "rbac", "should_abstain": False, "must_include": [], "evidence": [18],
                                "role": "NO_ACCESS_ROLE"}, {"answer": insufficient, "contexts": [ctx(20)]}, refusal)
        self.assertEqual((rbac["refusal"], rbac["rbac_leak"]), ("insufficient", True))
        skipped = score.score_row({"id": "F01", "type": "follow_up", "should_abstain": False}, {"skipped": "x"}, refusal)
        self.assertEqual(skipped["status"], "x")
        chit = score.score_row({"id": "H01", "type": "chitchat", "should_abstain": False, "must_include": [], "evidence": [],
                                "expect_no_citations": True}, {"answer": "Chào bạn", "contexts": [ctx(5)]}, refusal)
        self.assertTrue(chit["no_citation_ok"])

    def test_policy_pages_follow_the_plus_two_convention(self):
        pages = score.policy_pages()
        self.assertIn("300.000 VND/người/bữa", pages[14])  # policy page 12
        self.assertIn("Ít nhất ba báo giá văn bản", pages[53])  # Phụ lục B
        self.assertIn("Phụ lục D", pages[54])
        self.assertIn("VSC-OPS-POL-001", pages[1])

    def test_compare_reports_mcnemar_on_discordant_pairs(self):
        judged = lambda ids, good: {"arm": "x", "rows": [{"id": i, "status": "ok", "judge": {"correctness":
                                                         "correct" if i in good else "incorrect"}} for i in ids]}
        ids = [f"C{i}" for i in range(10)]
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder, "a.json"), Path(folder, "b.json")
            a.write_text(json.dumps(judged(ids, ids[:2])))
            b.write_text(json.dumps(judged(ids, ids[:8])))
            with mock.patch("builtins.print") as printed:
                score.compare(type("Args", (), {"a": a, "b": b}))
        result = json.loads(printed.call_args[0][0])
        self.assertEqual((result["only_a_correct"], result["only_b_correct"]), (0, 6))
        self.assertAlmostEqual(result["mcnemar_exact_p"], 0.0312, places=3)
        self.assertGreater(result["b_minus_a_95ci"][0], 0)


    def test_export_and_external_verdicts_round_trip_only_for_the_same_answer(self):
        import hashlib
        sha = hashlib.sha256(score.QUESTIONS.read_bytes()).hexdigest()
        run = {"dataset_sha256": sha, "arm": "B9", "configuration": {}, "results": [
            {"id": "L01", "type": "lookup", "answer": "Mã VSC-OPS-POL-001 [S1].", "contexts": [ctx(1, cited=True)]},
            {"id": "C01", "type": "calculation", "answer": "1.200.000 VND [S1].", "contexts": [ctx(14, cited=True)]},
            {"id": "R01", "type": "rbac", "answer": "x", "contexts": []}]}
        with tempfile.TemporaryDirectory() as folder:
            path, prompts, verdicts = Path(folder, "B9.json"), Path(folder, "p.jsonl"), Path(folder, "v.jsonl")
            path.write_text(json.dumps(run))
            score.export(type("A", (), {"runs": [path], "output": prompts}))
            items = [json.loads(line) for line in prompts.read_text().splitlines()]
            self.assertEqual([i["id"] for i in items], ["L01", "C01"])  # RBAC is never sent to a judge
            self.assertIn("VSC-OPS-POL-001", items[0]["prompt"])
            verdict = {"correctness": "correct", "key_points_covered": [True], "abstained": False, "faithful": True, "reason": "ok"}
            verdicts.write_text("\n".join(json.dumps({**items[0], "verdict": verdict}) for _ in [0]) + "\n" +
                                json.dumps({**items[1], "answer_sha256": "stale", "verdict": verdict}) + "\n")
            with mock.patch("builtins.print"):
                score.score(type("A", (), {"run": path, "judge": False, "verdicts": verdicts, "judge_model": "codex"}))
            rows = {r["id"]: r for r in json.loads(Path(folder, "B9.scored.codex.json").read_text())["rows"]}
        self.assertEqual(rows["L01"]["judge"]["correctness"], "correct")
        self.assertEqual(rows["C01"]["judge_error"], "no verdict for this answer")


if __name__ == "__main__":
    unittest.main()
