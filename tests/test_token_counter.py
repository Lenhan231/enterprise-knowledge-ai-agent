import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.utils.token_counter import TokenCounter


class _CharacterTokenizer:
    def num_special_tokens_to_add(self, pair=False):
        return 2

    def __call__(self, text, **kwargs):
        return {"offset_mapping": [(index, index + 1) for index in range(len(text))]}

    def encode(self, text, add_special_tokens=False):
        return list(text)


class TokenCounterTest(unittest.TestCase):
    def test_splits_at_token_limit_and_preserves_overlap(self):
        counter = TokenCounter.__new__(TokenCounter)
        counter.tokenizer = _CharacterTokenizer()

        chunks = counter.split_text("abcdefghijklmnop", max_sequence_tokens=7, overlap_tokens=1)

        self.assertTrue(all(counter.count(chunk) <= 5 for chunk in chunks))
        reconstructed = chunks[0] + "".join(chunk[1:] for chunk in chunks[1:])
        self.assertEqual(reconstructed, "abcdefghijklmnop")

    def test_short_text_is_returned_unchanged(self):
        counter = TokenCounter.__new__(TokenCounter)
        counter.tokenizer = _CharacterTokenizer()

        self.assertEqual(counter.split_text("abc", max_sequence_tokens=7, overlap_tokens=1), ["abc"])


if __name__ == "__main__":
    unittest.main()
