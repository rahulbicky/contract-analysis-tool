from langchain_core.documents import Document
from contractlens.retrieval.hybrid import reciprocal_rank_fusion


def _doc(chunk_id, content="text"):
    return Document(page_content=content, metadata={"chunk_id": chunk_id})


def test_rrf_ranks_docs_appearing_in_both_lists_highest():
    vector_results = [(_doc("a"), 0.9), (_doc("b"), 0.8), (_doc("c"), 0.7)]
    bm25_results = [(_doc("b"), 5.0), (_doc("a"), 4.0), (_doc("d"), 3.0)]

    fused = reciprocal_rank_fusion(vector_results, bm25_results, k=60)
    fused_ids = [doc.metadata["chunk_id"] for doc in fused]

    # "a" and "b" appear near the top of both rankings, so they should be
    # scored above anything that only appears in one ranking.
    assert set(fused_ids[:2]) == {"a", "b"}
    assert "c" in fused_ids
    assert "d" in fused_ids


def test_rrf_deduplicates_by_chunk_id():
    vector_results = [(_doc("a"), 0.9)]
    bm25_results = [(_doc("a"), 5.0)]

    fused = reciprocal_rank_fusion(vector_results, bm25_results)

    assert len(fused) == 1
    assert fused[0].metadata["chunk_id"] == "a"


def test_rrf_attaches_score_to_metadata():
    fused = reciprocal_rank_fusion([(_doc("a"), 0.9)], [])
    assert "rrf_score" in fused[0].metadata
    assert fused[0].metadata["rrf_score"] > 0


def test_rrf_empty_inputs_returns_empty():
    assert reciprocal_rank_fusion([], []) == []
