from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from contextlib import closing

import pytest


pytest.importorskip("playwright.sync_api")


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def webapp_server():
    port = _free_port()
    env = os.environ.copy()
    env["FLET_SERVER_PORT"] = str(port)
    env["FLET_SERVER_ADDRESS"] = "127.0.0.1"
    env["FLET_FORCE_WEB"] = "true"
    # Prefer using Flet CLI to run as a web app reliably in CI
    cmd = [sys.executable, "-m", "flet", "run", "--web", "--port", str(port), "qwerty_webapp/app/app.py"]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    # Wait for port to start accepting connections
    deadline = time.time() + 25
    ready = False
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                ready = True
                break
        except OSError:
            time.sleep(0.25)
    if not ready:
        try:
            out = proc.stdout.read().decode(errors="ignore") if proc.stdout else ""
        except Exception:
            out = ""
        proc.kill()
        pytest.skip(f"Webapp server not ready on port {port}. Output: {out[:500]}")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


@pytest.mark.e2e
def test_login_happy_path(page, webapp_server):
    # Intercept backend calls to the API base URL (default http://localhost:8000)
    def route_handler(route):
        url = route.request.url
        if url.endswith("/login") and route.request.method == "POST":
            return route.fulfill(status=200, json={"access_token": "a", "refresh_token": "r"})
        if url.endswith("/me") and route.request.method == "GET":
            return route.fulfill(status=200, json={"id": "u-1", "email": "user@example.com", "is_active": True})
        # Fallback for other calls in this simple path
        return route.fulfill(status=404, json={"detail": "not mocked"})

    page.route("http://localhost:8000/**", route_handler)

    page.goto(webapp_server, wait_until="domcontentloaded")

    # Fill auth form and submit
    page.get_by_label("Email").fill("user@example.com")
    page.get_by_label("Password").fill("password123")
    page.get_by_role("button", name="Login").click()

    # Expect main view content appears (e.g., "Chats" label)
    page.get_by_text("Chats").wait_for(timeout=5000)
