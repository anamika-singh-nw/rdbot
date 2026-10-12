"""The committed index must match the current chunker, or the hosted app answers from stale text."""

import json

import numpy as np

from rxdx_qna.chunking import build_chunks, load_records
from rxdx_qna.index import DATA_PATH, INDEX_DIR


def test_committed_index_matches_chunker():
    built = [c.to_dict() for c in build_chunks(load_records(DATA_PATH))]
    stored = json.loads((INDEX_DIR / "chunks.json").read_text())
    assert stored == built, "Index is stale — run `python -m rxdx_qna build` and commit rag-qna/index/"
    assert np.load(INDEX_DIR / "vectors.npy").shape == (len(built), 384)
