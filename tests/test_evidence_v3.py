"""Targeted duplicate-source correction must not relax other evidence requirements."""
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"),str(ROOT / "scripts/retrieval")]
from core.evaluation.evidence_metrics import score_evidence
from validate_vietstyle_evidence import validate


class TransactionEvidenceFixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = ROOT / "artifacts/evaluation/vietstyle-bilingual-20261019"
        cls.old_raw = (folder / "evidence-v2/evidence.json").read_bytes()
        cls.old = json.loads(cls.old_raw)
        cls.new = json.loads((folder / "evidence-v3/evidence.json").read_text())
        cls.sources = {}
        for language, meta in cls.new["sources"].items():
            rows = [json.loads(line) for line in (ROOT / meta["path"]).read_text().splitlines()]
            cls.sources[language] = {(r["document_id"],r.get("parser_chunk_index",r.get("chunk_index"))):r["content"] for r in rows}

    def test_only_q15_transaction_alternative_changes_and_english_already_covered(self):
        self.assertEqual(self.new["revision_provenance"]["previous_sha256"],hashlib.sha256(self.old_raw).hexdigest())
        self.assertEqual(validate(self.new)["required_status_counts"],{"ready":61,"needs_policy_resolution":2})
        for field in ("sources","question_sources","translation_provenance","rules"):
            self.assertEqual(self.old[field],self.new[field])
        self.assertEqual(len(self.new["spans"]),len(self.old["spans"])+1)
        for sid,span in self.old["spans"].items():
            self.assertEqual(span,self.new["spans"][sid])
        for old,new in zip(self.old["intents"],self.new["intents"]):
            if old["id"] != "Q15":
                self.assertEqual(old,new)
                continue
            for field in ("id","question","reference_answer","notes","full_intent_ready"):
                self.assertEqual(old[field],new[field])
            for before,after in zip(old["requirements"],new["requirements"]):
                if before["id"] != "Q15.transaction_id":
                    self.assertEqual(before,after)
                else:
                    self.assertTrue(after["required"])
                    self.assertEqual(before["status"],after["status"])
                    self.assertEqual(before["evidence_by_language"]["en"],after["evidence_by_language"]["en"])
                    self.assertEqual(after["evidence_by_language"]["vi"]["alternatives"][:-1],before["evidence_by_language"]["vi"]["alternatives"])

    def test_prose_duplicate_counts_but_field_name_alone_and_missing_history_do_not(self):
        question = next(q for q in self.new["intents"] if q["id"] == "Q15")
        req = next(c for c in question["requirements"] if c["id"] == "Q15.transaction_id")
        for language in ("vi","en"):
            sid = req["evidence_by_language"][language]["alternatives"][-1]["all_of"][0]
            span = self.new["spans"][sid]
            a,b = span["start_char"],span["end_char"]
            source = self.sources[language][span["document_id"],span["source_parser_index"]]
            def piece(end):
                return {"text":source[a:end],"metadata":{"document_id":span["document_id"],
                    "source_parser_index":span["source_parser_index"],"source_content_sha256":span["source_content_sha256"],
                    "source_spans":[{"source_start":a,"source_end":end,"chunk_start":0,"chunk_end":end-a}]}}
            result = score_evidence(self.new,"Q15",language,[piece(b)],self.sources[language])
            requirements = {c["id"]:c for c in result["requirements"]}
            self.assertTrue(requirements["Q15.transaction_id"]["complete"])
            self.assertFalse(requirements["Q15.history"]["complete"])
            self.assertFalse(result["full_evidence_success"])
            incomplete = score_evidence(self.new,"Q15",language,[piece(a+len("Adjustment Transaction ID"))],self.sources[language])
            self.assertFalse(next(c for c in incomplete["requirements"] if c["id"] == "Q15.transaction_id")["complete"])
            old = score_evidence(self.old,"Q15",language,[piece(b)],self.sources[language])
            self.assertEqual(next(c for c in old["requirements"] if c["id"] == "Q15.transaction_id")["complete"],language == "en")


if __name__ == "__main__":
    unittest.main()
