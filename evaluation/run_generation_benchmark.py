

from core.llm.models import BENCHMARK_MODELS
from core.llm.providers import GroqProvider


for model in BENCHMARK_MODELS:
    llm = GroqProvider(model=model)

    for sample in dataset:
        contexts = cached_contexts[sample["id"]]

        start = perf_counter()

        result = rag.generate_from_contexts(
            question=sample["question"],
            contexts=contexts,
            llm=llm,
        )

        latency_ms = (perf_counter() - start) * 1000

        save_result(...)