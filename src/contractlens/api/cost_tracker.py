import json
import os
from datetime import datetime

COST_LOG_PATH = "./data/cost_log.json"

# Approximate LLM cost per 1K tokens. Defaults reflect Groq's paid rate for
# llama-3.3-70b-versatile; on Groq's free tier actual spend is $0, and
# embeddings run locally (sentence-transformers) so they cost nothing.
# Override via env if you switch models or move to a paid plan.
INPUT_COST_PER_1K = float(os.getenv("LLM_INPUT_COST_PER_1K", "0.00059"))
OUTPUT_COST_PER_1K = float(os.getenv("LLM_OUTPUT_COST_PER_1K", "0.00079"))


def track_request(
    thread_id: str,
    filename: str,
    elapsed: float,
    requires_human: bool,
    input_tokens: int = 0,
    output_tokens: int = 0
):
    """
    Log request cost and metadata.
    """
    estimated_cost = (
        (input_tokens / 1000) * INPUT_COST_PER_1K +
        (output_tokens / 1000) * OUTPUT_COST_PER_1K
    )

    entry = {
        "thread_id": thread_id,
        "filename": filename,
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": elapsed,
        "requires_human": requires_human,
        "estimated_cost_usd": round(estimated_cost, 6),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens
    }

    # Load existing log
    logs = []
    if os.path.exists(COST_LOG_PATH):
        with open(COST_LOG_PATH, "r") as f:
            logs = json.load(f)

    logs.append(entry)

    with open(COST_LOG_PATH, "w") as f:
        json.dump(logs, f, indent=2)


def get_cost_summary() -> dict:
    """
    Return cost summary across all requests.
    """
    if not os.path.exists(COST_LOG_PATH):
        return {"total_requests": 0, "total_cost_usd": 0.0}

    with open(COST_LOG_PATH, "r") as f:
        logs = json.load(f)

    total_cost = sum(l["estimated_cost_usd"] for l in logs)
    total_tokens = sum(l["input_tokens"] + l["output_tokens"] for l in logs)

    return {
        "total_requests": len(logs),
        "total_cost_usd": round(total_cost, 4),
        "total_tokens": total_tokens,
        "avg_cost_per_request": round(total_cost / len(logs), 4) if logs else 0,
        "avg_elapsed_seconds": round(
            sum(l["elapsed_seconds"] for l in logs) / len(logs), 2
        ) if logs else 0,
        "requests_requiring_human": sum(1 for l in logs if l["requires_human"])
    }