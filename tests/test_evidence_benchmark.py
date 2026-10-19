import copy
import hashlib
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "scripts/retrieval"),
                str(Path(__file__).resolve().parents[1] / "src")]
from evaluate_embedding_candidates import score_case, summarize_evidence


class EvidenceBenchmarkTest(unittest.TestCase):
    def setUp(self):
        self.text = "limit 100"
        digest = hashlib.sha256(self.text.encode()).hexdigest()
        self.data = {"sources": {"en": {}}, "spans": {"s": {"language": "en", "document_id": "EN",
            "source_parser_index": 0, "source_content_sha256": digest,
            "start_char": 0, "end_char": len(self.text), "quote": self.text}},
            "intents": [{"id": "Q", "requirements": [{"id": "fact", "status": "ready", "required": True,
                "evidence_by_language": {"en": {"alternatives": [{"all_of": ["s"]}]}}}]}]}
        self.row = {"document_id": "EN", "document_name": "policy.txt", "language": "en", "chunk_index": 0,
            "content": self.text, "allowed_roles": ["staff"], "metadata": {"document_id": "EN",
                "source_parser_index": 0, "source_content_sha256": digest,
                "source_spans": [{"source_start": 0, "source_end": len(self.text), "chunk_start": 0,
                                  "chunk_end": len(self.text)}]}}
        self.case = {"id": "Q-vi-to-en", "intent_id": "Q", "question": "query", "query_language": "vi",
            "target_language": "en", "direction": "vi->en", "allowed_roles": ["admin"],
            "expected_sources": ["policy.txt"], "unavailable_expected_sources": []}
        self.context = {"data": self.data, "sources": {"en": {("EN",0): self.text}}}

    def test_language_scope_and_actual_dense_top_ten_precede_evidence_scoring(self):
        distractors = [dict(self.row, document_id="OTHER", chunk_index=i,
                            metadata=dict(self.row["metadata"], document_id="OTHER")) for i in range(10)]
        wrong_language = dict(self.row, document_id="VI", language="vi")
        self.context["sources"]["en"]["OTHER",0] = self.text
        rows = [wrong_language] + distractors + [self.row]
        vectors = np.array([[1.,0.]] + [[.8,.6]]*10 + [[0.,1.]])
        result = score_case(rows,vectors,np.array([1.,0.]),self.case,self.context)
        self.assertEqual(len(result["ranked_chunk_ids"]),10)
        self.assertTrue(all(s.startswith("OTHER::") for s in result["ranked_chunk_ids"]))
        self.assertFalse(result["evidence"]["full_evidence_success"])
        result = score_case(rows,vectors,np.array([0.,1.]),self.case,self.context)
        self.assertTrue(result["evidence"]["full_evidence_success"])
        self.assertTrue(result["ranked_chunk_ids"][0].startswith("EN::"))

    def test_acl_and_stable_ties_are_preserved(self):
        rows = [dict(self.row,chunk_index=3),dict(self.row,chunk_index=1)]
        result = score_case(rows,np.array([[1.,0.],[1.,0.]]),np.array([1.,0.]),self.case,self.context)
        self.assertEqual(result["ranked_chunk_ids"],["EN::chunk::3","EN::chunk::1"])
        case = dict(self.case,allowed_roles=["finance"])
        with self.assertRaises(ValueError):
            score_case(rows,np.array([[1.,0.],[1.,0.]]),np.array([1.,0.]),case,self.context)

    def test_legacy_source_only_mode_needs_no_provenance_or_language(self):
        case = dict(self.case)
        del case["target_language"]
        row = dict(self.row)
        del row["metadata"]
        del row["language"]
        result = score_case([row],np.array([[1.,0.]]),np.array([1.,0.]),case)
        self.assertEqual(result["source_recall_at_10"],1)
        self.assertNotIn("evidence",result)

    def test_pending_case_is_excluded_only_from_full_intent_denominator(self):
        result = score_case([self.row],np.array([[1.,0.]]),np.array([1.,0.]),self.case,self.context)
        pending = copy.deepcopy(result)
        pending["evidence"].update(intent_id="Q14",full_intent_eligible=False,full_evidence_success=None)
        summary = summarize_evidence([result,pending])["vi->en"]
        self.assertEqual(summary["required_ready_components"],2)
        self.assertEqual(summary["required_met_components"],2)
        self.assertEqual(summary["full_intent_eligible_cases"],1)
        self.assertEqual(summary["full_evidence_success_rate_at_10"],1)
        self.assertEqual(summary["excluded_full_intent_ids"],["Q14"])


if __name__ == "__main__":
    unittest.main()
