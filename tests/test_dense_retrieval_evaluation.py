import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from scripts.check_apple_retrieval import (  # noqa: E402
    TOP_K,
    build_artifact,
    evaluate_cases,
    evaluate_response,
    result_provenance,
    validate_cases,
    validate_response,
)
from core.retrieval.retrieval import (  # noqa: E402
    RankedChunk,
    RetrievalResponse,
    SourceLocation,
    make_chunk_id,
)


def chunk(
    document_id: str,
    rank: int,
    score: float,
    *,
    chunk_index: int | None = None,
    page_number: int | None = 1,
    section_title: str | None = "Section",
    official_url: str | None = "https://example.com/document.pdf",
) -> RankedChunk:
    index = rank - 1 if chunk_index is None else chunk_index
    return RankedChunk(
        rank=rank,
        chunk_id=make_chunk_id(document_id, index),
        document_id=document_id,
        text=f"Full text for {document_id}",
        score=score,
        source=f"{document_id.lower()}.pdf",
        location=SourceLocation(
            chunk_index=index,
            page_number=page_number,
            section_title=section_title,
        ),
        metadata={"document_id": document_id, "official_url": official_url},
    )


def response(query: str, results: list[RankedChunk], latency: float = 10) -> RetrievalResponse:
    return RetrievalResponse(query=query, latency_ms=latency, results=results)


class FakeRetrieval:
    def __init__(self, responses: dict[str, RetrievalResponse]):
        self.responses = responses
        self.requests = []

    def retrieve(self, request):
        self.requests.append(request)
        return self.responses[request.query]


class DenseRetrievalEvaluationTest(unittest.TestCase):
    def test_one_expected_document_found_and_not_found(self):
        found = evaluate_response(response("found", [chunk("DOC-A", 1, 0.9)]), ["DOC-A"])
        missed = evaluate_response(response("missed", [chunk("DOC-B", 1, 0.9)]), ["DOC-A"])

        self.assertEqual(found["hit"], {1: 1, 3: 1, 5: 1})
        self.assertEqual(found["recall"], {1: 1.0, 3: 1.0, 5: 1.0})
        self.assertEqual(missed["hit"], {1: 0, 3: 0, 5: 0})
        self.assertEqual(missed["recall"], {1: 0.0, 3: 0.0, 5: 0.0})

    def test_multiple_expected_documents_distinguish_hit_from_recall(self):
        result = evaluate_response(
            response("question", [
                chunk("DOC-A", 1, 0.9),
                chunk("DOC-A", 2, 0.8),
                chunk("DOC-B", 3, 0.7),
            ]),
            ["DOC-A", "DOC-B"],
        )

        self.assertEqual(result["hit"], {1: 1, 3: 1, 5: 1})
        self.assertEqual(result["recall"], {1: 0.5, 3: 1.0, 5: 1.0})
        self.assertLessEqual(max(result["recall"].values()), 1.0)

    def test_invalid_fixture_questions_and_expected_documents_are_rejected(self):
        for payload in (
            [],
            [{"question": " ", "expected_document_ids": ["DOC"]}],
            [{"question": "question", "expected_document_ids": []}],
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    validate_cases(payload)

    def test_macro_aggregate_and_request_level_latency(self):
        cases = [
            {"question": "one", "expected_document_ids": ["DOC-A"]},
            {"question": "two", "expected_document_ids": ["DOC-B", "DOC-C"]},
        ]
        retrieval = FakeRetrieval({
            "one": response("one", [chunk("DOC-A", 1, 0.9)], 10),
            "two": response("two", [chunk("DOC-B", 1, 0.8)], 30),
        })

        rows, summary = evaluate_cases(retrieval, cases)

        self.assertEqual(len(retrieval.requests), 2)
        self.assertTrue(all(request.top_k == TOP_K for request in retrieval.requests))
        self.assertEqual([row["latency_ms"] for row in rows], [10, 30])
        self.assertEqual(summary["recall"][1], 0.75)
        self.assertEqual(summary["mean_latency_ms"], 20)
        self.assertEqual(summary["median_latency_ms"], 20)

    def test_invalid_rank_and_score_order_are_detected(self):
        bad_rank = response("rank", [chunk("DOC-A", 1, 0.9), chunk("DOC-B", 3, 0.8)])
        bad_score = response("score", [chunk("DOC-A", 1, 0.8), chunk("DOC-B", 2, 0.9)])

        with self.assertRaisesRegex(ValueError, "ranks"):
            validate_response(bad_rank)
        with self.assertRaisesRegex(ValueError, "scores"):
            validate_response(bad_score)

    def test_top_k_limit_is_enforced(self):
        results = [chunk(f"DOC-{rank}", rank, 1 - rank / 10) for rank in range(1, 7)]
        with self.assertRaisesRegex(ValueError, "top_k"):
            validate_response(response("question", results))

    def test_provenance_preserves_identity_full_text_and_optional_nulls(self):
        first = chunk(
            "DOC-A", 1, 0.9, chunk_index=7,
            page_number=None, section_title=None, official_url=None,
        )
        mapped = result_provenance(first)

        self.assertEqual(mapped["chunk_id"], "DOC-A::chunk::7")
        self.assertEqual(mapped["rank"], 1)
        self.assertEqual(mapped["document_id"], "DOC-A")
        self.assertEqual(mapped["chunk_index"], 7)
        self.assertEqual(mapped["source_document"], "doc-a.pdf")
        self.assertEqual(mapped["content"], first.text)
        self.assertEqual(mapped["similarity_score"], 0.9)
        self.assertIsNone(mapped["page_number"])
        self.assertIsNone(mapped["section_title"])
        self.assertIsNone(mapped["official_url"])
        self.assertNotIn("citation_id", mapped)

    def test_rank_one_is_request_local_not_a_persistent_identity(self):
        one = result_provenance(chunk("DOC-A", 1, 0.9))
        two = result_provenance(chunk("DOC-B", 1, 0.8))

        self.assertNotEqual(one["chunk_id"], two["chunk_id"])
        self.assertNotEqual(one["document_id"], two["document_id"])
        self.assertNotIn("S1", one.values())
        self.assertNotIn("S1", two.values())

    def test_artifact_contains_reproducible_run_metadata(self):
        rows = [evaluate_response(
            response("question", [chunk("DOC-A", 1, 0.9)], 12), ["DOC-A"]
        )]
        summary = {
            "queries": 1,
            "hit": {1: 1, 3: 1, 5: 1},
            "recall": {1: 1.0, 3: 1.0, 5: 1.0},
            "mean_latency_ms": 12,
            "median_latency_ms": 12,
        }

        fixture = REPO_ROOT / "tests/fixtures/custom_cases.json"
        artifact = build_artifact(rows, summary, "test-model", fixture)

        self.assertEqual(artifact["embedding_model"], "test-model")
        self.assertEqual(artifact["top_k"], TOP_K)
        self.assertEqual(artifact["fixture"], "tests/fixtures/custom_cases.json")
        self.assertEqual(artifact["summary"]["hit_at_1"], 1)
        self.assertEqual(artifact["summary"]["recall_at_5"], 1.0)
        self.assertEqual(artifact["results"][0]["results"][0]["rank"], 1)


if __name__ == "__main__":
    unittest.main()
