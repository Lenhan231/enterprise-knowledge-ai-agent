# src/core/tokenization/token_counter.py
from transformers import AutoTokenizer
from core.embeddings.settings import E5_MODEL, E5_REVISION


class TokenCounter:
    def __init__(self, model_name: str):
        options = {"revision": E5_REVISION} if model_name == E5_MODEL else {}
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True, **options)

    def count(self, text: str) -> int:
        token_ids = self.tokenizer.encode(
            text,
            add_special_tokens=False
        )

        return len(token_ids)

    def split_text(
        self,
        text: str,
        max_sequence_tokens: int,
        overlap_tokens: int = 32,
    ) -> list[str]:
        """Return text only; keep the existing caller interface."""
        return [part for part, _, _ in self.split_text_with_offsets(
            text, max_sequence_tokens, overlap_tokens,
        )]

    def split_text_with_offsets(
        self,
        text: str,
        max_sequence_tokens: int,
        overlap_tokens: int = 32,
    ) -> list[tuple[str, int, int]]:
        """Return unchanged slices with Unicode [start, end) source coordinates."""
        if max_sequence_tokens <= 0:
            raise ValueError("Maximum sequence length must be positive")

        special_tokens = self.tokenizer.num_special_tokens_to_add(pair=False)
        content_limit = max_sequence_tokens - special_tokens
        if content_limit <= 0:
            raise ValueError("Maximum sequence length leaves no room for content")
        if overlap_tokens < 0 or overlap_tokens >= content_limit:
            raise ValueError("Token overlap must be non-negative and below the content limit")

        encoded = self.tokenizer(
            text,
            add_special_tokens=False,
            return_offsets_mapping=True,
            truncation=False,
            verbose=False,
        )
        offsets = encoded["offset_mapping"]
        if len(offsets) <= content_limit:
            return [(text, 0, len(text))]

        chunks = []
        token_start = 0
        previous_char_end = 0
        while token_start < len(offsets):
            token_end = min(token_start + content_limit, len(offsets))
            char_start = 0 if token_start == 0 else offsets[token_start][0]
            if overlap_tokens == 0 and token_start:
                char_start = previous_char_end
            char_end = offsets[token_end - 1][1]
            chunk = text[char_start:char_end]

            while self.count(chunk) > content_limit and token_end > token_start + 1:
                token_end -= 1
                char_end = offsets[token_end - 1][1]
                chunk = text[char_start:char_end]
            if self.count(chunk) > content_limit:
                raise ValueError("Tokenizer could not split text within the configured sequence length")

            chunks.append((chunk, char_start, char_end))
            previous_char_end = char_end
            if token_end == len(offsets):
                break
            token_start = max(token_start + 1, token_end - overlap_tokens)

        return chunks
