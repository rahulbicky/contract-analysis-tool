import contractlens.agents.graph as graph_module


def _fake_triage_agent(state):
    state["triage"] = {
        "document_type": "ServiceAgreement",
        "complexity": "high",
        "risk_areas": ["payment"],
        "requires_human": True,
        "reasoning": "test",
    }
    state["next"] = "human_gate"
    return state


def _fake_research_agent(state):
    state["research"] = {
        "summary": "looks fine",
        "findings": [],
        "overall_risk": "low",
        "recommended_action": "none",
    }
    state["next"] = "report"
    return state


def _base_state(document_text="some contract text"):
    return {
        "document_path": "irrelevant",
        "document_text": document_text,
        "triage": None,
        "human_approved": None,
        "human_notes": None,
        "research": None,
        "report": None,
        "next": None,
        "error": None,
    }


def test_api_mode_pauses_before_human_gate_without_blocking(monkeypatch, tmp_path):
    """
    This is the Tier-1 fix under test: build_graph(interactive=False) must never
    call input() — instead it should halt the run before the human_gate node,
    leaving human_approved untouched, so a server request can never hang.
    """
    monkeypatch.setattr(graph_module, "triage_agent", _fake_triage_agent)
    monkeypatch.setattr(graph_module, "research_agent", _fake_research_agent)

    compiled = graph_module.build_graph(interactive=False)
    config = {"configurable": {"thread_id": "test-thread-1"}}

    # document_path points nowhere real, but load_document_node reads a JSON
    # file — bypass it by starting state with document_text already populated
    # and monkeypatching load_document_node to a no-op passthrough.
    monkeypatch.setattr(graph_module, "load_document_node", lambda state: state)
    compiled = graph_module.build_graph(interactive=False)

    result = compiled.invoke(_base_state(), config)

    assert result["human_approved"] is None
    assert result["triage"]["requires_human"] is True
    state_snapshot = compiled.get_state(config)
    assert state_snapshot.next == ("human_gate",)


def test_api_mode_resumes_and_completes_after_approval(monkeypatch):
    monkeypatch.setattr(graph_module, "triage_agent", _fake_triage_agent)
    monkeypatch.setattr(graph_module, "research_agent", _fake_research_agent)
    monkeypatch.setattr(graph_module, "load_document_node", lambda state: state)

    compiled = graph_module.build_graph(interactive=False)
    config = {"configurable": {"thread_id": "test-thread-2"}}

    compiled.invoke(_base_state(), config)

    # Matches how main.py's /approve endpoint resumes a paused thread: apply
    # the decision via update_state, then advance past the interrupt with
    # invoke(None, ...) — invoke(new_dict, ...) alone would just re-halt.
    compiled.update_state(config, {"human_approved": True, "human_notes": "looks good"})
    resumed = compiled.invoke(None, config)

    assert resumed["report"]["overall_risk"] == "low"
    assert resumed["human_approved"] is True


def test_api_mode_stops_after_rejection(monkeypatch):
    monkeypatch.setattr(graph_module, "triage_agent", _fake_triage_agent)
    monkeypatch.setattr(graph_module, "research_agent", _fake_research_agent)
    monkeypatch.setattr(graph_module, "load_document_node", lambda state: state)

    compiled = graph_module.build_graph(interactive=False)
    config = {"configurable": {"thread_id": "test-thread-3"}}

    compiled.invoke(_base_state(), config)
    compiled.update_state(config, {"human_approved": False, "human_notes": "rejecting"})
    resumed = compiled.invoke(None, config)

    assert resumed["report"] is None
    assert resumed["human_approved"] is False


def test_no_human_review_needed_runs_straight_through(monkeypatch):
    def _fake_triage_no_human(state):
        state["triage"] = {
            "document_type": "NDA",
            "complexity": "low",
            "risk_areas": ["confidentiality"],
            "requires_human": False,
            "reasoning": "test",
        }
        state["next"] = "research"
        return state

    monkeypatch.setattr(graph_module, "triage_agent", _fake_triage_no_human)
    monkeypatch.setattr(graph_module, "research_agent", _fake_research_agent)
    monkeypatch.setattr(graph_module, "load_document_node", lambda state: state)

    compiled = graph_module.build_graph(interactive=False)
    config = {"configurable": {"thread_id": "test-thread-4"}}

    result = compiled.invoke(_base_state(), config)

    assert result["report"]["overall_risk"] == "low"
    assert result["human_approved"] is None
