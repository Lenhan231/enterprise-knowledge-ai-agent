"""Embedding models for experiment 2, each used as its model card specifies (prefixes, prompts, normalization).

Evaluation-only: production keeps core.embeddings.EmbeddingService. Implements embed_query/embed_documents so
RetrievalService(embedding_service=...) can use it unchanged.

  python evaluation/v3/embedders.py <slug> <chunks.jsonl> <out.npy>   # embed the corpus on the GPU
"""
import json
import sys

import numpy as np

MODELS = {  # slug -> (model id, query prefix, passage prefix, sentence-transformers prompt_name for queries)
    "minilm": ("sentence-transformers/all-MiniLM-L6-v2", "", "", None),
    "mminilm": ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "", "", None),
    "e5base": ("intfloat/multilingual-e5-base", "query: ", "passage: ", None),
    "e5large-en": ("intfloat/e5-large-v2", "query: ", "passage: ", None),
    "bgem3": ("BAAI/bge-m3", "", "", None),
    "qwen3": ("Qwen/Qwen3-Embedding-0.6B", "", "", "query"),
}


class Embedder:
    def __init__(self, slug, device="cuda"):
        from sentence_transformers import SentenceTransformer
        self.model_name, self.query_prefix, self.passage_prefix, self.query_prompt = MODELS[slug]
        self.model = SentenceTransformer(self.model_name, device=device,
                                         model_kwargs={"torch_dtype": "float16"} if device == "cuda" else {})
        self.model.max_seq_length = min(512, self.model.max_seq_length or 512)  # production uses 512 tokens

    def embed_documents(self, texts):
        return self.model.encode([self.passage_prefix + t for t in texts], batch_size=16, normalize_embeddings=True,
                                 show_progress_bar=False).astype(np.float32).tolist()

    def embed_query(self, text):
        options = {"prompt_name": self.query_prompt} if self.query_prompt else {}
        return self.model.encode(self.query_prefix + text, normalize_embeddings=True, **options).astype(np.float32).tolist()


if __name__ == "__main__":
    slug, chunks_path, out_path = sys.argv[1:4]
    rows = [json.loads(line) for line in open(chunks_path, encoding="utf-8")]
    vectors = np.asarray(Embedder(slug).embed_documents([r["content"] for r in rows]), dtype=np.float32)
    np.save(out_path, vectors)
    print(slug, vectors.shape)
