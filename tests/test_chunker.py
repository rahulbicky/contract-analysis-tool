from langchain_core.documents import Document
from contractlens.ingestion.chunker import (
    chunk_tables,
    chunk_titles_with_content,
    clean_chunks,
    split_huge_chunks,
)


def test_chunk_tables_extracts_only_table_elements():
    elements = [
        {"type": "Title", "content": "Section 1", "metadata": {}},
        {"type": "Table", "content": "col1 | col2", "metadata": {"page": 1}},
        {"type": "NarrativeText", "content": "some text", "metadata": {}},
    ]

    tables = chunk_tables(elements)

    assert len(tables) == 1
    assert tables[0].page_content == "col1 | col2"
    assert tables[0].metadata["chunk_type"] == "table"


def test_chunk_titles_with_content_groups_sections():
    elements = [
        {"type": "Title", "content": "Payment Terms"},
        {"type": "NarrativeText", "content": "Payment is due within 30 days."},
        {"type": "Title", "content": "Termination"},
        {"type": "NarrativeText", "content": "Either party may terminate."},
        {"type": "Table", "content": "skip me"},
        {"type": "PageBreak", "content": ""},
    ]

    sections = chunk_titles_with_content(elements)

    assert sections == [
        "Payment Terms\nPayment is due within 30 days.",
        "Termination\nEither party may terminate.",
    ]


def test_chunk_titles_with_content_handles_no_leading_title():
    elements = [
        {"type": "NarrativeText", "content": "orphan text"},
        {"type": "Title", "content": "Section"},
        {"type": "NarrativeText", "content": "body"},
    ]

    sections = chunk_titles_with_content(elements)

    assert sections == ["orphan text", "Section\nbody"]


def test_clean_chunks_removes_tiny_chunks():
    chunks = [
        Document(page_content="x" * 10, metadata={}),
        Document(page_content="x" * 100, metadata={}),
    ]

    cleaned = clean_chunks(chunks)

    assert len(cleaned) == 1
    assert len(cleaned[0].page_content) == 100


def test_split_huge_chunks_never_splits_tables():
    huge_table = Document(page_content="x" * 5000, metadata={"chunk_type": "table"})

    result = split_huge_chunks([huge_table], max_size=2000)

    assert len(result) == 1
    assert result[0].page_content == "x" * 5000


def test_split_huge_chunks_splits_oversized_text():
    huge_text = Document(page_content="word " * 1000, metadata={"chunk_type": "text"})

    result = split_huge_chunks([huge_text], max_size=2000)

    assert len(result) > 1
    assert all(c.metadata.get("was_split") for c in result)


def test_split_huge_chunks_leaves_small_chunks_untouched():
    small = Document(page_content="short text", metadata={"chunk_type": "text"})

    result = split_huge_chunks([small], max_size=2000)

    assert result == [small]
