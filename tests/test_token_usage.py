from types import SimpleNamespace

from contractlens.core.token_usage import accumulate_usage


def test_accumulate_usage_initializes_totals_on_first_call():
    state = {}
    response = SimpleNamespace(usage_metadata={"input_tokens": 100, "output_tokens": 20})

    accumulate_usage(state, response)

    assert state["token_usage"] == {"input_tokens": 100, "output_tokens": 20}


def test_accumulate_usage_adds_across_multiple_calls():
    state = {"token_usage": {"input_tokens": 100, "output_tokens": 20}}
    response = SimpleNamespace(usage_metadata={"input_tokens": 50, "output_tokens": 10})

    accumulate_usage(state, response)

    assert state["token_usage"] == {"input_tokens": 150, "output_tokens": 30}


def test_accumulate_usage_handles_missing_usage_metadata():
    state = {}
    response = SimpleNamespace()  # no usage_metadata attribute at all

    accumulate_usage(state, response)

    assert state["token_usage"] == {"input_tokens": 0, "output_tokens": 0}
