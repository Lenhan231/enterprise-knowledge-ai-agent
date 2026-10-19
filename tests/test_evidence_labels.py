"""Source-grounded checks of revised alternatives, not model-score expectations."""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/retrieval"), str(ROOT / "src")]
from validate_vietstyle_evidence import validate
from core.evaluation.evidence_metrics import score_evidence
from rescore_vietstyle_evidence import check_character_coverage


class RevisedEvidenceLabelsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = ROOT / "artifacts/evaluation/vietstyle-bilingual-20261019"
        cls.old_raw = (folder / "evidence-v1/evidence.json").read_bytes()
        cls.old = json.loads(cls.old_raw)
        cls.data = json.loads((folder / "evidence-v2/evidence.json").read_text())
        cls.questions = {q["id"]: q for q in cls.data["intents"]}
        cls.sources = {}
        for language, meta in cls.data["sources"].items():
            rows = [json.loads(line) for line in (ROOT / meta["path"]).read_text().splitlines()]
            cls.sources[language] = {(r["document_id"],r.get("parser_chunk_index",r.get("chunk_index"))): r["content"] for r in rows}

    def requirement(self, rid):
        return next(c for c in self.questions[rid.split(".")[0]]["requirements"] if c["id"] == rid)

    def chunk(self, sid, only_span=False):
        span = self.data["spans"][sid]
        key = (span["document_id"],span["source_parser_index"])
        source = self.sources[span["language"]][key]
        a,b = (span["start_char"],span["end_char"]) if only_span else (0,len(source))
        return {"text": source[a:b], "metadata": {"document_id": key[0],"source_parser_index": key[1],
            "source_content_sha256": span["source_content_sha256"], "source_spans": [
                {"source_start":a,"source_end":b,"chunk_start":0,"chunk_end":b-a}]}}

    def score(self,qid,language,chunks):
        return score_evidence(self.data,qid,language,chunks,self.sources[language])

    def component(self,result,rid):
        return next(c for c in result["requirements"] if c["id"] == rid)

    def test_versions_sources_questions_and_unresolved_controls_are_preserved(self):
        self.assertEqual(hashlib.sha256(self.old_raw).hexdigest(),self.data["revision_provenance"]["previous_sha256"])
        self.assertEqual(validate(self.data)["required_status_counts"],{"ready":61,"needs_policy_resolution":2})
        self.assertEqual(self.old["sources"],self.data["sources"])
        old = {q["id"]:q for q in self.old["intents"]}
        for qid in ["Q13","Q14"]:
            self.assertEqual(old[qid],self.questions[qid])
        for qid,q in self.questions.items():
            self.assertEqual(q["question"],old[qid]["question"])
            self.assertEqual(q["reference_answer"],old[qid]["reference_answer"])

    def test_checklist_alternative_requires_sop_and_slide_in_both_languages(self):
        for language in ("vi","en"):
            for rid in ("Q11.block_checks","Q12.verify"):
                ids = self.requirement(rid)["evidence_by_language"][language]["alternatives"][-1]["all_of"]
                self.assertEqual(len(ids),2)
                pieces = [self.chunk(s,only_span=True) for s in ids]
                qid = rid.split(".")[0]
                for piece in pieces:
                    self.assertFalse(self.component(self.score(qid,language,[piece]),rid)["complete"])
                self.assertTrue(self.component(self.score(qid,language,pieces),rid)["complete"])

    def test_missing_data_still_required_and_approval_chain_not_replaced_by_generic_human_approval(self):
        for language in ("vi","en"):
            sid = self.requirement("Q18.missing_inputs")["evidence_by_language"][language]["alternatives"][1]["all_of"][0]
            self.assertFalse(self.score("Q18",language,[])["full_evidence_success"])
            self.assertTrue(self.score("Q18",language,[self.chunk(sid)])["full_evidence_success"])
            regular = self.requirement("Q20.human_approval")["evidence_by_language"][language]["alternatives"][-1]["all_of"][0]
            result = self.score("Q20",language,[self.chunk(regular,only_span=True)])
            self.assertTrue(self.component(result,"Q20.human_approval")["complete"])
            generic = self.requirement("Q20.no_write")["evidence_by_language"][language]["alternatives"][-1]["all_of"][0]
            result = self.score("Q20",language,[self.chunk(generic)])
            self.assertTrue(self.component(result,"Q20.no_write")["complete"])
            self.assertFalse(self.component(result,"Q20.human_approval")["complete"])
            self.assertFalse(result["full_evidence_success"])

    def test_independent_character_check_rejects_a_fabricated_complete_span(self):
        for language in ("vi","en"):
            sid = self.requirement("Q18.missing_inputs")["evidence_by_language"][language]["alternatives"][1]["all_of"][0]
            actual = self.score("Q18",language,[])
            check_character_coverage(self.data,self.sources[language],[],actual)
            bad = copy.deepcopy(actual)
            bad["span_coverage"][sid]["complete"] = True
            with self.assertRaises(ValueError):
                check_character_coverage(self.data,self.sources[language],[],bad)


if __name__ == "__main__":
    unittest.main()
