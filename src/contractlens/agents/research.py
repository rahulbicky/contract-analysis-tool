import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, Field
from contractlens.core.token_usage import accumulate_usage
from contractlens.core.llm import get_chat_model
from dotenv import load_dotenv
from contractlens.retrieval.reranker import retrieve_and_rerank
from contractlens.retrieval.hybrid import COLLECTION_NAME, load_bm25
import logging
from contractlens.core.logging_config import configure_logging

logger = logging.getLogger(__name__)

load_dotenv()


# ── Output Schema ──────────────────────────────────────────
class RiskFinding(BaseModel):
    clause_type: str = Field(
        description="Type of clause: payment, liability, termination, IP, confidentiality, compliance"
    )
    finding: str = Field(
        description="What was found in this clause"
    )
    risk_level: str = Field(
        description="Risk level: low, medium, high"
    )
    recommendation: str = Field(
        description="What should be done about this risk"
    )
    source_chunk: str = Field(
        description="The exact text this finding came from"
    )


class ResearchOutput(BaseModel):
    summary: str = Field(
        description="Overall summary of the contract"
    )
    findings: list[RiskFinding] = Field(
        description="List of risk findings from the contract"
    )
    overall_risk: str = Field(
        description="Overall risk level: low, medium, high"
    )
    recommended_action: str = Field(
        description="Top recommended action to take"
    )


# ── Prompt ─────────────────────────────────────────────────
RESEARCH_PROMPT = """You are a contract risk analyst.
Analyze the following contract clauses and identify risks.
Be specific — quote directly from the text when describing findings.

Contract Clauses Retrieved:
{context}

Risk areas to investigate: {risk_areas}

For each risk area found:
1. Identify the specific clause
2. Assess the risk level (low/medium/high)
3. Give a clear recommendation

Rules:
- Only report findings that are actually in the provided clauses
- If a risk area has no relevant clause, skip it
- Be specific, not generic
- Quote the relevant text in source_chunk

{format_instructions}"""


# ── Research Queries by Risk Area ──────────────────────────
RISK_QUERIES = {
    "payment": [
        "payment terms amount due date",
        "compensation fees invoices late payment"
    ],
    "liability": [
        "liability limitation indemnification damages",
        "warranty disclaimer limitation of liability"
    ],
    "termination": [
        "termination clause early termination notice period",
        "breach of contract cure period consequences"
    ],
    "IP": [
        "intellectual property ownership work product",
        "assignment of rights inventions copyright"
    ],
    "confidentiality": [
        "confidentiality obligations trade secrets",
        "non-disclosure proprietary information"
    ],
    "compliance": [
        "compliance laws regulations FCPA",
        "governing law jurisdiction dispute resolution"
    ]
}


def retrieve_for_risk_areas(
    risk_areas: list[str],
    collection_name: str = COLLECTION_NAME,
    bm25=None,
    chunks_metadata=None,
) -> dict[str, list[Document]]:
    """
    Run targeted retrieval for each risk area against the given corpus.
    Returns dict of {risk_area: [relevant_docs]}
    """
    retrieved = {}

    for area in risk_areas:
        queries = RISK_QUERIES.get(area, [area])
        # Only use FIRST query per area — faster
        # Full 2-query search only needed for evaluation
        queries = queries[:1]
        area_docs = []

        for query in queries:
            docs = retrieve_and_rerank(
                query,
                collection_name=collection_name,
                bm25=bm25,
                chunks_metadata=chunks_metadata,
                k_retrieve=10,
                k_final=3,
            )
            area_docs.extend(docs)

        # Deduplicate by chunk_id
        seen = set()
        unique_docs = []
        for doc in area_docs:
            chunk_id = doc.metadata.get("chunk_id", doc.page_content[:50])
            if chunk_id not in seen:
                seen.add(chunk_id)
                unique_docs.append(doc)

        retrieved[area] = unique_docs
        logger.info(f"  📚 {area}: retrieved {len(unique_docs)} unique chunks")

    return retrieved


