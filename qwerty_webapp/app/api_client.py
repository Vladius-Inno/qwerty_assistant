from __future__ import annotations

from typing import Callable, Optional

import httpx


class AuthClient:
    def __init__(
        self,
        base_url: str,
        get_refresh_token: Callable[[], Optional[str]],
        set_refresh_token: Callable[[Optional[str]], None],
    ) -> None:
        self.base_url = base_url.rstrip("/")
        # Use generous default timeouts; long LLM/agent flows can exceed 10s easily
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=120.0, pool=60.0),
        )
        self._access_token: Optional[str] = None
        self._get_refresh_token = get_refresh_token
        self._set_refresh_token = set_refresh_token

    # --- Token helpers ---
    def _auth_headers(self) -> dict[str, str]:
        if not self._access_token:
            return {}
        return {"Authorization": f"Bearer {self._access_token}"}

    def set_tokens(self, access_token: str, refresh_token: Optional[str] = None) -> None:
        self._access_token = access_token
        if refresh_token is not None:
            self._set_refresh_token(refresh_token)

    def clear_tokens(self) -> None:
        self._access_token = None
        self._set_refresh_token(None)

    # --- Auth actions ---
    def register(self, email: str, password: str) -> None:
        resp = self._client.post("/register", json={"email": email, "password": password})
        if resp.status_code >= 400:
            # Friendly messages for common cases
            try:
                data = resp.json()
            except Exception:
                data = None
            if resp.status_code == 409:
                raise Exception("Email already registered")
            if resp.status_code == 422 and isinstance(data, dict):
                detail = data.get("detail")
                # Pydantic v2 error list -> craft readable text
                if isinstance(detail, list):
                    for err in detail:
                        loc = err.get("loc", [])
                        etype = err.get("type", "")
                        msg = err.get("msg") or err.get("message")
                        field = loc[-1] if loc else None
                        if field == "password" and (etype == "string_too_short" or (isinstance(msg, str) and "least" in msg)):
                            raise Exception("Password must be at least 8 characters")
                        if field == "email":
                            raise Exception("Please enter a valid email address")
                # Generic fallback
                raise Exception("Invalid registration data")
            # Other errors: use provided detail or generic
            if isinstance(data, dict):
                d = data.get("detail")
                if isinstance(d, str):
                    raise Exception(d)
            raise Exception(f"Registration failed: {resp.status_code}")
        data = resp.json()
        self.set_tokens(data["access_token"], data["refresh_token"])

    def login(self, email: str, password: str) -> None:
        resp = self._client.post("/login", json={"email": email, "password": password})
        if resp.status_code >= 400:
            try:
                data = resp.json()
            except Exception:
                data = None
            if resp.status_code == 422 and isinstance(data, dict):
                detail = data.get("detail")
                if isinstance(detail, list):
                    for err in detail:
                        loc = err.get("loc", [])
                        field = loc[-1] if loc else None
                        if field == "email":
                            raise Exception("Please enter a valid email address")
                        if field == "password":
                            raise Exception("Please enter your password")
                raise Exception("Invalid login data")
            if isinstance(data, dict):
                d = data.get("detail")
                if isinstance(d, str):
                    raise Exception(d)
            raise Exception(f"Login failed: {resp.status_code}")
        data = resp.json()
        self.set_tokens(data["access_token"], data["refresh_token"])

    def refresh(self) -> bool:
        refresh_token = self._get_refresh_token()
        if not refresh_token:
            return False
        resp = self._client.post("/refresh", json={"refresh_token": refresh_token}, timeout=8.0)
        if resp.status_code >= 400:
            return False
        data = resp.json()
        # Rotate refresh token on success
        self.set_tokens(data["access_token"], data.get("refresh_token"))
        return True

    def logout(self, all_sessions: bool = False) -> None:
        headers = self._auth_headers()
        refresh_token = self._get_refresh_token()
        params = {"all_sessions": str(all_sessions).lower()}
        payload = None if all_sessions else {"refresh_token": refresh_token} if refresh_token else None
        resp = self._client.post("/logout", headers=headers, params=params, json=payload)
        if resp.status_code < 400:
            self.clear_tokens()

    # --- Protected API call with auto-refresh ---
    def get_me(self) -> dict | None:
        headers = self._auth_headers()
        resp = self._client.get("/me", headers=headers)
        if resp.status_code == 401:
            if self.refresh():
                headers = self._auth_headers()
                resp = self._client.get("/me", headers=headers)
        if resp.status_code >= 400:
            return None
        return resp.json()

    # --- Internal helper for protected calls ---
    def _protected_request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> httpx.Response:
        headers = self._auth_headers()
        resp = self._client.request(method, path, headers=headers, json=json, params=params, timeout=timeout)
        if resp.status_code == 401 and self.refresh():
            headers = self._auth_headers()
            resp = self._client.request(method, path, headers=headers, json=json, params=params, timeout=timeout)
        return resp

    # --- Agent API (protected) ---
    def agent_call_llm(self, messages: list[dict[str, str]], model: str | None = None, temperature: float | None = 1.0, max_completions_tokens: int | None = None) -> dict | None:
        payload: dict = {"messages": messages}
        if model is not None:
            payload["model"] = model
        if temperature is not None:
            payload["temperature"] = temperature
        if max_completions_tokens is not None:
            payload["max_completions_tokens"] = max_completions_tokens
        resp = self._protected_request("POST", "/api/agent/call-llm", json=payload)
        if resp.status_code >= 400:
            return None
        return resp.json()

    def agent_fetch_articles(self, ids: list[int]) -> dict | None:
        resp = self._protected_request("POST", "/api/agent/fetch-articles", json={"ids": ids})
        if resp.status_code >= 400:
            return None
        return resp.json()

    def agent_get_related(self, article_id: int, method: str = "semantic", top_n: int = 10) -> dict | None:
        resp = self._protected_request(
            "POST",
            "/api/agent/get-related-articles",
            json={"article_id": article_id, "method": method, "top_n": top_n},
        )
        if resp.status_code >= 400:
            return None
        return resp.json()

    def agent_combined_search(self, query: str, limit: int = 10, preselect: int = 200, alpha: float = 0.7) -> dict | None:
        resp = self._protected_request(
            "POST",
            "/api/agent/combined-search",
            json={"query": query, "limit": limit, "preselect": preselect, "alpha": alpha},
        )
        if resp.status_code >= 400:
            return None
        return resp.json()

    def agent_loop(self, user_goal: str, max_turns: int = 3) -> dict | None:
        # Agent loops can run long; disable request timeouts to avoid client-side aborts
        resp = self._protected_request(
            "POST",
            "/api/agent/agent-loop",
            json={"user_goal": user_goal, "max_turns": max_turns},
            timeout=None,
        )
        if resp.status_code >= 400:
            return None
        return resp.json()

    # --- Long-running agent job APIs ---
    def agent_loop_start(self, user_goal: str, max_turns: int = 3) -> dict | None:
        resp = self._protected_request(
            "POST",
            "/api/agent/agent-loop/start",
            json={"user_goal": user_goal, "max_turns": max_turns},
            timeout=30.0,
        )
        if resp.status_code >= 400:
            return None
        return resp.json()

    def agent_loop_status(self, job_id: str) -> dict | None:
        resp = self._protected_request(
            "GET",
            f"/api/agent/agent-loop/status/{job_id}",
            timeout=15.0,
        )
        if resp.status_code >= 400:
            return None
        return resp.json()

    # --- Chats API (protected) ---
    def chats_create(self, name: str | None = None) -> dict | None:
        payload = {"name": name} if name else {}
        resp = self._protected_request("POST", "/api/chats/", json=payload)
        if resp.status_code >= 400:
            return None
        return resp.json()

    # --- Articles API (public) ---
    def articles_related(self, article_id: int, method: str = "semantic", top_n: int = 10) -> list[dict] | None:
        try:
            resp = self._client.get(
                f"/api/articles/{article_id}/related",
                params={"method": method, "top_n": top_n},
            )
            if resp.status_code >= 400:
                return None
            data = resp.json()
            if isinstance(data, list):
                return data
            return None
        except Exception:
            return None

    def articles_get(self, article_id: int) -> dict | None:
        try:
            resp = self._client.get(f"/api/articles/{article_id}")
            if resp.status_code >= 400:
                return None
            return resp.json()
        except Exception:
            return None

    def articles_search_keywords(
        self,
        *,
        keywords: list[str] | None = None,
        q: str | None = None,
        mode: str = "any",
        partial: bool = False,
        limit: int = 20,
    ) -> dict | None:
        try:
            params: dict = {"mode": mode, "partial": str(partial).lower(), "limit": limit}
            if keywords:
                params["keyword"] = keywords
            elif q:
                params["q"] = q
            else:
                params["q"] = ""
            resp = self._client.get("/api/articles/search/keywords", params=params)
            if resp.status_code >= 400:
                return None
            return resp.json()
        except Exception:
            return None

    def articles_combined_search(self, query: str, limit: int = 10, preselect: int = 200, alpha: float = 0.7) -> list[dict] | None:
        """
        Public combined search variant via /api/articles/search (returns list of metas or ids/title/date).
        Prefer agent_combined_search when auth is available. This is a convenience wrapper.
        """
        try:
            resp = self._client.get("/api/articles/search", params={"q": query, "limit": limit})
            if resp.status_code >= 400:
                return None
            data = resp.json()
            if isinstance(data, list):
                return data
            return None
        except Exception:
            return None

    def articles_list(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        topic: str | None = None,
        tag: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        q: str | None = None,
    ) -> list[dict] | None:
        try:
            params: dict = {"limit": limit, "offset": offset}
            if topic:
                params["topic"] = topic
            if tag:
                params["tag"] = tag
            if date_from:
                params["date_from"] = date_from
            if date_to:
                params["date_to"] = date_to
            if q:
                params["q"] = q
            resp = self._client.get("/api/articles/", params=params)
            if resp.status_code >= 400:
                return None
            data = resp.json()
            if isinstance(data, list):
                return data
            return None
        except Exception:
            return None

    def chats_list(self) -> list[dict] | None:
        resp = self._protected_request("GET", "/api/chats/")
        if resp.status_code >= 400:
            return None
        data = resp.json()
        if isinstance(data, list):
            return data
        return None

    def chats_messages(self, chat_id: str) -> list[dict] | None:
        resp = self._protected_request("GET", f"/api/chats/{chat_id}/messages")
        if resp.status_code >= 400:
            return None
        data = resp.json()
        if isinstance(data, list):
            return data
        return None

    def chats_add_message(self, chat_id: str, role: str, content: str) -> dict | None:
        resp = self._protected_request("POST", f"/api/chats/{chat_id}/messages", json={"role": role, "content": content})
        if resp.status_code >= 400:
            return None
        return resp.json()

    def chats_rename(self, chat_id: str, name: str) -> dict | None:
        resp = self._protected_request("PATCH", f"/api/chats/{chat_id}", json={"name": name})
        if resp.status_code >= 400:
            return None
        return resp.json()
