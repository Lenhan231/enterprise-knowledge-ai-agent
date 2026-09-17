# src/core/tokenization/token_counter.py
from transformers import AutoTokenizer

class TokenCounter:
    def __init__(self, model_name: str):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    def count(self, text: str) -> int:
        token_ids = self.tokenizer.encode(
            text,
            add_special_tokens=False
        )

        return len(token_ids)