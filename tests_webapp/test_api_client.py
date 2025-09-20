from __future__ import annotations

import uuid
from typing import Optional

import pytest

from qwerty_webapp.app.api_client import AuthClient


class TokenStore:
    def __init__(self) -> None:
        self.refresh: Optional[str] = None

    def get(self) -> Optional[str]:
        return self.refresh

    def set(self, v: Optional[str]) -> None:
        self.refresh = v


@pytest.fixture()
def client() -> tuple[AuthClient, TokenStore]:
    store = TokenStore()
    c = AuthClient(base_url="http://api.local", get_refresh_token=store.get, set_refresh_token=store.set)
    return c, store


def test_register_success(httpx_mock, client):
    c, store = client
    httpx_mock.add_response(method="POST", url="http://api.local/register", json={"access_token": "a", "refresh_token": "r"})
    c.register("user@example.com", "password123")
    assert store.refresh == "r"


def test_register_conflict(httpx_mock, client):
    c, _ = client
    httpx_mock.add_response(method="POST", url="http://api.local/register", status_code=409, json={"detail": "Email already registered"})
    with pytest.raises(Exception) as e:
        c.register("user@example.com", "password123")
    assert "already registered" in str(e.value).lower()


def test_login_success(httpx_mock, client):
    c, store = client
    httpx_mock.add_response(method="POST", url="http://api.local/login", json={"access_token": "x", "refresh_token": "y"})
    c.login("user@example.com", "password123")
    assert store.refresh == "y"


def test_refresh_success(httpx_mock, client):
    c, store = client
    store.set("rt")
    httpx_mock.add_response(method="POST", url="http://api.local/refresh", json={"access_token": "na", "refresh_token": "nr"})
    ok = c.refresh()
    assert ok is True and store.refresh == "nr"


def test_refresh_missing_token(httpx_mock, client):
    c, _ = client
    assert c.refresh() is False


def test_get_me_success(httpx_mock, client):
    c, store = client
    store.set("rt")
    # set access via login
    httpx_mock.add_response(method="POST", url="http://api.local/login", json={"access_token": "a", "refresh_token": "r"})
    c.login("u", "p")
    httpx_mock.add_response(method="GET", url="http://api.local/me", json={"id": str(uuid.uuid4()), "email": "user@example.com", "is_active": True})
    me = c.get_me()
    assert isinstance(me, dict) and me["email"] == "user@example.com"


def test_protected_request_refresh_retry(httpx_mock, client):
    c, store = client
    store.set("rt")
    # First call 401 -> triggers refresh
    httpx_mock.add_response(method="GET", url="http://api.local/protected", status_code=401)
    httpx_mock.add_response(method="POST", url="http://api.local/refresh", json={"access_token": "na", "refresh_token": "nr"})
    httpx_mock.add_response(method="GET", url="http://api.local/protected", json={"ok": True})
    r = c._protected_request("GET", "/protected")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_chats_endpoints(httpx_mock, client):
    c, _ = client
    httpx_mock.add_response(method="POST", url="http://api.local/login", json={"access_token": "a", "refresh_token": "r"})
    c.login("u", "p")
    httpx_mock.add_response(method="POST", url="http://api.local/api/chats/", json={"id": str(uuid.uuid4()), "name": "Chat"})
    created = c.chats_create()
    assert created and created.get("name") == "Chat"
    httpx_mock.add_response(method="GET", url="http://api.local/api/chats/", json=[{"id": str(uuid.uuid4()), "name": "C"}])
    lst = c.chats_list()
    assert isinstance(lst, list) and lst


def test_agent_start_and_status(httpx_mock, client):
    c, _ = client
    httpx_mock.add_response(method="POST", url="http://api.local/login", json={"access_token": "a", "refresh_token": "r"})
    c.login("u", "p")
    httpx_mock.add_response(method="POST", url="http://api.local/api/agent/agent-loop/start", json={"job_id": "job-1"})
    start = c.agent_loop_start("goal")
    assert start and start.get("job_id") == "job-1"
    httpx_mock.add_response(method="GET", url="http://api.local/api/agent/agent-loop/status/job-1", json={"job_id": "job-1", "status": "running"})
    st = c.agent_loop_status("job-1")
    assert st and st.get("status") == "running"

