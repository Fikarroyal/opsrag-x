"""Authentication: registration, sign-in, session cookie, route protection, throttling."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app.auth import hash_password, make_token, read_token, verify_password
from app.database.session import init_db, make_engine, make_session_factory
from app.main import create_app


@pytest.fixture()
def client(settings, tmp_path):
    engine = make_engine("sqlite://")
    init_db(engine)
    cfg = settings.model_copy(update={"auth_required": True, "secret_key": "test-secret", "data_dir": tmp_path})
    app = create_app(cfg, session_factory=make_session_factory(engine))
    with TestClient(app) as c:
        yield c


def _register(c, email="ani@rsyogyakarta.test", pw="password123", name="Ani Wijaya"):
    return c.post("/api/auth/register", json={"name": name, "email": email, "password": pw})


def test_password_hash_roundtrip():
    h = hash_password("rahasia-banget")
    assert h.startswith("pbkdf2_sha256$") and "rahasia" not in h
    assert verify_password("rahasia-banget", h) and not verify_password("salah", h)
    assert not verify_password("x", None) and not verify_password("x", "garbage")


def test_token_signature_and_expiry(settings):
    cfg = settings.model_copy(update={"secret_key": "k1"})
    tok = make_token("user-1", cfg)
    assert read_token(tok, cfg) == "user-1"
    assert read_token(tok + "x", cfg) is None
    assert read_token(tok, settings.model_copy(update={"secret_key": "other"})) is None
    expired = settings.model_copy(update={"secret_key": "k1", "session_ttl_hours": -1})
    assert read_token(make_token("user-1", expired), cfg) is None


def test_api_requires_login_but_health_is_public(client):
    assert client.get("/api/incidents").status_code == 401
    assert client.get("/api/dashboard/stats").json()["error"] == "unauthorized"
    assert client.get("/api/health").status_code in (200, 503)
    assert client.get("/api/auth/me").status_code == 401


def test_register_sets_session_and_first_user_is_admin(client):
    r = _register(client)
    assert r.status_code == 201 and r.json()["role"] == "admin" and "password" not in r.text
    assert "HttpOnly" in r.headers["set-cookie"]
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "ani@rsyogyakarta.test"
    assert client.get("/api/incidents").status_code == 200
    r2 = client.post("/api/auth/register", json={"name": "Budi", "email": "budi@rsyogyakarta.test", "password": "password123"})
    assert r2.json()["role"] == "it_support"


def test_register_validation_and_duplicates(client):
    assert client.post("/api/auth/register", json={"name": "A", "email": "bad", "password": "short"}).status_code == 422
    assert _register(client).status_code == 201
    dup = _register(client, email="ANI@rsyogyakarta.test")
    assert dup.status_code == 409


def test_login_logout_and_bearer(client):
    _register(client)
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/incidents").status_code == 401
    bad = client.post("/api/auth/login", json={"email": "ani@rsyogyakarta.test", "password": "salah-total"})
    assert bad.status_code == 401 and "salah" in bad.json()["message"].lower()
    ok = client.post("/api/auth/login", json={"email": "ani@rsyogyakarta.test", "password": "password123"})
    assert ok.status_code == 200
    token_cookie = ok.cookies.get("opsragx_session")
    client.cookies.clear()
    assert client.get("/api/incidents", headers={"Authorization": f"Bearer {token_cookie}"}).status_code == 200


def test_login_throttle(client):
    _register(client)
    client.cookies.clear()
    codes = [client.post("/api/auth/login", json={"email": "throttle@rsyogyakarta.test", "password": "x"}).status_code for _ in range(10)]
    assert codes[0] == 401 and codes[-1] == 429
