import json
import os
from pathlib import Path
from langchain_experimental.text_splitter import SemanticChunker
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from contractlens.core.llm import get_embeddings
from dotenv import load_dotenv
import logging
from contractlens.core.logging_config import configure_logging

logger = logging.getLogger(__name__)

load_dotenv()

def load_parsed_document(json_path: str) -> list[dict]:
    """
    Load previously parsed JSON from parser.py output.
    """
    with open(json_path, "r") as f:
        return json.load(f)


def chunk_tables(elements: list[dict]) -> list[Document]:
    """
    Tables are NEVER split — they go in as one chunk.
    Splitting a table destroys its meaning.
    """
    table_chunks = []
    for el in elements:
        if el["type"] == "Table":
            table_chunks.append(Document(
                page_content=el["content"],
                metadata={
                    **el["metadata"],
                    "chunk_type": "table"
                }
            ))
    return table_chunks


def chunk_titles_with_content(elements: list[dict]) -> list[str]:
    """
    Group Title + following NarrativeText/ListItems together.
    This keeps section headings with their content.
    
    Example:
        Title: "Payment Terms"
        NarrativeText: "Payment is due within 30 days..."
        → becomes one block: "Payment Terms\nPayment is due within 30 days..."
    """
    grouped = []
    current_section = []

    for el in elements:
        if el["type"] in ["Table", "PageBreak", "Image"]:
            continue

        if el["type"] == "Title":
            # Save previous section
            if current_section:
                grouped.append("\n".join(current_section))
            # Start new section with this title
            current_section = [el["content"]]
        else:
            current_section.append(el["content"])

    # Don't forget last section
    if current_section:
        grouped.append("\n".join(current_section))

    return grouped


def chunk_text_semantically(
    text_blocks: list[str],
    source_metadata: dict
) -> list[Document]:
    """
    Use SemanticChunker to split text on meaning boundaries,
    not fixed character counts.
    """
    embeddings = get_embeddings()
    splitter = SemanticChunker(
        embeddings,
        breakpoint_threshold_type="percentile",
        breakpoint_threshold_amount=90    
        # 90th percentile = split when meaning changes significantly
    )

    # Combine all text blocks into one string for semantic splitting
    full_text = "\n\n".join(text_blocks)

    docs = splitter.create_documents(
        texts=[full_text],
        metadatas=[{
            **source_metadata,
            "chunk_type": "text"
        }]
    )

    return docs

def clean_chunks(chunks: list[Document]) -> list[Document]:
    """
    Remove junk chunks and split oversized ones.
    """
    cleaned = []
    for chunk in chunks:
        content = chunk.page_content.strip()
        
        # Remove tiny chunks — they are junk
        if len(content) < 50:
            logger.info(f"  🗑️  Removed tiny chunk: '{content[:30]}'")
            continue
        
        cleaned.append(chunk)
    
    return cleaned

