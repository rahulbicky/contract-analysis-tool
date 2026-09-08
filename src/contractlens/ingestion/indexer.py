import os
import json
import pickle
from pathlib import Path
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    PayloadSchemaType
)
from rank_bm25 import BM25Okapi
from dotenv import load_dotenv
import logging
from contractlens.core.logging_config import configure_logging
from contractlens.core.llm import get_embeddings, EMBEDDING_DIM

logger = logging.getLogger(__name__)

load_dotenv()

# Constants
COLLECTION_NAME = "contractlens"
VECTOR_SIZE = EMBEDDING_DIM          # matches the local embedding model (all-MiniLM-L6-v2 = 384)
BM25_INDEX_PATH = "./data/processed/bm25_index.pkl"
CHUNKS_METADATA_PATH = "./data/processed/all_chunks_metadata.json"


def get_qdrant_client() -> QdrantClient:
    """
    Connect to Qdrant.
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
        client.get_collections()    # test connection
        logger.info("✅ Connected to Qdrant server")
        return client
    except Exception:
        logger.warning("⚠️  Qdrant server not found — using local mode")
        client = QdrantClient(path="./data/qdrant_local")
        return client


def create_collection(client: QdrantClient, collection_name: str = COLLECTION_NAME):
    """
    Create a Qdrant collection (dropping any existing one of the same name).
    """
    existing = [c.name for c in client.get_collections().collections]

    if collection_name in existing:
        logger.warning(f"⚠️  Collection '{collection_name}' already exists — deleting and recreating")
        client.delete_collection(collection_name)

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE
        )
    )

    # Qdrant requires a payload index before a field can be used in a query
    # filter -- this backs the per-document filename_filter in hybrid_search()
    # (retrieval/hybrid.py), which keeps document-specific questions from
    # retrieving chunks out of unrelated contracts in the same collection.
    client.create_payload_index(
        collection_name=collection_name,
        field_name="filename",
        field_schema=PayloadSchemaType.KEYWORD
    )

    logger.info(f"✅ Created collection: {collection_name} (with filename payload index)")


def delete_collection(client: QdrantClient, collection_name: str):
    """Best-effort delete of a per-upload collection (used for cleanup)."""
    try:
        client.delete_collection(collection_name)
        logger.info(f"🗑️  Deleted collection: {collection_name}")
    except Exception as e:
        logger.warning(f"⚠️  Could not delete collection {collection_name}: {e}")


def load_all_chunks(
    processed_dir: str = "./data/processed"
) -> list[Document]:
    """
    Load all chunk JSON files from processed directory.
    """
    chunks = []
    chunk_files = [
        f for f in os.listdir(processed_dir)
        if f.endswith("_chunks.json")
    ]

    if not chunk_files:
        logger.error("❌ No chunk files found. Run chunker.py first.")
        return []

    for chunk_file in chunk_files:
        path = os.path.join(processed_dir, chunk_file)
        with open(path, "r") as f:
            data = json.load(f)

        for item in data:
            chunks.append(Document(
                page_content=item["content"],
                metadata=item["metadata"]
            ))

    logger.info(f"✅ Loaded {len(chunks)} total chunks from {len(chunk_files)} files")
    return chunks


def build_vector_index(
    client: QdrantClient,
    chunks: list[Document],
    collection_name: str = COLLECTION_NAME
) -> None:
    """
    Embed all chunks and store in the given Qdrant collection.
    """
    logger.info(f"\nBuilding vector index for {len(chunks)} chunks...")
    embeddings = get_embeddings()

    # Process in batches to avoid API rate limits
    batch_size = 20
    points = []

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c.page_content for c in batch]

        # Get embeddings for batch
        vectors = embeddings.embed_documents(texts)

        for j, (chunk, vector) in enumerate(zip(batch, vectors)):
            point_id = i + j
            points.append(PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "content": chunk.page_content,
                    "chunk_id": chunk.metadata.get("chunk_id", f"chunk_{point_id}"),
                    "chunk_type": chunk.metadata.get("chunk_type", "text"),
                    "source": chunk.metadata.get("source", "unknown"),
                    "filename": chunk.metadata.get("filename", "unknown"),
                    "chunk_index": chunk.metadata.get("chunk_index", 0)
                }
            ))

        logger.info(f"  Embedded batch {i//batch_size + 1}/{(len(chunks)-1)//batch_size + 1}")

    # Upload all points to Qdrant
    client.upsert(
        collection_name=collection_name,
        points=points
    )
    logger.info(f"✅ Uploaded {len(points)} vectors to Qdrant")


def build_bm25_index(
    chunks: list[Document],
    bm25_path: str = BM25_INDEX_PATH,
    meta_path: str = CHUNKS_METADATA_PATH
) -> BM25Okapi:
    """
    Build a BM25 keyword index over the chunks and save it to disk.
    Paths default to the global corpus but can be per-upload.
    """
    logger.info(f"\nBuilding BM25 index for {len(chunks)} chunks...")

    # Tokenize each chunk
    tokenized = [
        chunk.page_content.lower().split()
        for chunk in chunks
    ]

    bm25 = BM25Okapi(tokenized)

    # Save BM25 index
    os.makedirs(os.path.dirname(bm25_path), exist_ok=True)
    with open(bm25_path, "wb") as f:
        pickle.dump(bm25, f)

    # Save chunk texts separately for BM25 result lookup
    chunks_metadata = [
        {
            "content": chunk.page_content,
            "metadata": chunk.metadata
        }
        for chunk in chunks
    ]
    with open(meta_path, "w") as f:
        json.dump(chunks_metadata, f, indent=2)

    logger.info(f"✅ BM25 index saved to {bm25_path}")
    logger.info(f"✅ Chunks metadata saved to {meta_path}")
    return bm25


def verify_index(client: QdrantClient):
    """
    Quick verification that indexing worked correctly.
    """
    collection = client.get_collection(COLLECTION_NAME)
    count = collection.points_count

    logger.info(f"\n{'='*50}")
    logger.info("INDEX VERIFICATION")
    logger.info(f"{'='*50}")
    logger.info(f"  Qdrant vectors stored : {count}")

    # Test a sample search
    embeddings = get_embeddings()
    test_query = "payment terms and conditions"
    query_vector = embeddings.embed_query(test_query)

    results = client.query_points(
    collection_name=COLLECTION_NAME,
    query=query_vector,
    limit=3
    ).points

    logger.info(f"\n  Test query: '{test_query}'")
    logger.info(f"  Top 3 results:")
    for i, r in enumerate(results, 1):
        logger.info(f"\n  Result {i} (score: {r.score:.3f}):")
        logger.info(f"  Source: {r.payload.get('filename')}")
        logger.info(f"  Preview: {r.payload.get('content')[:150]}...")

    # Verify BM25
    if os.path.exists(BM25_INDEX_PATH):
        logger.info(f"\n  ✅ BM25 index exists at {BM25_INDEX_PATH}")
    else:
        logger.error(f"\n  ❌ BM25 index missing")


def build_full_index(processed_dir: str = "./data/processed"):
    """
    Main function — builds both vector and BM25 indexes.
    """
    # 1. Connect to Qdrant
    client = get_qdrant_client()

    # 2. Create collection
    create_collection(client)

    # 3. Load all chunks
    chunks = load_all_chunks(processed_dir)
    if not chunks:
        return

    # 4. Build vector index
    build_vector_index(client, chunks)

    # 5. Build BM25 index
    build_bm25_index(chunks)

    # 6. Verify everything worked
    verify_index(client)

    logger.info(f"\n✅ Full index built successfully")
    logger.info(f"   Total documents indexed: {len(chunks)}")
    logger.info(f"   Ready for retrieval")


if __name__ == "__main__":
    configure_logging()
    build_full_index()