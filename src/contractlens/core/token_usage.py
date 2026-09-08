def accumulate_usage(state: dict, response) -> None:
    """
    Add a chat model response's real usage_metadata (input/output tokens) onto
    state["token_usage"], so cost tracking reflects actual API usage instead
    of a hardcoded estimate.
    """
    usage = getattr(response, "usage_metadata", None) or {}
    totals = state.get("token_usage") or {"input_tokens": 0, "output_tokens": 0}
    totals["input_tokens"] += usage.get("input_tokens", 0)
    totals["output_tokens"] += usage.get("output_tokens", 0)
    state["token_usage"] = totals