def split_huge_chunks(
    chunks: list[Document],
    max_size: int = 2000
) -> list[Document]:
    """
    Any text chunk over max_size gets split further
    using recursive character splitting.
    Tables are never split regardless of size.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_size,
        chunk_overlap=200,
        length_function=len
    )
    
    final_chunks = []
    for chunk in chunks:
        # Never split tables
        if chunk.metadata.get("chunk_type") == "table":
            final_chunks.append(chunk)
            continue
        
        # Split oversized text chunks
        if len(chunk.page_content) > max_size:
            split = splitter.split_documents([chunk])
            for i, s in enumerate(split):
                s.metadata["chunk_type"] = "text"
                s.metadata["was_split"] = True
            final_chunks.extend(split)
            logger.info(f"  ✂️  Split huge chunk ({len(chunk.page_content)} chars) → {len(split)} pieces")
        else:
            final_chunks.append(chunk)
    
    return final_chunks

def chunk_document(
    json_path: str,
    output_dir: str = "./data/processed"
) -> list[Document]:
    logger.info(f"\nChunking: {json_path}")

    elements = load_parsed_document(json_path)
    filename = Path(json_path).stem.replace("_parsed", "")

    source_metadata = {
        "source": filename,
        "filename": filename
    }

    # 1. Tables stay whole
    table_chunks = chunk_tables(elements)
    logger.info(f"  📊 Table chunks: {len(table_chunks)}")

    # 2. Group titles with content
    text_blocks = chunk_titles_with_content(elements)
    logger.info(f"  📝 Text sections grouped: {len(text_blocks)}")

    # 3. Semantic chunking
    text_chunks = chunk_text_semantically(text_blocks, source_metadata)
    logger.info(f"  ✂️  Semantic chunks created: {len(text_chunks)}")

    # 4. Combine
    all_chunks = table_chunks + text_chunks

    # 5. Remove tiny chunks          ← NEW
    all_chunks = clean_chunks(all_chunks)

    # 6. Split huge chunks           ← NEW
    all_chunks = split_huge_chunks(all_chunks, max_size=2000)

    logger.info(f"  ✅ Final chunks: {len(all_chunks)}")

    # 7. Add chunk index to metadata
    for i, chunk in enumerate(all_chunks):
        chunk.metadata["chunk_id"] = f"{filename}_chunk_{i}"
        chunk.metadata["chunk_index"] = i
        chunk.metadata["total_chunks"] = len(all_chunks)

    # 8. Save
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(
        output_dir,
        filename + "_chunks.json"
    )
    chunks_data = [
        {
            "chunk_id": c.metadata["chunk_id"],
            "content": c.page_content,
            "chunk_type": c.metadata.get("chunk_type"),
            "metadata": c.metadata
        }
        for c in all_chunks
    ]
    with open(output_path, "w") as f:
        json.dump(chunks_data, f, indent=2)

    logger.info(f"  💾 Saved to {output_path}")
    return all_chunks

def chunk_all_documents(
    processed_dir: str = "./data/processed"
) -> dict[str, list[Document]]:
    """
    Chunk all parsed JSON files in processed directory.
    """
    all_chunks = {}
    json_files = [
        f for f in os.listdir(processed_dir)
        if f.endswith("_parsed.json")
    ]

    if not json_files:
        logger.error("❌ No parsed JSON files found. Run parser.py first.")
        return {}

    logger.info(f"Found {len(json_files)} parsed documents to chunk")

    for json_file in json_files:
        json_path = os.path.join(processed_dir, json_file)
        try:
            chunks = chunk_document(json_path)
            all_chunks[json_file] = chunks
        except Exception as e:
            logger.error(f"❌ Failed to chunk {json_file}: {e}")

    return all_chunks


def quality_check(all_chunks: dict):
    """
    Verify chunk quality before indexing.
    """
    logger.info("\n" + "="*50)
    logger.info("CHUNK QUALITY CHECK")
    logger.info("="*50)

    for filename, chunks in all_chunks.items():
        text_chunks = [c for c in chunks if c.metadata.get("chunk_type") == "text"]
        table_chunks = [c for c in chunks if c.metadata.get("chunk_type") == "table"]

        lengths = [len(c.page_content) for c in text_chunks]
        avg_length = sum(lengths) / len(lengths) if lengths else 0
        min_length = min(lengths) if lengths else 0
        max_length = max(lengths) if lengths else 0

        logger.info(f"\n{filename}:")
        logger.info(f"  Total chunks    : {len(chunks)}")
        logger.info(f"  Text chunks     : {len(text_chunks)}")
        logger.info(f"  Table chunks    : {len(table_chunks)}")
        logger.info(f"  Avg text length : {avg_length:.0f} chars")
        logger.info(f"  Min text length : {min_length} chars")
        logger.info(f"  Max text length : {max_length} chars")

        # Warn about bad chunks
        tiny_chunks = [c for c in text_chunks if len(c.page_content) < 50]
        huge_chunks = [c for c in text_chunks if len(c.page_content) > 3000]

        if tiny_chunks:
            logger.warning(f"  ⚠️  Tiny chunks (<50 chars): {len(tiny_chunks)} — may need cleanup")
        if huge_chunks:
            logger.warning(f"  ⚠️  Huge chunks (>3000 chars): {len(huge_chunks)} — may hurt retrieval")
        if not tiny_chunks and not huge_chunks:
            logger.info(f"  ✅ Chunk sizes look healthy")

        # Preview first text chunk
        if text_chunks:
            logger.info(f"\n  First chunk preview:")
            logger.info(f"  {text_chunks[0].page_content[:300]}...")


if __name__ == "__main__":
    configure_logging()
    all_chunks = chunk_all_documents("./data/processed")
    quality_check(all_chunks)