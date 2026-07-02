"""Offline smoke tests for the agent graph (no LLM / API key needed)."""


def test_graph_builds_and_registers_nodes():
    import app.services.agent.nodes  # noqa: F401  (side-effect: register nodes)
    from app.services.agent.graph import _graph
    from app.services.agent.nodes.base import all_nodes

    graph = _graph()
    assert graph is not None

    names = {n.name for n in all_nodes()}
    assert {"expenses", "budgets", "investments"} <= names


def test_orchestrator_handoff_tools_match_nodes():
    from app.services.agent.nodes.base import all_nodes
    from app.services.agent.orchestrator import _handoff_tools

    tool_names = {t.name for t in _handoff_tools()}
    expected = {f"to_{n.name}" for n in all_nodes()}
    assert expected <= tool_names


def test_chat_requires_a_key_when_none_configured(client, monkeypatch):
    # No user key stored and no shared key → /chat should 400 (never reaches LLM).
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_api_key", "")
    resp = client.post("/chat", json={"conversation_id": "c1", "message": "hi"})
    assert resp.status_code == 400
