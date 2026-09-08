"""
End-to-end test of the /analyze -> /approve flow with the LLM agents mocked
out. This is what actually exercises the Tier-1 fix: the original code called
input() inside the human_gate node, which would hang forever if triggered
through the API. Here we drive the full HTTP flow and confirm it completes.
"""
import importlib

import pytest
from fastapi.testclient import TestClient

import contractlens.agents.graph as graph_module
import contractlens.ingestion.parser as parser_module


def _fake_triage_agent(state):
    state["triage"] = {
        "document_type": "ServiceAgreement",
        "complexity": "high",
        "risk_areas": ["payment"],
        "requires_human": True,
        "reasoning": "high value contract",
    }
    state["next"] = "human_gate"
    return state


# Records the corpus each research call actually saw, so tests can assert that
# every upload is analyzed against its OWN isolated collection.
SEEN_COLLECTIONS = []


def _fake_research_agent(state):
    SEEN_COLLECTIONS.append(state.get("collection"))
    state["research"] = {
        "summary": "Contract looks standard.",
        "findings": [],
        "overall_risk": "medium",
        "recommended_action": "Proceed with minor changes.",
    }
    state["next"] = "report"
    return state


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTRACTLENS_API_KEY", "test-api-key")
    monkeypatch.chdir(tmp_path)
    SEEN_COLLECTIONS.clear()

    monkeypatch.setattr(graph_module, "triage_agent", _fake_triage_agent)
    monkeypatch.setattr(graph_module, "research_agent", _fake_research_agent)
    monkeypatch.setattr(
        graph_module, "load_document_node",
        lambda state: {**state, "document_text": "some contract text"}
    )
    monkeypatch.setattr(parser_module, "parse_document", lambda *a, **k: None)

    import contractlens.api.main as main
    importlib.reload(main)
    monkeypatch.setattr(main, "graph", graph_module.build_graph(interactive=False))

    # Stub out chunking + indexing (they need embeddings + a live Qdrant).
    monkeypatch.setattr(main, "chunk_document", lambda *a, **k: [])
    monkeypatch.setattr(main, "get_qdrant_client", lambda *a, **k: object())
    monkeypatch.setattr(main, "create_collection", lambda *a, **k: None)
    monkeypatch.setattr(main, "build_vector_index", lambda *a, **k: None)
    monkeypatch.setattr(main, "build_bm25_index", lambda *a, **k: None)
    monkeypatch.setattr(main, "delete_collection", lambda *a, **k: None)

    return TestClient(main.app)


def test_analyze_then_approve_completes_without_hanging(client):
    resp = client.post(
        "/analyze",
        headers={"X-API-Key": "test-api-key"},
        files={"file": ("contract.pdf", b"%PDF-1.4 fake pdf body", "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending_approval"
    thread_id = body["thread_id"]

    resp = client.get(f"/status/{thread_id}", headers={"X-API-Key": "test-api-key"})
    assert resp.json()["status"] == "pending_approval"

    resp = client.post(
        f"/approve/{thread_id}",
        headers={"X-API-Key": "test-api-key"},
        json={"approved": True, "notes": "looks fine"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["report"]["overall_risk"] == "medium"

    # The thread should no longer be pending after approval.
    resp = client.get(f"/status/{thread_id}", headers={"X-API-Key": "test-api-key"})
    assert resp.json()["status"] == "not_found"


def test_analyze_then_reject_stops_pipeline(client):
    resp = client.post(
        "/analyze",
        headers={"X-API-Key": "test-api-key"},
        files={"file": ("contract.pdf", b"%PDF-1.4 fake pdf body", "application/pdf")},
    )
    thread_id = resp.json()["thread_id"]

    resp = client.post(
        f"/approve/{thread_id}",
        headers={"X-API-Key": "test-api-key"},
        json={"approved": False, "notes": "too risky"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["report"] == {}


def test_each_upload_is_analyzed_against_its_own_collection(client):
    """
    Regression test for the per-upload isolation fix: two uploads must each be
    researched against their own thread-specific Qdrant collection, never a
    shared/stale one.
    """
    SEEN_COLLECTIONS.clear()

    r1 = client.post(
        "/analyze",
        headers={"X-API-Key": "test-api-key"},
        files={"file": ("a.pdf", b"%PDF-1.4 contract A", "application/pdf")},
    )
    r2 = client.post(
        "/analyze",
        headers={"X-API-Key": "test-api-key"},
        files={"file": ("b.pdf", b"%PDF-1.4 contract B", "application/pdf")},
    )

    tid1 = r1.json()["thread_id"]
    tid2 = r2.json()["thread_id"]

    # Approve both so the research agent runs for each.
    for tid in (tid1, tid2):
        client.post(
            f"/approve/{tid}",
            headers={"X-API-Key": "test-api-key"},
            json={"approved": True, "notes": "ok"},
        )

    # Each research call saw its own thread-specific collection, and they differ.
    assert f"contractlens_{tid1}" in SEEN_COLLECTIONS
    assert f"contractlens_{tid2}" in SEEN_COLLECTIONS
    assert tid1 != tid2
