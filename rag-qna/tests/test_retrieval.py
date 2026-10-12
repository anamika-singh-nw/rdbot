"""Guards retrieval quality against regressions. Needs a built index (`python -m rxdx_qna build`)."""

import sys
from pathlib import Path

import pytest

from rxdx_qna.index import INDEX_DIR, Retriever

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
from run_retrieval import evaluate  # noqa: E402

pytestmark = pytest.mark.skipif(not (INDEX_DIR / "chunks.json").exists(), reason="index not built")


@pytest.fixture(scope="module")
def retriever():
    return Retriever()


def test_eval_thresholds(retriever):
    r = evaluate(retriever)
    assert r["hit@8"] >= 0.95, r["misses"]
    assert r["mrr"] >= 0.80


def test_exact_name_ranks_first(retriever):
    assert retriever.search("Dr Chirag D", k=1)[0].chunk.id == "doctor:dr-chirag-d"


def test_lay_term_reaches_speciality(retriever):
    top = retriever.search("kidney doctor", k=3)
    assert any("Nephrology" in h.chunk.text for h in top)
