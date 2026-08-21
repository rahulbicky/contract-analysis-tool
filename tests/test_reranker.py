from unittest.mock import MagicMock

from langchain_core.documents import Document
import contractlens.retrieval.reranker as reranker


def test_rerank_orders_by_score_and_respects_top_k(monkeypatch):
    docs = [
        Document(page_content="low relevance"),
        Document(page_content="high relevance"),
        Document(page_content="medium relevance"),
    ]

    fake_model = MagicMock()
    fake_model.predict.return_value = [0.1, 0.9, 0.5]
    monkeypatch.setattr(reranker, "get_reranker", lambda: fake_model)

    result = reranker.rerank("some query", docs, top_k=2)

    assert [d.page_content for d in result] == ["high relevance", "medium relevance"]
    assert result[0].metadata["rerank_score"] == 0.9


def test_rerank_empty_documents_returns_empty_without_calling_model(monkeypatch):
    fake_model = MagicMock()
    monkeypatch.setattr(reranker, "get_reranker", lambda: fake_model)

    result = reranker.rerank("query", [], top_k=5)

    assert result == []
    fake_model.predict.assert_not_called()


def test_rerank_threshold_drops_low_scoring_chunks(monkeypatch):
    docs = [
        Document(page_content="irrelevant a"),
        Document(page_content="relevant"),
        Document(page_content="irrelevant b"),
    ]
    fake_model = MagicMock()
    fake_model.predict.return_value = [-2.0, 5.0, -1.0]
    monkeypatch.setattr(reranker, "get_reranker", lambda: fake_model)

    result = reranker.rerank("q", docs, top_k=5, score_threshold=0.0)

    # only the positively-scored chunk survives the threshold
    assert [d.page_content for d in result] == ["relevant"]


def test_rerank_threshold_falls_back_to_best_when_all_below(monkeypatch):
    docs = [Document(page_content="a"), Document(page_content="b")]
    fake_model = MagicMock()
    fake_model.predict.return_value = [-5.0, -3.0]
    monkeypatch.setattr(reranker, "get_reranker", lambda: fake_model)

    result = reranker.rerank("q", docs, top_k=5, score_threshold=0.0)

    # never returns empty — keeps the single best chunk
    assert [d.page_content for d in result] == ["b"]
