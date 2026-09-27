import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qa_human_review import import_reviews, prepare_review  # noqa: E402


def write_run(path: Path, model: str, context_hash: str = "same-context"):
    path.write_text(json.dumps({
        "llm_model": model,
        "results": [{
            "id": "case-a",
            "question": "What happened?",
            "answer": "A source-backed response.",
            "context_sha256": context_hash,
            "sources": [{"source_id": "S1", "page_number": 2, "content_preview": "Source evidence."}],
            "human_reviews": [],
        }],
    }), encoding="utf-8")


def fill_packet(path: Path, reviewer: str, hallucinated: int = 0, factual: int = 2):
    packet = json.loads(path.read_text(encoding="utf-8"))
    for row in packet["responses"]:
        row["review"] = {
            "reviewer": reviewer,
            "faithfulness": 4,
            "answer_relevancy": 5,
            "context_precision": 3,
            "hallucinated_claim_count": hallucinated,
            "factual_claim_count": factual,
            "notes": "Checked against evidence.",
        }
    path.write_text(json.dumps(packet), encoding="utf-8")


class BlindQAReviewTest(unittest.TestCase):
    def test_blinded_packets_hide_model_labels_and_import_multiple_reviewers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_a, run_b = root / "a.json", root / "b.json"
            write_run(run_a, "model-secret-a")
            write_run(run_b, "model-secret-b")
            packet_a, packet_b, key = root / "review-a.json", root / "review-b.json", root / "private-key.json"
            prepare_review([run_a, run_b], packet_a, key, seed=7)
            self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
            packet_text = packet_a.read_text(encoding="utf-8")
            self.assertNotIn("model-secret-a", packet_text)
            self.assertNotIn("model-secret-b", packet_text)
            self.assertEqual(len(json.loads(packet_a.read_text())["responses"]), 2)

            packet_b.write_text(packet_text, encoding="utf-8")
            fill_packet(packet_a, "reviewer-1", hallucinated=1)
            fill_packet(packet_b, "reviewer-2", hallucinated=0)
            output_dir = root / "scored"
            import_reviews([packet_a, packet_b], key, output_dir)

            scored = json.loads((output_dir / "a.json").read_text(encoding="utf-8"))
            self.assertEqual(len(scored["results"][0]["human_reviews"]), 2)
            summary = scored["generation_metric_summary"]["human_review"]
            self.assertEqual(summary["reviewer_count"], 2)
            self.assertEqual(summary["mean_faithfulness"], 4.0)
            self.assertEqual(summary["hallucination_rate"], 0.25)

    def test_prepare_rejects_model_runs_with_different_contexts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_a, run_b = root / "a.json", root / "b.json"
            write_run(run_a, "model-a")
            write_run(run_b, "model-b", context_hash="different")
            with self.assertRaisesRegex(ValueError, "contexts differ"):
                prepare_review([run_a, run_b], root / "packet.json", root / "key.json")
            self.assertFalse((root / "packet.json").exists())

    def test_import_rejects_invalid_rating_before_writing_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_a, run_b = root / "a.json", root / "b.json"
            write_run(run_a, "model-a")
            write_run(run_b, "model-b")
            packet, key = root / "packet.json", root / "key.json"
            prepare_review([run_a, run_b], packet, key, seed=1)
            fill_packet(packet, "reviewer-1")
            data = json.loads(packet.read_text(encoding="utf-8"))
            data["responses"][0]["review"]["faithfulness"] = 6
            packet.write_text(json.dumps(data), encoding="utf-8")

            output_dir = root / "scored"
            with self.assertRaisesRegex(ValueError, "1 to 5"):
                import_reviews([packet], key, output_dir)
            self.assertFalse(output_dir.exists())


if __name__ == "__main__":
    unittest.main()
