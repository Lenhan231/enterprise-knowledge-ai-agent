import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.evaluation.evidence_metrics import score_evidence


class EvidenceMetricsTest(unittest.TestCase):
    def setUp(self):
        self.text = "Header: SKU | limit\nABC | 100 units"
        self.sources = {("DOC", 0): self.text, ("OTHER", 0): self.text, ("DOC", 1): self.text}
        self.start = self.text.index("ABC")
        self.hash = hashlib.sha256(self.text.encode()).hexdigest()
        self.evidence = {"sources": {"en": {}}, "spans": {}, "intents": []}
        for sid, a, b in [("whole", self.start, len(self.text)), ("left", self.start, self.start+3),
                          ("right", self.start+6, len(self.text))]:
            self.evidence["spans"][sid] = {"language": "en", "document_id": "DOC", "source_parser_index": 0,
                "source_content_sha256": self.hash, "start_char": a, "end_char": b, "quote": self.text[a:b]}
        self.requirement = {"id": "fact", "required": True, "status": "ready",
            "evidence_by_language": {"en": {"alternatives": [{"all_of": ["whole"]}]}}}
        self.evidence["intents"] = [{"id": "Q", "requirements": [self.requirement]}]

    def chunk(self, a, b, doc="DOC", parent=0):
        return {"text": self.text[a:b], "metadata": {"document_id": doc, "source_parser_index": parent,
            "source_content_sha256": self.hash,
            "source_spans": [{"source_start": a, "source_end": b, "chunk_start": 0, "chunk_end": b-a}]}}

    def score(self, chunks, k=10):
        return score_evidence(self.evidence, "Q", "en", chunks, self.sources, k)

    def test_split_evidence_requires_both_chunks(self):
        cut = self.start+7
        a, b = self.chunk(self.start, cut), self.chunk(cut, len(self.text))
        self.assertFalse(self.score([a])["full_evidence_success"])
        self.assertFalse(self.score([b])["full_evidence_success"])
        self.assertTrue(self.score([a,b])["full_evidence_success"])
        self.assertFalse(self.score([a,b], k=1)["full_evidence_success"])

    def test_overlap_and_duplicates_do_not_inflate_coverage(self):
        a = self.chunk(self.start, self.start+9)
        once, twice = self.score([a]), self.score([a,a])
        self.assertEqual(once["span_coverage"], twice["span_coverage"])
        self.assertFalse(twice["full_evidence_success"])
        self.assertTrue(self.score([a, self.chunk(self.start+3, len(self.text))])["full_evidence_success"])

    def test_header_wrong_document_or_parent_does_not_count(self):
        for chunk in [self.chunk(0,self.start), self.chunk(self.start,len(self.text),doc="OTHER"),
                      self.chunk(self.start,len(self.text),parent=1)]:
            self.assertEqual(self.score([chunk])["span_coverage"]["whole"]["fraction"], 0)
        # Repeated header + later body must retain the gap, not a bounding interval.
        a, b = self.chunk(0, self.start), self.chunk(len(self.text)-5,len(self.text))
        meta = copy.deepcopy(a["metadata"])
        tail = copy.deepcopy(b["metadata"]["source_spans"][0])
        tail["chunk_start"] += len(a["text"])
        tail["chunk_end"] += len(a["text"])
        meta["source_spans"].append(tail)
        self.assertFalse(self.score([{"text": a["text"]+b["text"], "metadata": meta}])["full_evidence_success"])

    def test_invalid_or_missing_provenance_raises_instead_of_scoring_a_miss(self):
        good = self.chunk(0,len(self.text))
        variants = [{"text": good["text"], "metadata": {}}, copy.deepcopy(good), copy.deepcopy(good), copy.deepcopy(good)]
        variants[1]["metadata"]["source_content_sha256"] = "old"
        variants[2]["text"] = "X"+good["text"][1:]
        variants[3]["metadata"]["source_spans"][0]["source_end"] += 1
        for bad in variants:
            with self.assertRaises(ValueError):
                self.score([bad])
        with self.assertRaises(ValueError):
            self.score([good], k=0)
        with self.assertRaises(ValueError):
            self.score([good], k=True)

    def test_and_bundle_and_or_alternatives_are_distinct(self):
        alternatives = self.requirement["evidence_by_language"]["en"]["alternatives"]
        alternatives[:] = [{"all_of": ["left", "right"]}]
        left, right = self.chunk(self.start,self.start+3), self.chunk(self.start+6,len(self.text))
        self.assertFalse(self.score([left])["full_evidence_success"])
        self.assertTrue(self.score([left,right])["full_evidence_success"])
        # Partial spans from two alternatives cannot be combined into a complete alternative.
        alternatives[:] = [{"all_of": ["whole"]}, {"all_of": ["right"]}]
        self.assertFalse(self.score([left, self.chunk(self.start+6,self.start+7)])["full_evidence_success"])
        self.assertTrue(self.score([right])["full_evidence_success"])

    def test_pending_and_optional_requirements_are_excluded(self):
        pending = {"id": "pending", "required": True, "status": "pending"}
        self.evidence["intents"][0]["requirements"].append(pending)
        result = self.score([self.chunk(self.start,len(self.text))])
        self.assertEqual(result["required_coverage"], 1)
        self.assertIsNone(result["full_evidence_success"])
        self.assertFalse(result["full_intent_eligible"])
        pending["required"] = False
        self.assertTrue(self.score([self.chunk(self.start,len(self.text))])["full_evidence_success"])
        optional = copy.deepcopy(self.requirement)
        optional.update(id="optional", required=False)
        self.evidence["intents"][0]["requirements"].append(optional)
        self.assertEqual(self.score([])["required_ready"], 1)

    def test_only_whitespace_gaps_may_be_ignored(self):
        space = self.text.index(" ", self.start)
        chunks = [self.chunk(self.start,space), self.chunk(space+1,len(self.text))]
        self.assertTrue(self.score(chunks)["full_evidence_success"])
        digit = self.text.index("100")
        self.assertFalse(self.score([self.chunk(self.start,digit),self.chunk(digit+1,len(self.text))])["full_evidence_success"])


if __name__ == "__main__":
    unittest.main()
