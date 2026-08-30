import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, Field
from contractlens.core.token_usage import accumulate_usage
from contractlens.core.llm import get_chat_model
from dotenv import load_dotenv
import logging
from contractlens.core.logging_config import configure_logging

logger = logging.getLogger(__name__)

load_dotenv()


# ── Output Schema ──────────────────────────────────────────
class TriageOutput(BaseModel):
    document_type: str = Field(
        description="Type of contract: NDA, ServiceAgreement, Employment, Lease, SoftwareLicense, Unknown"
    )
    complexity: str = Field(
        description="Complexity level: low, medium, high"
    )
    risk_areas: list[str] = Field(
        description="List of risk areas found: payment, liability, termination, IP, confidentiality, compliance"
    )
    requires_human: bool = Field(
        description="True if document needs human review before processing"
    )
    reasoning: str = Field(
        description="Brief explanation of triage decision"
    )


# ── Prompt ─────────────────────────────────────────────────
TRIAGE_PROMPT = """You are a contract triage specialist.
Analyze the document preview and classify it accurately.
Be thorough — err on the side of finding MORE risk areas, not fewer.

Document Preview:
{document_preview}

Classify this document and identify ALL risk areas present.

Risk area definitions:
- payment: ANY mention of money, fees, invoices, compensation, remuneration
- liability: ANY mention of indemnification, damages, limitations, warranties
- termination: ANY mention of ending, canceling, breach, notice periods
- IP: ANY mention of intellectual property, ownership, work product, inventions
- confidentiality: ANY mention of NDA, trade secrets, disclosure, proprietary
- compliance: ANY mention of laws, regulations, policies, FCPA, government

Complexity rules:
- low: under 5 pages, single topic (e.g. simple NDA)
- medium: 5-15 pages, 2-3 risk areas
- high: 15+ pages OR 3+ risk areas OR involves payments

Mark requires_human=True if ANY of these:
- Document involves ANY payment amount
- Contains 3 or more risk areas
- Document type is Unknown
- Complexity is high

{format_instructions}"""


# ── Agent ──────────────────────────────────────────────────
def get_document_preview(document_text: str, max_chars: int = 3000) -> str:
    """
    Sample from beginning, middle, and end of document.
    Gives triage agent a better overall picture.
    """
    if len(document_text) <= max_chars:
        return document_text

    chunk = max_chars // 3

    beginning = document_text[:chunk]
    middle_start = len(document_text) // 2 - chunk // 2
    middle = document_text[middle_start:middle_start + chunk]
    end = document_text[-chunk:]

    return f"{beginning}\n...\n{middle}\n...\n{end}"

def triage_agent(state: dict) -> dict:
    """
    Classifies contract type, complexity, and risk areas.
    Updates state with triage results.
    """
    logger.info("\n🔍 Running Triage Agent...")

    llm = get_chat_model(temperature=0)      # deterministic output
    parser = PydanticOutputParser(pydantic_object=TriageOutput)
    prompt = ChatPromptTemplate.from_template(TRIAGE_PROMPT)

    document_preview = get_document_preview(state.get("document_text", ""))

    messages = prompt.format_messages(
        document_preview=document_preview,
        format_instructions=parser.get_format_instructions()
    )

    response = llm.invoke(messages)
    accumulate_usage(state, response)

    try:
        triage = parser.parse(response.content)
    except OutputParserException as e:
        logger.error(f"  ⚠️ Parser error: {e}")
        # Fallback triage
        triage = TriageOutput(
            document_type="Unknown",
            complexity="high",
            risk_areas=["liability"],
            requires_human=True,
            reasoning="Failed to parse — defaulting to human review"
        )

    # Update state
    state["triage"] = triage.model_dump()
    state["next"] = "human_gate" if triage.requires_human else "research"

    logger.info(f"  📄 Document type  : {triage.document_type}")
    logger.info(f"  ⚡ Complexity      : {triage.complexity}")
    logger.warning(f"  ⚠️  Risk areas     : {', '.join(triage.risk_areas)}")
    logger.info(f"  👤 Requires human : {triage.requires_human}")
    logger.info(f"  💭 Reasoning      : {triage.reasoning}")
    logger.info(f"  ➡️  Next step      : {state['next']}")

    return state


if __name__ == "__main__":
    configure_logging()
    # Test with both documents
    import json

    test_docs = [
        {
            "name": "NDA",
            "path": "./data/processed/Basic-Non-Disclosure-Agreement_parsed.json"
        },
        {
            "name": "Service Agreement",
            "path": "./data/processed/service-agreement-01.pdf_parsed.json"
        }
    ]

    for doc in test_docs:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing: {doc['name']}")
        logger.info(f"{'='*60}")

        # Load parsed document
        with open(doc["path"], "r") as f:
            elements = json.load(f)

        # Combine text content
        document_text = "\n".join([
            el["content"] for el in elements
            if el["type"] in ["NarrativeText", "Title", "ListItem"]
            and el["content"].strip()
        ])

        # Run triage
        state = {"document_text": document_text}
        result = triage_agent(state)