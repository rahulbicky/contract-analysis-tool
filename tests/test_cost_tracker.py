import importlib

import contractlens.api.cost_tracker as cost_tracker


def test_track_request_writes_real_token_counts(tmp_path, monkeypatch):
    log_path = tmp_path / "cost_log.json"
    monkeypatch.setattr(cost_tracker, "COST_LOG_PATH", str(log_path))

    cost_tracker.track_request(
        thread_id="t1",
        filename="contract.pdf",
        elapsed=1.5,
        requires_human=True,
        input_tokens=1234,
        output_tokens=321,
    )

    summary = cost_tracker.get_cost_summary()
    assert summary["total_requests"] == 1
    assert summary["total_tokens"] == 1234 + 321
    assert summary["requests_requiring_human"] == 1
    assert summary["total_cost_usd"] > 0


def test_track_request_defaults_to_zero_tokens_when_not_provided(tmp_path, monkeypatch):
    log_path = tmp_path / "cost_log.json"
    monkeypatch.setattr(cost_tracker, "COST_LOG_PATH", str(log_path))

    cost_tracker.track_request(
        thread_id="t2",
        filename="contract.pdf",
        elapsed=0.5,
        requires_human=False,
    )

    summary = cost_tracker.get_cost_summary()
    assert summary["total_tokens"] == 0
    assert summary["total_cost_usd"] == 0.0


def test_get_cost_summary_with_no_log_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cost_tracker, "COST_LOG_PATH", str(tmp_path / "missing.json"))
    summary = cost_tracker.get_cost_summary()
    assert summary == {"total_requests": 0, "total_cost_usd": 0.0}