def format_context(retrieved_docs: dict[str, list[Document]]) -> str:
    """
    Format retrieved docs into context string for LLM.
    """
    context_parts = []

    for area, docs in retrieved_docs.items():
        if not docs:
            continue
        context_parts.append(f"\n=== {area.upper()} CLAUSES ===")
        for doc in docs:
            context_parts.append(f"[Source: {doc.metadata.get('filename', 'unknown')}]")
            context_parts.append(doc.page_content)
            context_parts.append("")

    return "\n".join(context_parts)


def research_agent(state: dict) -> dict:
    """
    Retrieves relevant clauses for each risk area
    and generates structured risk findings.
    """
    logger.info("\n🔬 Running Research Agent...")

    triage = state.get("triage", {})
    risk_areas = triage.get("risk_areas", ["liability"])

    logger.info(f"  🎯 Investigating risk areas: {risk_areas}")

    # Select the corpus to search. The per-upload flow puts an isolated Qdrant
    # collection + BM25 index in the state so this contract is analyzed against
    # its OWN clauses, not whatever was previously indexed.
    collection_name = state.get("collection") or COLLECTION_NAME
    bm25, chunks_metadata = None, None
    bm25_path = state.get("bm25_path")
    if bm25_path:
        bm25, chunks_metadata = load_bm25(bm25_path, state.get("bm25_meta_path"))

    # 1. Retrieve relevant chunks per risk area
    retrieved_docs = retrieve_for_risk_areas(
        risk_areas, collection_name, bm25, chunks_metadata
    )

    # 2. Format into context
    context = format_context(retrieved_docs)

    if not context.strip():
        logger.error("  ❌ No relevant context retrieved")
        state["research"] = {"error": "No context retrieved"}
        state["next"] = "report"
        return state

    # 3. Generate risk analysis
    from langchain_core.output_parsers import PydanticOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    llm = get_chat_model(temperature=0)
    parser = PydanticOutputParser(pydantic_object=ResearchOutput)
    prompt = ChatPromptTemplate.from_template(RESEARCH_PROMPT)

    messages = prompt.format_messages(
        context=context,
        risk_areas=", ".join(risk_areas),
        format_instructions=parser.get_format_instructions()
    )

    logger.info("  🤖 Generating risk analysis...")
    response = llm.invoke(messages)
    accumulate_usage(state, response)

    try:
        research = parser.parse(response.content)
    except OutputParserException as e:
        logger.error(f"  ⚠️ Parser error: {e}")
        state["research"] = {"error": str(e), "raw": response.content}
        state["next"] = "report"
        return state

    # 4. Update state
    state["research"] = research.model_dump()
    state["next"] = "report"

    # 5. Print summary
    logger.info(f"\n  📋 Summary: {research.summary[:150]}...")
    logger.info(f"  🚨 Overall risk: {research.overall_risk}")
    logger.info(f"  ✅ Recommended action: {research.recommended_action}")
    logger.info(f"\n  📊 Findings ({len(research.findings)} total):")
    for f in research.findings:
        logger.info(f"    [{f.risk_level.upper()}] {f.clause_type}: {f.finding[:100]}...")

    return state


if __name__ == "__main__":
    configure_logging()
    import json

    # Load service agreement for testing
    with open("./data/processed/service-agreement-01.pdf_parsed.json", "r") as f:
        elements = json.load(f)

    document_text = "\n".join([
        el["content"] for el in elements
        if el["type"] in ["NarrativeText", "Title", "ListItem"]
        and el["content"].strip()
    ])

    # Simulate state coming from triage agent
    state = {
        "document_text": document_text,
        "triage": {
            "document_type": "ServiceAgreement",
            "complexity": "high",
            "risk_areas": ["payment", "termination", "liability", "IP", "confidentiality"],
            "requires_human": True,
            "reasoning": "High value contract with multiple risk areas"
        }
    }

    result = research_agent(state)

    logger.info(f"\n{'='*60}")
    logger.info("FULL RESEARCH OUTPUT")
    logger.info(f"{'='*60}")
    logger.info(json.dumps(result["research"], indent=2))