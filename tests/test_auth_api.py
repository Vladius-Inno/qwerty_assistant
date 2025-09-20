from __future__ import annotations

import types
import uuid
from datetime import datetime, timedelta, timezone


class FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeSession:
    def __init__(self, *, existing_user=None, token_row=None):
        self.existing_user = existing_user
        self.token_row = token_row
        self.added = []
        self.revoked_all = False

    async def execute(self, stmt):
        # Very lightweight branch based on model class presence
        text = str(stmt)
        if "FROM users" in text:
            return FakeResult(self.existing_user)
        if "FROM refresh_tokens" in text and "UPDATE" not in text:
            return FakeResult(self.token_row)
        # UPDATE refresh_tokens ... SET revoked = true
        if "UPDATE refresh_tokens" in text:
            # emulate mass revoke or single revoke
            if self.token_row is not None:
                self.token_row.revoked = True
            self.revoked_all = True
            return FakeResult(None)
        return FakeResult(None)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        # assign IDs to new rows if not set
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                setattr(obj, "id", uuid.uuid4())

    async def refresh(self, obj):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def close(self):
        return None


def _override_session(app, session: FakeSession):
    # Install a dependency override for get_session
    from app.db.sa import get_session as dep_get_session

    async def _gen():
        yield session

    app.dependency_overrides[dep_get_session] = _gen


def test_register_returns_token_pair(client, monkeypatch):
    # Make crypto/token helpers deterministic
    monkeypatch.setattr("app.api.auth.hash_password", lambda p: f"hashed:{p}")
    monkeypatch.setattr("app.api.auth.create_access_token", lambda sub, **_: "access-token")
    monkeypatch.setattr("app.api.auth.create_refresh_token", lambda sub, jti=None, **_: "refresh-token")
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    monkeypatch.setattr(
        "app.api.auth.decode_token",
        lambda t: {"exp": int(future.timestamp()), "type": "refresh", "jti": str(uuid.uuid4()), "sub": str(uuid.uuid4())},
    )

    # No existing user
    session = FakeSession(existing_user=None)
    from app import main as main_mod

    _override_session(main_mod.app, session)

    resp = client.post("/register", json={"email": "a@b.com", "password": "goodpassword"})
    assert resp.status_code == 201
    body = resp.json()
    assert set(body.keys()) >= {"access_token", "refresh_token", "token_type"}
    assert body["access_token"] == "access-token"
    assert body["refresh_token"] == "refresh-token"


def test_login_returns_token_pair(client, monkeypatch):
    # Fake user object with fields used in endpoint
    User = types.SimpleNamespace
    fake_user = User(id=uuid.uuid4(), email="a@b.com", password_hash="hashed:pw", is_active=True)

    # Verification/token helpers
    monkeypatch.setattr("app.api.auth.verify_password", lambda plain, hashed: plain == "pw")
    monkeypatch.setattr("app.api.auth.create_access_token", lambda sub, **_: "access-token")
    monkeypatch.setattr("app.api.auth.create_refresh_token", lambda sub, jti=None, **_: "refresh-token")
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    monkeypatch.setattr(
        "app.api.auth.decode_token",
        lambda t: {"exp": int(future.timestamp()), "type": "refresh", "jti": str(uuid.uuid4()), "sub": str(fake_user.id)},
    )

    session = FakeSession(existing_user=fake_user)
    from app import main as main_mod
    _override_session(main_mod.app, session)

    resp = client.post("/login", json={"email": "a@b.com", "password": "pw"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] == "access-token"
    assert body["refresh_token"] == "refresh-token"


def test_me_returns_profile(client):
    # get_current_user is overridden in conftest; just call /me
    resp = client.get("/me")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) >= {"id", "email", "is_active"}


