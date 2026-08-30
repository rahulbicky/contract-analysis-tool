import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from contractlens.agents.triage import triage_agent
from contractlens.agents.research import research_agent
from dotenv import load_dotenv
import logging
from contractlens.core.logging_config import configure_logging

logger = logging.getLogger(__name__)

load_dotenv()


# ── State Definition ───────────────────────────────────────
class ContractState(TypedDict):
    # Input
    document_path: str
    document_text: str

    # Triage output
    triage: Optional[dict]

    # Human gate
    human_approved: Optional[bool]
    human_notes: Optional[str]

    # Research output
    research: Optional[dict]

    # Report output
    report: Optional[dict]

    # Routing
    next: Optional[str]
    error: Optional[str]

    # Actual token usage accumulated across LLM calls (triage + research)
    token_usage: Optional[dict]

    # Per-upload retrieval corpus (isolates each contract's own clauses)
    collection: Optional[str]
    bm25_path: Optional[str]
    bm25_meta_path: Optional[str]


# ── Nodes ──────────────────────────────────────────────────
def load_document_node(state: ContractState) -> ContractState:
    """
    Load document text from parsed JSON.
    """
    logger.info("\n📂 Loading document...")

    document_path = state.get("document_path", "")

    # Convert PDF path to parsed JSON path
    if document_path.endswith(".pdf"):
        filename = os.path.basename(document_path)
        stem = filename.replace(".pdf", "").replace(".pdf", "")
        json_path = f"./data/processed/{stem}_parsed.json"
    else:
        json_path = document_path

    try:
        with open(json_path, "r") as f:
            elements = json.load(f)

        document_text = "\n".join([
            el["content"] for el in elements
            if el["type"] in ["NarrativeText", "Title", "ListItem"]
            and el["content"].strip()
        ])

        state["document_text"] = document_text
        logger.info(f"  ✅ Loaded {len(document_text)} characters")

    except Exception as e:
        state["error"] = f"Failed to load document: {e}"
        state["next"] = END
        logger.error(f"  ❌ Error: {e}")

    return state


def triage_node(state: ContractState) -> ContractState:
    """
    Wrapper around triage_agent for LangGraph.
    """
    return triage_agent(state)


def human_gate_node(state: ContractState) -> ContractState:
    """
    Pause for human review.

    In API mode the graph is compiled with interrupt_before=["human_gate"], so
    this node only runs once the caller has already supplied human_approved via
    /approve — no blocking input() call here.
    In CLI mode (human_approved not yet set) it falls back to interactive input().
    """
    triage = state.get("triage", {})

    if state.get("human_approved") is not None:
        # Resumed after an external approval decision (API /approve flow).
        logger.info("\n" + "="*60)
        logger.info("🛑 HUMAN REVIEW RESULT")
        logger.info("="*60)
        logger.info(f"Approved : {state['human_approved']}")
        logger.info(f"Notes    : {state.get('human_notes')}")
        state["next"] = "research" if state["human_approved"] else "end"
        return state

    logger.info("\n" + "="*60)
    logger.info("🛑 HUMAN REVIEW REQUIRED")
    logger.info("="*60)
    logger.info(f"Document type : {triage.get('document_type')}")
    logger.info(f"Complexity    : {triage.get('complexity')}")
    logger.info(f"Risk areas    : {', '.join(triage.get('risk_areas', []))}")
    logger.info(f"Reasoning     : {triage.get('reasoning')}")
    logger.info("="*60)

    # Interactive approval for CLI testing
    while True:
        response = input("\nApprove for research? (yes/no): ").strip().lower()
        if response in ["yes", "y"]:
            state["human_approved"] = True
            notes = input("Add notes (optional, press Enter to skip): ").strip()
            state["human_notes"] = notes if notes else "Approved"
            logger.info("✅ Approved — proceeding to research")
            break
        elif response in ["no", "n"]:
            state["human_approved"] = False
            state["human_notes"] = input("Reason for rejection: ").strip()
            logger.error("❌ Rejected — stopping pipeline")
            break
        else:
            logger.info("Please enter yes or no")

    state["next"] = "research" if state["human_approved"] else "end"
    return state


def research_node(state: ContractState) -> ContractState:
    """
    Wrapper around research_agent for LangGraph.
    """
    return research_agent(state)


