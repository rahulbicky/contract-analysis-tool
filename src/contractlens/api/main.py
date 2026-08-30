import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import uuid
import time
from fastapi import FastAPI, UploadFile, File, HTTPException, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contractlens.agents.graph import build_graph, ContractState
from contractlens.api.cost_tracker import track_request, get_cost_summary
from contractlens.ingestion.chunker import chunk_document
from contractlens.ingestion.indexer import (
    get_qdrant_client, create_collection, build_vector_index,
    build_bm25_index, delete_collection,
)
from dotenv import load_dotenv
import logging
from contractlens.core.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

load_dotenv()

API_KEY = os.environ.get("CONTRACTLENS_API_KEY")
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CONTRACTLENS_ALLOWED_ORIGINS", "http://localhost:8501").split(",")
    if origin.strip()
]
MAX_UPLOAD_BYTES = int(os.environ.get("CONTRACTLENS_MAX_UPLOAD_MB", "20")) * 1024 * 1024
PDF_MAGIC_BYTES = b"%PDF-"

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="ContractLens API",
    description="Autonomous Contract Risk Analysis",
    version="1.0.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"]
)


async def require_api_key(key: str = Security(api_key_header)):
    """Reject unauthenticated requests. Set CONTRACTLENS_API_KEY to enable."""
    if not API_KEY:
        # No key configured: fail closed rather than silently allowing all traffic.
        raise HTTPException(status_code=503, detail="Server is missing CONTRACTLENS_API_KEY configuration")
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Pre-loading models...")
    from contractlens.retrieval.reranker import get_reranker
    from contractlens.retrieval.hybrid import get_qdrant
    from contractlens.core.llm import get_embeddings
    get_reranker()      # loads cross-encoder once
    get_embeddings()    # loads local embedding model once
    get_qdrant()        # opens the shared Qdrant connection once
    logger.info("✅ Models ready")


# Single graph instance — interactive=False so human_gate never blocks on input()
# and instead pauses (interrupt_before) until /approve is called.
graph = build_graph(interactive=False)

# In-memory state store for human-in-the-loop
pending_approvals = {}


def _cleanup_corpus(state: dict):
    """
    Remove a request's isolated Qdrant collection and on-disk BM25 index once
    the analysis is finished, so per-upload data doesn't accumulate.
    """
    collection = state.get("collection")
    if collection:
        try:
            delete_collection(get_qdrant_client(), collection)
        except Exception:
            logger.exception(f"Failed to delete collection {collection}")
    for path_key in ("bm25_path", "bm25_meta_path"):
        p = state.get(path_key)
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                logger.warning(f"Could not remove {p}")


# ── Request/Response Models ────────────────────────────────
class AnalyzeResponse(BaseModel):
    thread_id: str
    status: str                # "completed" or "pending_approval"
    triage: dict
    report: dict = None
    message: str


class ApproveRequest(BaseModel):
    approved: bool
    notes: str = ""


class ApproveResponse(BaseModel):
    thread_id: str
    status: str
    report: dict


# ── Routes ─────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "name": "ContractLens",
        "version": "1.0.0",
        "status": "running"
    }


