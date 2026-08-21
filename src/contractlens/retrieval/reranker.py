import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.documents import Document
from sentence_transformers import CrossEncoder
from contractlens.retrieval.hybrid import hybrid_search, COLLECTION_NAME
import logging
from contractlens.core.logging_config import configure_logging

logger = logging.getLogger(__name__)

# Drop reranked chunks scoring below this cross-encoder threshold (raises
# context precision). Set via env; empty/unset disables filtering.
_RERANK_THRESHOLD_ENV = os.getenv("RERANK_SCORE_THRESHOLD", "").strip()
RERANK_SCORE_THRESHOLD = float(_RERANK_THRESHOLD_ENV) if _RERANK_THRESHOLD_ENV else None

# Load once globally — model is heavy
_reranker_model = None

def get_reranker() -> CrossEncoder:
    """
    Load cross-encoder model once and reuse.
    """
    global _reranker_model
    if _reranker_model is None:
        logger.info("Loading reranker model...")
        _reranker_model = CrossEncoder(
            "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )
        logger.info("✅ Reranker model loaded")
    return _reranker_model


def rerank(
    query: str,
    documents: list[Document],
    top_k: int = 5,
    score_threshold: float = None
) -> list[Document]:
    """
    Rerank documents using a cross-encoder.

    Cross-encoder looks at query AND document together, giving much better
    relevance scores than vector similarity alone.

    If score_threshold is set, chunks scoring below it are dropped instead of
    padding the result up to top_k — this raises context precision (fewer
    irrelevant chunks). At least one chunk is always returned so downstream
    analysis never sees an empty context.
    """
    if not documents:
        return []

    model = get_reranker()

    # Create query-document pairs
    pairs = [(query, doc.page_content) for doc in documents]

    # Score all pairs
    scores = model.predict(pairs)

    # Attach scores to documents
    for doc, score in zip(documents, scores):
        doc.metadata["rerank_score"] = float(score)

    # Sort by rerank score
    ranked = sorted(
        zip(documents, scores),
        key=lambda x: x[1],
        reverse=True
    )

    if score_threshold is not None:
        kept = [(doc, s) for doc, s in ranked if s >= score_threshold]
        # Never return nothing — fall back to the single best chunk.
        ranked = kept if kept else ranked[:1]

    return [doc for doc, _ in ranked[:top_k]]


def retrieve_and_rerank(
    query: str,
    collection_name: str = COLLECTION_NAME,
    bm25=None,
    chunks_metadata=None,
    k_retrieve: int = 20,
    k_final: int = 5,
    filename_filter: str = None
) -> list[Document]:
    """
    Full retrieval pipeline:
    1. Hybrid search (vector + BM25) → top 20
    2. Cross-encoder rerank → top 5

    Why this order:
    - Hybrid search is fast, casts wide net
    - Reranker is slow but very accurate, runs on small set

    collection_name / bm25 / chunks_metadata select the corpus to search — the
    per-upload flow passes an isolated index; omitting them uses the global one.

    filename_filter restricts hybrid search to one source document -- pass it
    when the question is known to be about a specific contract, so chunks from
    unrelated documents in the same corpus never reach the reranker at all.
    """
    # Step 1: Hybrid retrieval — cast wide net
    candidates = hybrid_search(
        query,
        collection_name=collection_name,
        bm25=bm25,
        chunks_metadata=chunks_metadata,
        k_final=k_retrieve,
        filename_filter=filename_filter,
    )
    logger.info(f"  📥 Retrieved {len(candidates)} candidates")

    # Step 2: Rerank — pick best, dropping low-relevance chunks if a threshold
    # is configured (improves context precision).
    reranked = rerank(query, candidates, top_k=k_final, score_threshold=RERANK_SCORE_THRESHOLD)
    logger.info(f"  🎯 Reranked to top {len(reranked)}")

    return reranked


if __name__ == "__main__":
    configure_logging()
    test_queries = [
        "What are the payment terms?",
        "What happens if the contract is terminated early?",
        "What are the confidentiality obligations?"
    ]

    for query in test_queries:
        logger.info(f"\n{'='*60}")
        logger.info(f"Query: {query}")
        logger.info(f"{'='*60}")

        results = retrieve_and_rerank(
            query,
            k_retrieve=20,
            k_final=5
        )

        for i, doc in enumerate(results, 1):
            logger.info(f"\nResult {i}:")
            logger.info(f"  Source       : {doc.metadata.get('filename')}")
            logger.info(f"  Rerank Score : {doc.metadata.get('rerank_score', 0):.4f}")
            logger.info(f"  RRF Score    : {doc.metadata.get('rrf_score', 0):.4f}")
            logger.info(f"  Type         : {doc.metadata.get('chunk_type')}")
            logger.info(f"  Preview      : {doc.page_content[:200]}...")