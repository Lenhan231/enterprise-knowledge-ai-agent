import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.document_processing.chunking.router import split_ranges, split_text


class StructureAwareChunkingTest(unittest.TestCase):
    def test_sentence_strategy_keeps_sentences_together_and_observes_paragraphs(self):
        text = "First sentence. Second sentence.\n\nThird sentence. Fourth sentence."
        chunks = split_text(text, size=35, overlap=0, strategy="sentence")

        self.assertEqual(chunks, [
            "First sentence. Second sentence.",
            "Third sentence. Fourth sentence.",
        ])

    def test_sentence_strategy_keeps_content_before_trailing_newlines(self):
        text = "First sentence. Second sentence.\n"
        ranges = split_ranges(text, strategy="sentence")

        self.assertEqual([text[start:end].strip() for start, end in ranges], [
            "First sentence. Second sentence.",
        ])

    def test_fixed_strategy_retains_character_overlap(self):
        text = "one two three four five six seven eight"
        ranges = split_ranges(text, size=16, overlap=5, strategy="fixed")
        chunks = [text[start:end].strip() for start, end in ranges]

        self.assertGreaterEqual(len(chunks), 2)
        self.assertLessEqual(len(chunks[0]), 16)
        self.assertTrue(set(chunks[0].split()[-1:]) & set(chunks[1].split()[:2]))

    def test_long_sentence_falls_back_to_bounded_word_ranges(self):
        text = "word " * 30
        chunks = split_text(text.strip(), size=24, overlap=0, strategy="sentence")

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 24 for chunk in chunks))
        self.assertEqual(" ".join(chunks).split(), text.split())

    def test_invalid_chunking_strategy_fails_explicitly(self):
        with self.assertRaisesRegex(ValueError, "chunking strategy"):
            split_text("text", strategy="embedding_magic")


if __name__ == "__main__":
    unittest.main()