def test_logout_all_sessions(client, monkeypatch):
    # fake current user provided by conftest; session should accept update to revoke all
    session = FakeSession()
    from app import main as main_mod
    _override_session(main_mod.app, session)

    resp = client.post("/logout?all_sessions=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("revoked") == "all"


def test_refresh_rotates_tokens(client, monkeypatch):
    user_id = uuid.uuid4()
    token_id = uuid.uuid4()

    # Existing refresh token row
    TokenRow = types.SimpleNamespace
    token_row = TokenRow(id=token_id, token="old-refresh", user_id=user_id, revoked=False, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))

    # Helpers
    monkeypatch.setattr("app.api.auth.create_access_token", lambda sub, **_: "new-access")
    monkeypatch.setattr("app.api.auth.create_refresh_token", lambda sub, jti=None, **_: "new-refresh")
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    monkeypatch.setattr(
        "app.api.auth.decode_token",
        lambda t: {"type": "refresh", "sub": str(user_id), "jti": str(token_id), "exp": int(future.timestamp())},
    )

    session = FakeSession(token_row=token_row)
    from app import main as main_mod
    _override_session(main_mod.app, session)

    resp = client.post("/refresh", json={"refresh_token": "old-refresh"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] == "new-access"
    assert body["refresh_token"] == "new-refresh"


def test_login_invalid_password(client, monkeypatch):
    # Existing user but password check fails
    User = types.SimpleNamespace
    fake_user = User(id=uuid.uuid4(), email="a@b.com", password_hash="hashed", is_active=True)

    monkeypatch.setattr("app.api.auth.verify_password", lambda plain, hashed: False)

    session = FakeSession(existing_user=fake_user)
    from app import main as main_mod
    _override_session(main_mod.app, session)

    resp = client.post("/login", json={"email": "a@b.com", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["detail"].lower().startswith("invalid email or password".split()[0])


def test_refresh_invalid_type(client, monkeypatch):
    # decode_token returns non-refresh type
    monkeypatch.setattr("app.api.auth.decode_token", lambda t: {"type": "access"})
    from app import main as main_mod
    _override_session(main_mod.app, FakeSession())
    resp = client.post("/refresh", json={"refresh_token": "x"})
    assert resp.status_code == 401


def test_refresh_expired_token(client, monkeypatch):
    user_id = uuid.uuid4()
    token_id = uuid.uuid4()
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token_row = types.SimpleNamespace(id=token_id, token="tok", user_id=user_id, revoked=False, expires_at=past)
    monkeypatch.setattr(
        "app.api.auth.decode_token",
        lambda t: {"type": "refresh", "sub": str(user_id), "jti": str(token_id), "exp": int(past.timestamp())},
    )
    from app import main as main_mod
    _override_session(main_mod.app, FakeSession(token_row=token_row))
    resp = client.post("/refresh", json={"refresh_token": "tok"})
    assert resp.status_code == 401


def test_logout_single_other_user_forbidden(client, monkeypatch):
    current_uid = uuid.uuid4()
    token_uid = uuid.uuid4()
    token_id = uuid.uuid4()
    monkeypatch.setattr(
        "app.api.auth.decode_token",
        lambda t: {"type": "refresh", "sub": str(token_uid), "jti": str(token_id)},
    )
    # override get_current_user to fixed id
    from app.core import deps as core_deps
    from app import main as main_mod

    async def fixed_user():
        class U:
            id = current_uid
            email = "x@y"
            is_active = True
        return U()

    main_mod.app.dependency_overrides[core_deps.get_current_user] = fixed_user
    _override_session(main_mod.app, FakeSession())
    resp = client.post("/logout", json={"refresh_token": "tok"})
    assert resp.status_code == 403


def test_logout_single_revokes_token(client, monkeypatch):
    user_id = uuid.uuid4()
    token_id = uuid.uuid4()
    monkeypatch.setattr(
        "app.api.auth.decode_token",
        lambda t: {"type": "refresh", "sub": str(user_id), "jti": str(token_id)},
    )
    token_row = types.SimpleNamespace(id=token_id, token="tok", user_id=user_id, revoked=False, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    from app.core import deps as core_deps
    from app import main as main_mod

    async def fixed_user():
        class U:
            id = user_id
            email = "x@y"
            is_active = True
        return U()

    main_mod.app.dependency_overrides[core_deps.get_current_user] = fixed_user
    _override_session(main_mod.app, FakeSession(token_row=token_row))
    resp = client.post("/logout", json={"refresh_token": "tok"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["revoked"] == "single"
    assert data["jti"] == str(token_id)
