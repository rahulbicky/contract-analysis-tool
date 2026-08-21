# ContractLens — Autonomous Contract Risk Analysis

An end-to-end multi-agent system that reads contracts, identifies risk clauses, and generates structured risk reports — with human-in-the-loop oversight for high-stakes documents.

---

## What It Does

Most "chat with PDF" tools stop at answering questions. ContractLens goes further:

- **Parses** contracts preserving tables, headings, and clause structure
- **Indexes** documents using hybrid vector + keyword search
- **Triages** document type, complexity, and risk areas automatically
- **Pauses for human approval** on high-value or complex contracts
- **Retrieves** relevant clauses per risk area using reranked hybrid search
- **Generates** a structured risk report with HIGH / MEDIUM / LOW findings
- **Tracks** cost per analysis and exposes a REST API

---

## Architecture

```mermaid
flowchart TD
    Upload["📄 PDF Upload<br/>FastAPI + Streamlit"]

    subgraph Ingestion["Ingestion Layer"]
        direction LR
        Parser["Parser<br/><i>unstructured</i>"]
        Chunker["Chunker<br/>semantic + table-aware"]
        Indexer["Indexer<br/>Qdrant + BM25"]
        Parser --> Chunker --> Indexer
    end

    subgraph Retrieval["Retrieval Layer"]
        direction LR
        Hybrid["Hybrid Search<br/>vector + BM25 + RRF"]
        Reranker["Cross-Encoder Reranker<br/>ms-marco-MiniLM-L-6-v2"]
        Hybrid --> Reranker
    end

    subgraph Agents["Agent Orchestration — LangGraph"]
        direction LR
        Triage["Triage Agent<br/>classify type / complexity / risk areas"]
        Gate{"Human Gate<br/>high-value or complex?"}
        Research["Research Agent<br/>retrieve + analyze per risk area"]
        Triage --> Gate
        Gate -->|approved| Research
        Gate -->|auto-clear| Research
        Gate -->|rejected| Stopped["Stopped"]
    end

    Report["📋 Risk Report<br/>HIGH / MEDIUM / LOW findings"]

    Upload --> Ingestion
    Ingestion --> Retrieval
    Retrieval --> Agents
    Research --> Report

    Groq[("Groq<br/>llama-3.3-70b")] -.-> Triage
    Groq -.-> Research
    QdrantDB[("Qdrant<br/>local or Cloud")] -.-> Indexer
    QdrantDB -.-> Hybrid
```

---

## Benchmark Results

Evaluation across 15 test cases (easy / medium / hard) covering 6 clause categories.

### Overall

| Metric | Baseline (pure vector) | Final (hybrid + rerank) | Change |
|---|---|---|---|
| Exact Match | 0.178 | **0.867** | +387% |
| Faithfulness | 0.793 | **0.793** | — |
| Answer Relevancy | 0.860 | **0.860** | — |
| Context Precision | 0.267 | **0.271** | +1.5% |

### By Difficulty

| Difficulty | Exact Match | Faithfulness | Answer Relevancy |
|---|---|---|---|
| Easy | 1.000 | 0.940 | 1.000 |
| Medium | 0.875 | 0.775 | 0.862 |
| Hard | 0.500 | 0.500 | 0.500 |

### By Category

| Category | Exact Match | Faithfulness |
|---|---|---|
| Payment | 1.000 | 1.000 |
| Liability | 1.000 | 1.000 |
| Termination | 1.000 | 1.000 |
| Compliance | 1.000 | 0.850 |
| Confidentiality | 0.750 | 0.550 |
| IP | 0.500 | 0.500 |

> Hard queries (cross-document comparison, negation) remain the known limitation. Context precision of 0.271 indicates retrieval casts a wide net — a targeted retrieval strategy per risk area is the next improvement.

---

## Tech Stack

| Component | Technology |
|---|---|
| PDF Parsing | `unstructured` (`hi_res` + OCR by default, `fast` strategy also supported) |
| Vector Store | Qdrant — local (`QDRANT_HOST`/`QDRANT_PORT`) or Qdrant Cloud (`QDRANT_URL`/`QDRANT_API_KEY`) |
| Keyword Search | BM25 (rank-bm25) |
| Result Fusion | Reciprocal Rank Fusion (RRF) |
| Reranking | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| LLM | Groq — `llama-3.3-70b-versatile` by default (`src/contractlens/core/llm.py`) |
| Agent Framework | LangGraph state machine |
| Embeddings | Local, via sentence-transformers — `all-MiniLM-L6-v2` by default, no API cost |
| API | FastAPI |
| UI | Streamlit |
| Evaluation | Custom metrics + LLM-as-judge |

