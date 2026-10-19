import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/retrieval"), str(ROOT / "src")]
from evaluate_neighbor_context import context_candidates, pack_context, render_context
from core.evaluation.evidence_metrics import score_evidence


def row(index, text="data", doc="DOC", language="vi", roles=None):
    return {"document_id":doc,"document_name":doc+".txt","language":language,"chunk_index":index,
            "content":text,"allowed_roles":["staff"] if roles is None else roles,"metadata":{}}


class NeighborContextTest(unittest.TestCase):
    def test_neighbors_are_same_document_language_authorized_and_exactly_adjacent(self):
        rows=[row(0,roles=["finance"]),row(1),row(2,doc="OTHER"),row(2,language="en"),row(3)]
        result=context_candidates(rows,[1],["staff"],"vi","neighbors")
        self.assertEqual([c["index"] for c in result],[1])
        with self.assertRaises(ValueError):
            context_candidates(rows,[0],["staff"],"vi","neighbors")
        # Missing chunk 2 does not make chunk 3 an immediate neighbor.
        self.assertNotIn(4,[c["index"] for c in result])

    def test_neighbor_dedup_preserves_seed_then_previous_then_next(self):
        rows=[row(0),row(1),row(2)]
        result=context_candidates(rows,[1,2],["staff"],"vi","neighbors")
        self.assertEqual([c["index"] for c in result],[1,0,2])
        self.assertEqual([c["reason"] for c in result],["seed","previous","next"])
        dense=context_candidates(rows,[1,2],["staff"],"vi","dense10")
        self.assertEqual([c["index"] for c in dense],[1,2])

    def test_budget_counts_citations_and_separators_skips_whole_oversized_chunks(self):
        rows=[row(0,"A"),row(1,"X"*200),row(2,"B")]
        candidates=[{"index":i} for i in range(3)]
        budget=len(render_context([rows[0],rows[2]]))
        selected,skipped,tokens=pack_context(rows,candidates,len,budget)
        self.assertEqual([c["index"] for c in selected],[0,2])
        self.assertEqual([c["index"] for c in skipped],[1])
        self.assertEqual(tokens,budget)
        self.assertEqual(rows[1]["content"],"X"*200)
        selected,_,tokens=pack_context(rows,candidates,len,1)
        self.assertEqual((selected,tokens),([],0))
        for invalid in (0,-1,True):
            with self.assertRaises(ValueError):
                pack_context(rows,candidates,len,invalid)

    def test_adjacent_chunks_supply_both_source_halves_without_reembedding(self):
        source="ABCD";digest=hashlib.sha256(source.encode()).hexdigest()
        rows=[row(0,"AB"),row(1,"CD")]
        for i,r in enumerate(rows):
            r["metadata"]={"document_id":"DOC","source_parser_index":0,"source_content_sha256":digest,
                "source_spans":[{"source_start":i*2,"source_end":i*2+2,"chunk_start":0,"chunk_end":2}]}
        labels={"sources":{"vi":{}},"spans":{"s":{"language":"vi","document_id":"DOC","source_parser_index":0,
            "source_content_sha256":digest,"start_char":0,"end_char":4,"quote":source}},
            "intents":[{"id":"Q","requirements":[{"id":"fact","status":"ready","required":True,
                "evidence_by_language":{"vi":{"alternatives":[{"all_of":["s"]}]}}}]}]}
        def score(selected):
            chunks=[{"text":rows[c["index"]]["content"],"metadata":rows[c["index"]]["metadata"]} for c in selected]
            return score_evidence(labels,"Q","vi",chunks,{("DOC",0):source},k=max(1,len(chunks)))
        dense=context_candidates(rows,[1],["staff"],"vi","dense10")
        expanded=context_candidates(rows,[1],["staff"],"vi","neighbors")
        self.assertFalse(score(dense)["full_evidence_success"])
        selected,_,_=pack_context(rows,expanded,len,1000)
        self.assertTrue(score(selected)["full_evidence_success"])


if __name__ == "__main__":
    unittest.main()
