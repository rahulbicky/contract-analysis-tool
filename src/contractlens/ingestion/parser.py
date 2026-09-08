import os
from pathlib import Path
from unstructured.partition.pdf import partition_pdf
import json
import logging
from contractlens.core.logging_config import configure_logging

logger = logging.getLogger(__name__)

def clean_elements(structured: list[dict]) -> list[dict]:
    """
    Reclassify UncategorizedText based on content patterns.
    """
    cleaned = []
    for el in structured:
        if el["type"] == "UncategorizedText":
            content = el["content"].strip()
            
            # Reclassify based on content
            if len(content.split()) < 10 and content.endswith(":"):
                el["type"] = "Title"
            elif content.startswith(("1.", "2.", "a.", "b.", "•", "-")):
                el["type"] = "ListItem"
            elif len(content) > 100:
                el["type"] = "NarrativeText"
            # else leave as UncategorizedText
        
        # Skip empty content and page breaks
        if el["content"].strip() and el["type"] != "PageBreak":
            cleaned.append(el)
    
    return cleaned


def parse_document(
    file_path: str,
    output_dir: str = "./data/processed",
    strategy: str = "hi_res"    # ← add this parameter
) -> list[dict]:
    logger.info(f"\nParsing: {file_path}")
    
    elements = partition_pdf(
        filename=file_path,
        strategy=strategy,          # ← use parameter
        infer_table_structure=True,
        include_page_breaks=True
    )
    
    structured = []
    type_counts = {}
    
    for el in elements:
        element_type = el.category
        type_counts[element_type] = type_counts.get(element_type, 0) + 1
        
        structured.append({
            "content": el.text,
            "type": element_type,
            "metadata": {
                "page": el.metadata.page_number,
                "source": file_path,
                "filename": Path(file_path).name,
                "element_type": element_type
            }
        })
    
    # Clean and reclassify
    structured = clean_elements(structured)       # ← add this line
    
    # Recount after cleaning
    type_counts = {}
    for el in structured:
        type_counts[el["type"]] = type_counts.get(el["type"], 0) + 1
    
    # Save
    output_path = os.path.join(
        output_dir,
        Path(file_path).stem + "_parsed.json"
    )
    os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(structured, f, indent=2)
    
    logger.info(f" Parsed {len(elements)} elements → {len(structured)} after cleaning")
    logger.info(f" Element breakdown:")
    for etype, count in sorted(type_counts.items()):
        logger.info(f"   {etype}: {count}")
    logger.info(f" Saved to {output_path}")
    
    return structured

def parse_all_documents(raw_dir: str = "./data/raw") -> dict:
    """
    Parse all PDFs in the raw directory.
    """
    all_docs = {}
    pdf_files = [f for f in os.listdir(raw_dir) if f.endswith('.pdf')]
    
    if not pdf_files:
        logger.error("❌ No PDFs found in", raw_dir)
        return {}
    
    logger.info(f"Found {len(pdf_files)} PDFs to parse")
    
    for filename in pdf_files:
        file_path = os.path.join(raw_dir, filename)
        try:
            elements = parse_document(file_path)
            all_docs[filename] = elements
        except Exception as e:
            logger.error(f"❌ Failed to parse {filename}: {e}")
    
    return all_docs


if __name__ == "__main__":
    configure_logging()
    docs = parse_all_documents("./data/raw")
    
    # Quick quality check
    logger.info("\n" + "="*50)
    logger.info("QUALITY CHECK")
    logger.info("="*50)
    for filename, elements in docs.items():
        tables = [e for e in elements if e["type"] == "Table"]
        text = [e for e in elements if e["type"] == "NarrativeText"]
        titles = [e for e in elements if e["type"] == "Title"]
        logger.info(f"\n{filename}:")
        logger.info(f"  Tables found: {len(tables)}")
        logger.info(f"  Text blocks: {len(text)}")
        logger.info(f"  Headings: {len(titles)}")
        if tables:
            logger.info(f"  First table preview: {tables[0]['content'][:200]}")