> Chat/reasoning runs on Groq and embeddings run locally, so there's no OpenAI
> dependency anywhere in this stack — `src/contractlens/core/llm.py` is the single place both
> are wired up if you want to swap providers.

---

## Project Structure

```
contractlens/
├── docs/
│   └── DEPLOY.md               # Render deployment guide
├── data/
│   ├── raw/                    # Original PDFs
│   ├── processed/              # Parsed JSON, chunks, indexes
│   └── evaluation/             # Test cases and results
├── src/
│   └── contractlens/           # Package namespace
│       ├── core/               # LLM, logging, token tracking
│       │   ├── llm.py
│       │   ├── logging_config.py
│       │   └── token_usage.py
│       ├── ingestion/          # PDF parsing, chunking, indexing
│       │   ├── parser.py
│       │   ├── chunker.py
│       │   └── indexer.py
│       ├── retrieval/          # Hybrid search & cross-encoder reranker
│       │   ├── hybrid.py
│       │   └── reranker.py
│       ├── agents/             # LangGraph state machine & agents
│       │   ├── triage.py
│       │   ├── research.py
│       │   └── graph.py
│       ├── evaluation/         # Metrics & benchmark runner
│       │   ├── testset.py
│       │   ├── metrics.py
│       │   └── runner.py
│       └── api/                # FastAPI backend & cost tracker
│           ├── main.py
│           └── cost_tracker.py
├── ui/
│   └── app.py                  # Streamlit interface
├── tests/                      # Pytest suite
├── requirements.txt
└── .env
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/RahulBicky/contractlens
cd contractlens
python -m venv env
env\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 2. System dependencies

The default parsing strategy (`hi_res`, used by `parse_all_documents()` /
`python -m contractlens.ingestion.parser`) runs OCR and **requires Tesseract +
Poppler on PATH** — without them it fails with `TesseractNotFoundError`.

```bash
# Windows — install from links below
# Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki
# Poppler: https://github.com/oschwartz10612/poppler-windows/releases

# Mac
brew install tesseract poppler

# Ubuntu
sudo apt-get install tesseract-ocr poppler-utils
```

If you don't want to install these, call `parse_document(..., strategy="fast")`
instead — it skips OCR and works on any machine, at the cost of not picking
up text from scanned/image-only pages or table structure as reliably.

### 3. Environment variables

```bash
cp .env.example .env
```

Then fill in `.env` (see `.env.example` for the fully annotated version):

```bash
# Groq (chat / reasoning) — free tier key at https://console.groq.com
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Embeddings run locally via sentence-transformers — no key needed
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIM=384

# Qdrant — either local...
QDRANT_HOST=localhost
QDRANT_PORT=6333
# ...or Qdrant Cloud (leave QDRANT_HOST/PORT unset if using this)
# QDRANT_URL=https://xxxxxxxx.qdrant.io
# QDRANT_API_KEY=

# Required — the API refuses all requests to protected endpoints without this
CONTRACTLENS_API_KEY=your_own_arbitrary_key
CONTRACTLENS_ALLOWED_ORIGINS=http://localhost:8501
CONTRACTLENS_MAX_UPLOAD_MB=20
CONTRACTLENS_API_URL=http://localhost:8000

# Optional
LANGSMITH_API_KEY=
LANGSMITH_TRACING=false
```

### 4. Add PDF contracts

Place PDF contracts in `data/raw/` (gitignored). The system works best with:
- NDA / Non-Disclosure Agreements
- Service / Vendor Agreements
- Employment Contracts

`data/raw/ServiceAgreement_IntegrityFunds.pdf` is a real sample SEC-filed
service agreement already sitting there locally (this directory is gitignored,
so it won't be pushed) to try the pipeline against immediately.

More sample contracts available from [SEC EDGAR](https://efts.sec.gov/LATEST/search-index?q=%22service+agreement%22&forms=EX-10).

---

## Usage

### Step 1 — Ingest documents

```bash
# Parse PDFs
python -m contractlens.ingestion.parser

# Chunk parsed documents
python -m contractlens.ingestion.chunker

# Build vector + BM25 index
python -m contractlens.ingestion.indexer
```

### Step 2 — Run the full pipeline (CLI)

```bash
python -m contractlens.agents.graph
```

### Step 3 — Run the API + UI

```bash
# Terminal 1 — FastAPI
uvicorn contractlens.api.main:app --reload --port 8000 --app-dir src

