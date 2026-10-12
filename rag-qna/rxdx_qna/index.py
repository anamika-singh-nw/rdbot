"""Hybrid retrieval: BM25 for exact terms, dense embeddings for meaning, fused by rank.

Neither half is enough alone on this corpus:

- Dense retrieval maps "skin doctor" to dermatology but blurs proper nouns — "Dr Vikram A G"
  and "Dr Vikram Shetty" embed almost identically.
- BM25 nails names, council numbers and clinic names but knows nothing of synonyms.

Reciprocal-rank fusion combines the two rankings without having to calibrate a BM25 score
against a cosine similarity.

At ~650 chunks a numpy matrix *is* the vector store: a full scan is well under a
millisecond, so there is nothing for a vector database to speed up.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from .chunking import Chunk, build_chunks, load_records

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
# bge models retrieve better when the *query* (not the passage) carries this instruction.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
RRF_K = 60

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT.parent / "data" / "rxdx.json"  # shared by every project in the repo
INDEX_DIR = ROOT / "index"

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _embedder():
    from fastembed import TextEmbedding  # deferred: loading ONNX costs ~1s

    return TextEmbedding(EMBED_MODEL)


def build_index(data_path: Path = DATA_PATH, index_dir: Path = INDEX_DIR) -> int:
    chunks = build_chunks(load_records(data_path))
    vectors = np.array(list(_embedder().embed([c.text for c in chunks])), dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    index_dir.mkdir(parents=True, exist_ok=True)
    np.save(index_dir / "vectors.npy", vectors)
    (index_dir / "chunks.json").write_text(json.dumps([c.to_dict() for c in chunks], ensure_ascii=False))
    return len(chunks)


@dataclass
class Hit:
    chunk: Chunk
    score: float


class Retriever:
    def __init__(self, index_dir: Path = INDEX_DIR):
        if not (index_dir / "chunks.json").exists():
            raise FileNotFoundError(f"No index at {index_dir}. Run `python -m rxdx_qna build` first.")
        self.chunks = [Chunk(**c) for c in json.loads((index_dir / "chunks.json").read_text())]
        self.vectors = np.load(index_dir / "vectors.npy")
        # Titles are repeated so a name match outweighs a passing mention in someone's bio.
        self.bm25 = BM25Okapi([tokenize(f"{c.title} {c.title} {c.text}") for c in self.chunks])
        self._embed = _embedder()

    def _dense_ranking(self, query: str) -> np.ndarray:
        q = np.array(next(iter(self._embed.embed([QUERY_PREFIX + query]))), dtype=np.float32)
        q /= np.linalg.norm(q)
        return np.argsort(-(self.vectors @ q))

    def _sparse_ranking(self, query: str) -> np.ndarray:
        return np.argsort(-self.bm25.get_scores(tokenize(query)))

    def search(self, query: str, k: int = 8, depth: int = 50) -> list[Hit]:
        fused: dict[int, float] = {}
        for ranking in (self._dense_ranking(query), self._sparse_ranking(query)):
            for rank, idx in enumerate(ranking[:depth]):
                fused[int(idx)] = fused.get(int(idx), 0.0) + 1.0 / (RRF_K + rank + 1)
        best = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:k]
        return [Hit(self.chunks[i], s) for i, s in best]
