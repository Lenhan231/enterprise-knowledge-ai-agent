"""Build the shared Ragas metrics and judge client for benchmark runs."""

from __future__ import annotations

import os

from openai import AsyncOpenAI
from ragas.embeddings.base import embedding_factory
from ragas.llms import llm_factory
from ragas.metrics.collections import AnswerRelevancy, ContextPrecision, Faithfulness

DEFAULT_RAGAS_MODEL = "openai/gpt-oss-20b"
GROQ_OPENAI_BASE_URL = "https://api.groq.com/openai/v1"


def build_ragas_metrics(*, environ=None):
    environ = os.environ if environ is None else environ
    api_key = environ.get("GROQ_API_KEY_RAGAS")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY_RAGAS is required for Ragas judge models")
    client = AsyncOpenAI(api_key=api_key, base_url=GROQ_OPENAI_BASE_URL, timeout=60)
    judge = llm_factory(environ.get("RAGAS_JUDGE_MODEL", DEFAULT_RAGAS_MODEL), client=client)
    embeddings = embedding_factory(
        "huggingface",
        model=environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-base"),
    )
    return {
        "faithfulness": Faithfulness(llm=judge),
        "answer_relevancy": AnswerRelevancy(llm=judge, embeddings=embeddings),
        "context_precision": ContextPrecision(llm=judge),
    }
