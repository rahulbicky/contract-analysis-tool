import os
import json
import pickle
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue
from rank_bm25 import BM25Okapi
from dotenv import load_dotenv
import logging
from contractlens.core.logging_config import configure_logging
from contractlens.core.llm import get_embeddings

logger = logging.getLogger(__name__)

load_dotenv()

COLLECTION_NAME = "contractlens"
BM25_INDEX_PATH = "./data/processed/bm25_index.pkl"
CHUNKS_METADATA_PATH = "./data/processed/all_chunks_metadata.json"


def load_bm25(
    bm25_path: str = BM25_INDEX_PATH,
    meta_path: str = CHUNKS_METADATA_PATH,
) -> tuple[BM25Okapi, list[dict]]:
    """
    Load a BM25 index and its chunk metadata from disk. Paths default to the
    global corpus but can point at a per-request index (per-upload isolation).
    """
    with open(bm25_path, "rb") as f:
        bm25 = pickle.load(f)

    with open(meta_path, "r") as f:
        chunks_metadata = json.load(f)

    return bm25, chunks_metadata


def load_bm25_index() -> tuple[BM25Okapi, list[dict]]:
    """Backwards-compatible loader for the global corpus."""
    return load_bm25(BM25_INDEX_PATH, CHUNKS_METADATA_PATH)


# Create client ONCE at module level
def get_qdrant_client() -> QdrantClient:
    """
    Uses QDRANT_URL (+ QDRANT_API_KEY) for Qdrant Cloud if set, otherwise
    QDRANT_HOST/QDRANT_PORT for a local/self-hosted instance, falling back to
    an embedded local-mode client if neither is reachable.
    """
    try:
        qdrant_url = os.getenv("QDRANT_URL")
        if qdrant_url:
            client = QdrantClient(url=qdrant_url, api_key=os.getenv("QDRANT_API_KEY"))
        else:
            client = QdrantClient(
                host=os.getenv("QDRANT_HOST", "localhost"),
                port=int(os.getenv("QDRANT_PORT", 6333))
            )
        client.get_collections()
        return client
    except Exception:
        return QdrantClient(
            path="./data/qdrant_local",
            force_disable_check_same_thread=True    # ← add this
        )

# Single shared Qdrant client (connection reuse). BM25 is no longer cached
# globally because it varies per corpus / per upload.
_qdrant_client = None


