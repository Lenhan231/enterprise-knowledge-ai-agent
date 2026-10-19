import copy
import hashlib
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/retrieval"),str(ROOT / "src")]
from evaluate_vietstyle_reranker import dense_candidates,rerank_candidates,check_pair_lengths,evidence_for


class RerankerBenchmarkTest(unittest.TestCase):
    def test_dense_candidates_enforce_acl_and_target_language_and_preserve_ties(self):
        rows=[{"language":"vi","allowed_roles":["staff"]},
              {"language":"vi","allowed_roles":["finance"]},
              {"language":"en","allowed_roles":["staff"]},
              {"language":"vi","allowed_roles":["staff"]}]
        vectors=np.array([[.8,.6],[1.,0.],[1.,0.],[.8,.6]])
        case={"target_language":"vi","allowed_roles":["staff"]}
        self.assertEqual(dense_candidates(rows,vectors,np.array([1.,0.]),case),[0,3])
        self.assertEqual(dense_candidates(rows,vectors,np.array([1.,0.]),dict(case,allowed_roles=["admin"])),[1,0,3])

    def test_score_sort_returns_only_candidates_and_ties_keep_dense_order(self):
        self.assertEqual(rerank_candidates([9,4,2],[.5,2.,2.],top_k=2),[4,2])
        for indices,scores in [([1,2],[.5]),([1,2],[np.nan,1]),([1,2],[np.inf,1]),
                               ([1,1],[1.,2.]),([],[]),([1,2],[[1.,2.]])]:
            with self.assertRaises(ValueError):
                rerank_candidates(indices,scores)
        with self.assertRaises(ValueError):
            rerank_candidates([1],[1.],top_k=0)

    def test_preflight_counts_whole_question_passage_pair_and_rejects_truncation(self):
        def tokenizer(questions,passages,**kwargs):
            self.assertFalse(kwargs["truncation"])
            return {"input_ids":[list(range(len(q)+len(p)+4)) for q,p in zip(questions,passages)]}
        pairs=[("AB","CDE")]
        self.assertEqual(check_pair_lengths(tokenizer,pairs,9),[9])
        with self.assertRaises(ValueError):
            check_pair_lengths(tokenizer,pairs,8)

    def test_rerank_can_promote_rank12_evidence_without_changing_text_or_vectors(self):
        rows,sources=[],{}
        for i in range(12):
            text="answer" if i==11 else "noise"
            digest=hashlib.sha256(text.encode()).hexdigest()
            sources["DOC",i]=text
            rows.append({"content":text,"metadata":{"document_id":"DOC","source_parser_index":i,
                "source_content_sha256":digest,"source_spans":[{"source_start":0,"source_end":len(text),
                                                                "chunk_start":0,"chunk_end":len(text)}]}})
        labels={"sources":{"vi":{}},"spans":{"s":{"language":"vi","document_id":"DOC","source_parser_index":11,
                "source_content_sha256":rows[11]["metadata"]["source_content_sha256"],"start_char":0,"end_char":6,"quote":"answer"}},
                "intents":[{"id":"Q","requirements":[{"id":"fact","required":True,"status":"ready",
                    "evidence_by_language":{"vi":{"alternatives":[{"all_of":["s"]}]}}}]}]}
        data={"rows":rows,"context":{"data":labels,"sources":{"vi":sources}}}
        original=copy.deepcopy(rows)
        case={"intent_id":"Q","target_language":"vi"}
        indices=list(range(12))
        self.assertFalse(evidence_for(data,case,indices[:10])["full_evidence_success"])
        chosen=rerank_candidates(indices,[0.]*11+[10.])
        self.assertEqual(chosen[0],11)
        self.assertEqual(len(chosen),10)
        self.assertTrue(evidence_for(data,case,chosen)["full_evidence_success"])
        self.assertEqual(rows,original)


if __name__ == "__main__":
    unittest.main()
