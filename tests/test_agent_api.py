from __future__ import annotations

import uuid


def test_call_llm(client, monkeypatch):
    async def fake_call_llm(messages, model, temperature, max_completions_tokens):
        return {"echo": messages[-1]["content"]}
    # Patch where it's used in the router module
    monkeypatch.setattr("app.api.agent.call_llm", fake_call_llm)

    resp = client.post(
        "/api/agent/call-llm",
        json={
            "messages": [{"role": "user", "content": "Hi"}],
            "model": "gpt-4o-mini",
            "temperature": 0.2,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["result"]["echo"] == "Hi"


def test_combined_search(client, monkeypatch):
    async def fake_combined_search_agent(query: str, limit: int = 10, preselect: int = 200, alpha: float = 0.7):
        return [
            {"id": 1, "title": "A", "date": "2020-01-01", "score": 0.9},
            {"id": 2, "title": "B", "date": "2020-01-02", "score": 0.8},
        ][:limit]
    monkeypatch.setattr("app.api.agent.svc_combined_search", fake_combined_search_agent)

    resp = client.post(
        "/api/agent/combined-search",
        json={"query": "test", "limit": 2, "preselect": 10, "alpha": 0.7},
    )
    assert resp.status_code == 200
    data = resp.json()["result"]
    assert isinstance(data, list) and len(data) == 2
    assert data[0]["id"] == 1


def test_agent_loop_direct(client, monkeypatch):
    async def fake_agent_loop(user_goal: str, max_turns: int = 3):
        return {"summary": f"done: {user_goal}", "turns": max_turns}
    monkeypatch.setattr("app.api.agent.agent_loop", fake_agent_loop)

    resp = client.post(
        "/api/agent/agent-loop",
        json={"user_goal": "hello", "max_turns": 2},
    )
    assert resp.status_code == 200
    assert resp.json()["result"]["summary"].startswith("done:")


def test_agent_loop_job_flow(client, monkeypatch):
    async def fake_agent_loop(user_goal: str, max_turns: int = 3):
        # quick-returning coroutine to finish the job almost instantly
        return {"summary": f"job for {user_goal}"}
    monkeypatch.setattr("app.api.agent.agent_loop", fake_agent_loop)

    start = client.post(
        "/api/agent/agent-loop/start",
        json={"user_goal": "goal", "max_turns": 1},
    )
    assert start.status_code == 200
    job_id = start.json()["job_id"]
    assert isinstance(uuid.UUID(job_id), uuid.UUID)

    # Immediately check status — may be running or done depending on timing
    status = client.get(f"/api/agent/agent-loop/status/{job_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["job_id"] == job_id
    assert body["status"] in {"queued", "running", "done", "error"}