def get_qdrant():
    """Return a shared Qdrant client, created once and reused."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = get_qdrant_client()
    return _qdrant_client


def get_clients():
    """
    Backwards-compatible helper for the global corpus: shared Qdrant client
    plus the on-disk global BM25 index.
    """
    return get_qdrant(), *load_bm25_index()


def vector_search(
    query: str,
    client: QdrantClient,
    collection_name: str = COLLECTION_NAME,
    k: int = 20,
    filename_filter: str = None
) -> list[tuple[Document, float]]:
    """
    Semantic search using Qdrant.
    Returns list of (Document, score) tuples.

    filename_filter restricts the search to chunks from one source document
    (matched against the "filename" payload field) -- without it, retrieval
    searches every document in the collection, which is how unrelated chunks
    from other contracts end up polluting the top-k for document-specific
    questions.
    """
    embeddings = get_embeddings()
    query_vector = embeddings.embed_query(query)

    query_filter = None
    if filename_filter:
        query_filter = Filter(
            must=[FieldCondition(key="filename", match=MatchValue(value=filename_filter))]
        )

    results = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        query_filter=query_filter,
        limit=k
    ).points

    docs_with_scores = []
    for r in results:
        doc = Document(
            page_content=r.payload.get("content", ""),
            metadata={
                "chunk_id": r.payload.get("chunk_id"),
                "chunk_type": r.payload.get("chunk_type"),
                "source": r.payload.get("source"),
                "filename": r.payload.get("filename"),
                "chunk_index": r.payload.get("chunk_index"),
                "vector_score": r.score
            }
        )
        docs_with_scores.append((doc, r.score))

    return docs_with_scores


def bm25_search(
    query: str,
    bm25: BM25Okapi,
    chunks_metadata: list[dict],
    k: int = 20,
    filename_filter: str = None
) -> list[tuple[Document, float]]:
    """
    Keyword search using BM25.
    Returns list of (Document, score) tuples.

    filename_filter restricts results to one source document, same purpose as
    in vector_search. BM25 scores are computed over the full corpus (the index
    isn't rebuilt per document), so filtering happens by excluding
    non-matching indices before picking the top k.
    """
    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)

    eligible_indices = range(len(scores))
    if filename_filter:
        eligible_indices = [
            i for i in eligible_indices
            if chunks_metadata[i]["metadata"].get("filename") == filename_filter
        ]

    # Get top k indices
    top_indices = sorted(
        eligible_indices,
        key=lambda i: scores[i],
        reverse=True
    )[:k]

    docs_with_scores = []
    for idx in top_indices:
        if scores[idx] == 0:
            continue        # skip zero-score results

        chunk = chunks_metadata[idx]
        doc = Document(
            page_content=chunk["content"],
            metadata={
                **chunk["metadata"],
                "bm25_score": float(scores[idx])
            }
        )
        docs_with_scores.append((doc, float(scores[idx])))

    return docs_with_scores


def reciprocal_rank_fusion(
    vector_results: list[tuple[Document, float]],
    bm25_results: list[tuple[Document, float]],
    k: int = 60
) -> list[Document]:
    """
    Combine vector and BM25 results using Reciprocal Rank Fusion.
    
    RRF score = 1/(k + rank)
    
    Higher RRF = appeared high in both rankings = more relevant.
    k=60 is standard, reduces impact of very high rankings.
    """
    rrf_scores = {}
    doc_map = {}

    # Score from vector ranking
    for rank, (doc, _) in enumerate(vector_results):
        chunk_id = doc.metadata.get("chunk_id", doc.page_content[:50])
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + 1 / (k + rank + 1)
        doc_map[chunk_id] = doc

    # Score from BM25 ranking
    for rank, (doc, _) in enumerate(bm25_results):
        chunk_id = doc.metadata.get("chunk_id", doc.page_content[:50])
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + 1 / (k + rank + 1)
        doc_map[chunk_id] = doc

    # Sort by combined RRF score
    sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)

    # Return documents with RRF scores in metadata
    fused = []
    for chunk_id in sorted_ids:
        doc = doc_map[chunk_id]
        doc.metadata["rrf_score"] = rrf_scores[chunk_id]
        fused.append(doc)

    return fused


def hybrid_search(
    query: str,
    collection_name: str = COLLECTION_NAME,
    bm25: BM25Okapi = None,
    chunks_metadata: list[dict] = None,
    k_final: int = 20,
    filename_filter: str = None
) -> list[Document]:
    """
    Hybrid vector + BM25 search over a given corpus. If bm25/chunks_metadata are
    not supplied, the global on-disk index is used (backwards compatible); the
    per-upload flow passes an isolated collection + BM25 index instead.

    filename_filter restricts both legs of retrieval to one source document --
    pass it whenever the question is known to be about a specific contract
    rather than the whole corpus, to keep unrelated documents' chunks out of
    the candidate set entirely (see context_precision in evaluation/metrics.py).
    """
    client = get_qdrant()
    if bm25 is None or chunks_metadata is None:
        bm25, chunks_metadata = load_bm25_index()

    vector_results = vector_search(query, client, collection_name, k=20, filename_filter=filename_filter)
    bm25_results = bm25_search(query, bm25, chunks_metadata, k=20, filename_filter=filename_filter)
    fused = reciprocal_rank_fusion(vector_results, bm25_results)

    return fused[:k_final]


if __name__ == "__main__":
    configure_logging()
    test_queries = [
        "What are the payment terms?",
        "What happens if the contract is terminated early?",
        "What are the confidentiality obligations?"
    ]

    # Initialize once before all queries
    get_clients()

    for query in test_queries:
        logger.info(f"\n{'='*60}")
        logger.info(f"Query: {query}")
        logger.info(f"{'='*60}")

        results = hybrid_search(query, k_final=3)

        for i, doc in enumerate(results, 1):
            logger.info(f"\nResult {i}:")
            logger.info(f"  Source    : {doc.metadata.get('filename')}")
            logger.info(f"  RRF Score : {doc.metadata.get('rrf_score', 0):.4f}")
            logger.info(f"  Type      : {doc.metadata.get('chunk_type')}")
            logger.info(f"  Preview   : {doc.page_content[:200]}...")