def report_node(state: ContractState) -> ContractState:
    """
    Generate final risk report from research output.
    """
    logger.info("\n📝 Generating Final Report...")

    research = state.get("research", {})
    triage = state.get("triage", {})

    if "error" in research:
        state["report"] = {"error": research["error"]}
        return state

    # Build structured report
    report = {
        "document_type": triage.get("document_type"),
        "complexity": triage.get("complexity"),
        "overall_risk": research.get("overall_risk"),
        "summary": research.get("summary"),
        "recommended_action": research.get("recommended_action"),
        "human_approved": state.get("human_approved"),
        "human_notes": state.get("human_notes"),
        "findings": research.get("findings", []),
        "findings_by_risk": {
            "high": [
                f for f in research.get("findings", [])
                if f.get("risk_level") == "high"
            ],
            "medium": [
                f for f in research.get("findings", [])
                if f.get("risk_level") == "medium"
            ],
            "low": [
                f for f in research.get("findings", [])
                if f.get("risk_level") == "low"
            ]
        }
    }

    state["report"] = report

    # Print report
    logger.info("\n" + "="*60)
    logger.info("CONTRACT RISK REPORT")
    logger.info("="*60)
    logger.info(f"Type          : {report['document_type']}")
    logger.info(f"Complexity    : {report['complexity']}")
    logger.info(f"Overall Risk  : {report['overall_risk'].upper()}")
    logger.info(f"\nSummary:\n{report['summary']}")
    logger.info(f"\nRecommended Action:\n{report['recommended_action']}")

    logger.info(f"\n🚨 HIGH RISK ({len(report['findings_by_risk']['high'])} findings):")
    for f in report["findings_by_risk"]["high"]:
        logger.info(f"  • {f['clause_type'].upper()}: {f['finding'][:120]}...")
        logger.info(f"    → {f['recommendation']}")

    logger.warning(f"\n⚠️  MEDIUM RISK ({len(report['findings_by_risk']['medium'])} findings):")
    for f in report["findings_by_risk"]["medium"]:
        logger.info(f"  • {f['clause_type'].upper()}: {f['finding'][:120]}...")

    logger.info(f"\n✅ LOW RISK ({len(report['findings_by_risk']['low'])} findings):")
    for f in report["findings_by_risk"]["low"]:
        logger.info(f"  • {f['clause_type'].upper()}: {f['finding'][:120]}...")

    # Save report to file
    report_dir = os.environ.get("DATA_DIR", "/tmp/contractlens")
    report_path = os.path.join(report_dir, f"report_{triage.get('document_type', 'unknown')}.json")
    os.makedirs(report_dir, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"\n💾 Report saved to {report_path}")

    return state


# ── Routing Logic ──────────────────────────────────────────
def route_after_triage(state: ContractState) -> str:
    if state.get("error"):
        return END
    return "human_gate" if state.get("triage", {}).get("requires_human") else "research"


def route_after_human_gate(state: ContractState) -> str:
    return "research" if state.get("human_approved") else END


# ── Build Graph ────────────────────────────────────────────
def build_graph(interactive: bool = True):
    """
    Build the LangGraph state machine.

    Flow:
    load_document → triage → [human_gate?] → research → report

    interactive=True (CLI):  human_gate_node blocks on input().
    interactive=False (API): graph pauses before human_gate via interrupt_before,
                              so the caller must resume via /approve without ever
                              hitting a blocking input() call on the server.
    """
    graph = StateGraph(ContractState)

    # Add nodes
    graph.add_node("load_document", load_document_node)
    graph.add_node("triage", triage_node)
    graph.add_node("human_gate", human_gate_node)
    graph.add_node("research", research_node)
    graph.add_node("report", report_node)

    # Entry point
    graph.set_entry_point("load_document")

    # Edges
    graph.add_edge("load_document", "triage")

    # Conditional routing after triage
    graph.add_conditional_edges(
        "triage",
        route_after_triage,
        {
            "human_gate": "human_gate",
            "research": "research",
            END: END
        }
    )

    # Conditional routing after human gate
    graph.add_conditional_edges(
        "human_gate",
        route_after_human_gate,
        {
            "research": "research",
            END: END
        }
    )

    graph.add_edge("research", "report")
    graph.add_edge("report", END)

    # Memory for human-in-the-loop persistence
    memory = MemorySaver()
    interrupt_before = [] if interactive else ["human_gate"]
    return graph.compile(checkpointer=memory, interrupt_before=interrupt_before)


# ── Run ────────────────────────────────────────────────────
if __name__ == "__main__":
    configure_logging()
    graph = build_graph()

    # Test with service agreement (requires human approval)
    logger.info("\n" + "="*60)
    logger.info("CONTRACTIQ — FULL PIPELINE TEST")
    logger.info("="*60)

    config = {"configurable": {"thread_id": "test-001"}}

    initial_state = {
        "document_path": "./data/processed/service-agreement-01.pdf_parsed.json",
        "document_text": "",
        "triage": None,
        "human_approved": None,
        "human_notes": None,
        "research": None,
        "report": None,
        "next": None,
        "error": None
    }

    final_state = graph.invoke(initial_state, config)

    logger.info("\n✅ Pipeline complete")
    logger.info(f"Final next: {final_state.get('next')}")