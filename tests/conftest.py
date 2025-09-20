import asyncio
import uuid

import pytest
import sys
from pathlib import Path

# Ensure repository root is on sys.path for `import app`
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture()
def client(monkeypatch):
    # Patch DB init/close in lifespan to no-op
    import app.db.pool as db_pool
    import app.db.sa as db_sa

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(db_pool, "connect_db", _noop)
    monkeypatch.setattr(db_pool, "close_db", _noop)
    monkeypatch.setattr(db_sa, "init_sa_engine", _noop)
    monkeypatch.setattr(db_sa, "close_sa_engine", _noop)

    # Build TestClient with dependency override for auth
    from app.core import deps as core_deps
    from app import main as main_mod

    async def fake_current_user():
        class User:
            id = uuid.uuid4()
            email = "tester@example.com"
            is_active = True

        return User()

    app = main_mod.app
    app.dependency_overrides[core_deps.get_current_user] = fake_current_user

    with TestClient(app) as test_client:
        yield test_client
