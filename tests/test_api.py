import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("CONTRACTLENS_API_KEY", "test-api-key")
    import contractlens.api.main as main

    importlib.reload(main)
    return TestClient(main.app)


def test_health_is_public(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


def test_root_is_public(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "ContractLens"


@pytest.mark.parametrize("path", ["/costs", "/status/some-thread"])
def test_protected_routes_reject_missing_key(client, path):
    resp = client.get(path)
    assert resp.status_code == 401


@pytest.mark.parametrize("path", ["/costs", "/status/some-thread"])
def test_protected_routes_reject_wrong_key(client, path):
    resp = client.get(path, headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


def test_costs_accepts_correct_key(client):
    resp = client.get("/costs", headers={"X-API-Key": "test-api-key"})
    assert resp.status_code == 200
    assert "total_requests" in resp.json()


def test_status_unknown_thread_with_correct_key(client):
    resp = client.get("/status/unknown-thread", headers={"X-API-Key": "test-api-key"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_found"


def test_analyze_rejects_non_pdf_extension(client):
    resp = client.post(
        "/analyze",
        headers={"X-API-Key": "test-api-key"},
        files={"file": ("contract.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400
    assert "PDF" in resp.json()["detail"]


def test_analyze_rejects_fake_pdf_content(client):
    resp = client.post(
        "/analyze",
        headers={"X-API-Key": "test-api-key"},
        files={"file": ("contract.pdf", b"not really a pdf", "application/pdf")},
    )
    assert resp.status_code == 400
    assert "valid PDF" in resp.json()["detail"]


def test_analyze_rejects_oversized_upload(client, monkeypatch):
    import contractlens.api.main as main

    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 10)
    resp = client.post(
        "/analyze",
        headers={"X-API-Key": "test-api-key"},
        files={"file": ("contract.pdf", b"%PDF-1.4" + b"x" * 100, "application/pdf")},
    )
    assert resp.status_code == 413


def test_analyze_requires_api_key(client):
    resp = client.post(
        "/analyze",
        files={"file": ("contract.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code == 401


def test_missing_api_key_config_fails_closed(monkeypatch):
    monkeypatch.delenv("CONTRACTLENS_API_KEY", raising=False)
    # Neutralize load_dotenv so a real local .env can't re-populate the key
    # on reload — this test needs a truly empty CONTRACTLENS_API_KEY.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    import contractlens.api.main as main

    importlib.reload(main)
    client = TestClient(main.app)

    resp = client.get("/costs", headers={"X-API-Key": "anything"})
    assert resp.status_code == 503