# Terminal 2 — Streamlit
streamlit run ui/app.py
```

Open `http://localhost:8501` and upload a contract.

### Step 4 — Run evaluation

```bash
python -m contractlens.evaluation.runner
```

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/analyze` | POST | Upload PDF, run triage + research |
| `/approve/{thread_id}` | POST | Approve or reject human gate |
| `/status/{thread_id}` | GET | Check pipeline status |
| `/costs` | GET | Cost summary for all requests |
| `/health` | GET | Health check |

### Example

```bash
# Upload contract
curl -X POST http://localhost:8000/analyze \
  -F "file=@contract.pdf"

# Returns:
{
  "thread_id": "abc-123",
  "status": "pending_approval",
  "triage": {
    "document_type": "ServiceAgreement",
    "complexity": "high",
    "risk_areas": ["payment", "liability", "termination", "IP"]
  }
}

# Approve
curl -X POST http://localhost:8000/approve/abc-123 \
  -H "Content-Type: application/json" \
  -d '{"approved": true, "notes": "Standard contract"}'
```

---

## Key Design Decisions

**Why hybrid search over pure vector search?**
Pure vector search misses exact keyword matches — contract clause numbers, specific dollar amounts, legal terms. BM25 catches these. RRF fusion combines both rankings without requiring score normalization.

**Why semantic chunking over fixed-size chunking?**
Contracts have variable-length clauses. Fixed-size chunks cut mid-sentence. Semantic chunking splits on meaning boundaries, keeping clauses intact. Tables are never split regardless of size.

**Why cross-encoder reranking?**
Bi-encoders (used in vector search) encode query and document independently. Cross-encoders see both together, giving dramatically better relevance judgments at the cost of speed. Running reranking only on the top-20 candidates keeps latency acceptable.

**Why human-in-the-loop?**
High-value contracts ($100k+) with multiple risk areas should never be auto-processed in production. LangGraph's checkpoint system allows the pipeline to pause mid-execution and resume after human approval without losing state.

---

## Evaluation Methodology

Custom metrics rather than off-the-shelf RAGAS:

- **Exact Match** — key facts from ground truth present in prediction (normalized for number formats)
- **Faithfulness** — LLM-as-judge: does every claim in the answer appear in retrieved context?
- **Answer Relevancy** — LLM-as-judge: does the answer address the question?
- **Context Precision** — are retrieved chunks actually useful for answering?

Test set: 15 hand-labeled cases (5 easy, 7 medium, 3 hard) across payment, liability, termination, IP, confidentiality, and compliance categories. Includes one cross-document comparison case.

---

## Known Limitations

- Context precision (0.271) was low because retrieval cast a wide net across
  all documents rather than filtering by document when the query is
  document-specific. **Partially addressed**: `hybrid_search()` /
  `retrieve_and_rerank()` now accept a `filename_filter` (backed by a Qdrant
  payload index on `filename`, set up in `indexer.py`), and `runner.py` passes
  each test case's known source document through automatically. Verified live
  with two real indexed contracts: without the filter, an unrelated
  document's chunks measurably leaked into the top candidates for a
  same-corpus query; with the filter, they're excluded entirely and
  faithfulness improved (0.2 → 0.6 on that query). Context precision itself
  didn't move on that single test query — the LLM-judge scores per-chunk
  usefulness somewhat coarsely on broad questions — so this should be
  re-validated across the full 15-question set with the original corpus
  before treating it as fully resolved; the cross-document leakage it targets
  is confirmed real and confirmed fixed at the retrieval layer.
- Hard queries (cross-document comparison, negation detection) score 0.50 — requires multi-hop reasoning not currently implemented
- Reranker model (90MB) loads on first request — pre-loading via FastAPI startup event mitigates this after first run
- Cost tracking uses estimated token counts rather than actual API usage

---

## Requirements

See `requirements.txt` for exact pinned versions. Summary:

```
# Core LLM & LangChain — chat on Groq, embeddings local (no OpenAI dependency)
langchain, langchain-groq, langchain-huggingface, langchain-community, langchain-experimental, langgraph

# Vector database
qdrant-client

# PDF parsing
unstructured[pdf], unstructured-inference, pikepdf, pdfminer.six

# Retrieval
rank-bm25, sentence-transformers

# Evaluation
ragas, datasets, pandas

# API
fastapi, uvicorn, python-multipart, slowapi

# UI
streamlit

# Utilities / observability
python-dotenv, pydantic, langsmith
```

---

## License

MIT