@app.post("/analyze", response_model=AnalyzeResponse, dependencies=[Security(require_api_key)])
@limiter.limit("10/minute")
async def analyze_contract(request: Request, file: UploadFile = File(...)):
    """
    Upload a contract PDF and run triage + research pipeline.
    Returns immediately if no human review needed.
    Pauses at human gate if required.
    """
    # Validate file extension
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported"
        )

    thread_id = str(uuid.uuid4())
    start_time = time.time()

    content = await file.read()

    # Enforce a size limit before writing anything to disk.
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds max upload size of {MAX_UPLOAD_BYTES // (1024 * 1024)}MB"
        )

    # Validate real file type via magic bytes, not just the extension.
    if not content.startswith(PDF_MAGIC_BYTES):
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid PDF"
        )

    # Save uploaded file — use /tmp so this works on Render (read-only /app)
    tmp_dir = os.environ.get("DATA_DIR", "/tmp/contractlens")
    upload_path = os.path.join(tmp_dir, "raw", f"upload_{thread_id}.pdf")
    os.makedirs(os.path.join(tmp_dir, "raw"), exist_ok=True)

    with open(upload_path, "wb") as f:
        f.write(content)

    # parse_document is imported lazily because it pulls in `unstructured`.
    from contractlens.ingestion.parser import parse_document

    # Isolated per-upload corpus so this contract is analyzed against its OWN
    # clauses, not whatever was previously indexed.
    processed_dir = os.path.join(tmp_dir, "processed")
    os.makedirs(processed_dir, exist_ok=True)
    parsed_path = os.path.join(processed_dir, f"upload_{thread_id}_parsed.json")
    collection = f"contractlens_{thread_id}"
    bm25_path = os.path.join(processed_dir, f"{thread_id}_bm25.pkl")
    bm25_meta_path = os.path.join(processed_dir, f"{thread_id}_bm25_meta.json")

    try:
        # 1. Parse the PDF into structured elements.
        parse_document(
            upload_path,
            output_dir=processed_dir,
            strategy="fast"        # much faster, good enough for most contracts
        )

        # 2. Chunk and index THIS document into its own collection + BM25 index.
        chunks = chunk_document(parsed_path, output_dir=processed_dir)
        qdrant = get_qdrant_client()
        create_collection(qdrant, collection)
        build_vector_index(qdrant, chunks, collection)
        build_bm25_index(chunks, bm25_path, bm25_meta_path)

        # 3. Run graph — stops at human gate if needed
        config = {"configurable": {"thread_id": thread_id}}

        initial_state: ContractState = {
            "document_path": parsed_path,
            "document_text": "",
            "triage": None,
            "human_approved": None,
            "human_notes": None,
            "research": None,
            "report": None,
            "next": None,
            "error": None,
            "collection": collection,
            "bm25_path": bm25_path,
            "bm25_meta_path": bm25_meta_path,
        }

        final_state = graph.invoke(initial_state, config)

        elapsed = round(time.time() - start_time, 2)

        # Track cost using actual token usage reported by the LLM calls
        token_usage = final_state.get("token_usage") or {}
        track_request(
            thread_id=thread_id,
            filename=file.filename,
            elapsed=elapsed,
            requires_human=final_state.get("triage", {}).get("requires_human", False),
            input_tokens=token_usage.get("input_tokens", 0),
            output_tokens=token_usage.get("output_tokens", 0)
        )

        # Check if stopped at human gate
        triage = final_state.get("triage", {})
        if triage.get("requires_human") and final_state.get("human_approved") is None:
            # Keep the isolated corpus alive — /approve resumes research against it.
            pending_approvals[thread_id] = final_state
            return AnalyzeResponse(
                thread_id=thread_id,
                status="pending_approval",
                triage=triage,
                message=f"Human review required. POST /approve/{thread_id} to continue."
            )

        # Completed in one shot — the corpus is no longer needed.
        _cleanup_corpus(final_state)
        return AnalyzeResponse(
            thread_id=thread_id,
            status="completed",
            triage=triage,
            report=final_state.get("report"),
            message=f"Analysis complete in {elapsed}s"
        )

    except Exception:
        logger.exception(f"Failed to analyze contract for thread {thread_id}")
        _cleanup_corpus({
            "collection": collection,
            "bm25_path": bm25_path,
            "bm25_meta_path": bm25_meta_path,
        })
        raise HTTPException(status_code=500, detail="Failed to analyze contract")


@app.post("/approve/{thread_id}", response_model=ApproveResponse, dependencies=[Security(require_api_key)])
async def approve_contract(thread_id: str, request: ApproveRequest):
    """
    Approve or reject a contract pending human review.
    Resumes the pipeline after human gate.
    """
    if thread_id not in pending_approvals:
        raise HTTPException(
            status_code=404,
            detail=f"No pending approval found for thread {thread_id}"
        )

    state = pending_approvals[thread_id]
    tokens_before = dict(state.get("token_usage") or {"input_tokens": 0, "output_tokens": 0})

    config = {"configurable": {"thread_id": thread_id}}
    start_time = time.time()

    # The graph is paused (interrupt_before=["human_gate"]) — apply the human's
    # decision to the checkpointed state, then resume with invoke(None, ...).
    # Passing a new value straight to invoke() would only overwrite state and
    # re-halt at the same interrupt instead of advancing past it.
    graph.update_state(config, {
        "human_approved": request.approved,
        "human_notes": request.notes or ("Approved" if request.approved else "Rejected")
    })
    final_state = graph.invoke(None, config)

    del pending_approvals[thread_id]

    # Track the incremental cost of the post-approval research call.
    tokens_after = final_state.get("token_usage") or {}
    track_request(
        thread_id=thread_id,
        filename=f"approve_{thread_id}",
        elapsed=round(time.time() - start_time, 2),
        requires_human=True,
        input_tokens=tokens_after.get("input_tokens", 0) - tokens_before.get("input_tokens", 0),
        output_tokens=tokens_after.get("output_tokens", 0) - tokens_before.get("output_tokens", 0)
    )

    # Analysis is finished (approved or rejected) — drop the isolated corpus.
    _cleanup_corpus(state)

    return ApproveResponse(
        thread_id=thread_id,
        status="completed" if request.approved else "rejected",
        report=final_state.get("report") or {}
    )


@app.get("/status/{thread_id}", dependencies=[Security(require_api_key)])
def get_status(thread_id: str):
    """Check if a thread is pending approval."""
    if thread_id in pending_approvals:
        triage = pending_approvals[thread_id].get("triage", {})
        return {
            "thread_id": thread_id,
            "status": "pending_approval",
            "triage": triage
        }
    return {"thread_id": thread_id, "status": "not_found"}


@app.get("/costs", dependencies=[Security(require_api_key)])
def get_costs():
    """Get cost summary for all requests."""
    return get_cost_summary()


@app.get("/health")
def health():
    return {"status": "healthy"}