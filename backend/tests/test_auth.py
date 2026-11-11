from conftest import Account, set_env

from app.models import User
from app.db import SessionLocal


def test_register_login_me(client):
    a = Account(client, "a@example.com", "Ann Lee")
    assert a.user["email"] == "a@example.com"
    assert a.get("/api/v1/auth/me").json()["name"] == "Ann Lee"
    ws = a.get("/api/v1/workspaces").json()
    assert len(ws) == 1 and ws[0]["role"] == "owner"
    r = client.post("/api/v1/auth/login", json={"email": "A@Example.com", "password": a.password})
    assert r.status_code == 200 and r.json()["access_token"]


def test_password_is_hashed(client):
    Account(client, "hash@example.com", password="secret-pass-123")
    with SessionLocal() as db:
        u = db.query(User).one()
        assert "secret-pass-123" not in u.password_hash and u.password_hash.startswith("$argon2")


def test_duplicate_email_and_weak_password(client):
    Account(client, "dup@example.com")
    r = client.post("/api/v1/auth/register", json={"email": "dup@example.com", "password": "x" * 12, "name": "X"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"
    r = client.post("/api/v1/auth/register", json={"email": "new@example.com", "password": "short", "name": "X"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_wrong_password_and_unknown_email_same_error(client):
    Account(client, "w@example.com")
    r1 = client.post("/api/v1/auth/login", json={"email": "w@example.com", "password": "nope-nope-nope"})
    r2 = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "nope-nope-nope"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_protected_routes_require_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/workspaces").status_code == 401
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401


def test_logout_revokes_token(client):
    a = Account(client, "out@example.com")
    assert a.post("/api/v1/auth/logout").status_code == 200
    assert a.get("/api/v1/auth/me").status_code == 401


def test_change_password(client):
    a = Account(client, "cp@example.com")
    r = a.post("/api/v1/auth/change-password", json={"current_password": "wrong-wrong", "new_password": "n" * 12})
    assert r.status_code == 400
    r = a.post("/api/v1/auth/change-password", json={"current_password": a.password, "new_password": "brand-new-pass"})
    assert r.status_code == 200
    assert a.get("/api/v1/auth/me").status_code == 401  # old token revoked
    assert client.post("/api/v1/auth/login", json={"email": "cp@example.com", "password": "brand-new-pass"}).status_code == 200


def test_password_reset_flow(client, monkeypatch):
    import app.routers.auth as auth_mod
    Account(client, "reset@example.com")
    monkeypatch.setattr(auth_mod, "new_reset_token", lambda: ("known-token-value-123", auth_mod.hash_token("known-token-value-123")))
    r = client.post("/api/v1/auth/password-reset/request", json={"email": "reset@example.com"})
    assert r.status_code == 200
    # Unknown emails get the identical response (no account enumeration).
    assert client.post("/api/v1/auth/password-reset/request", json={"email": "ghost@example.com"}).json() == r.json()
    bad = client.post("/api/v1/auth/password-reset/confirm", json={"token": "wrong-token-000", "new_password": "x" * 12})
    assert bad.status_code == 400
    ok = client.post("/api/v1/auth/password-reset/confirm", json={"token": "known-token-value-123",
                                                                 "new_password": "after-reset-pass"})
    assert ok.status_code == 200
    again = client.post("/api/v1/auth/password-reset/confirm", json={"token": "known-token-value-123",
                                                                    "new_password": "another-pass-1"})
    assert again.status_code == 400  # single use
    assert client.post("/api/v1/auth/login", json={"email": "reset@example.com",
                                                   "password": "after-reset-pass"}).status_code == 200


def test_login_rate_limited(client, monkeypatch):
    set_env(monkeypatch, rate_limit_enabled="true")
    Account(client, "rl@example.com")
    codes = [client.post("/api/v1/auth/login", json={"email": "rl@example.com", "password": "bad-password"}).status_code
             for _ in range(12)]
    assert codes[:10] == [401] * 10
    assert codes[-1] == 429


def test_delete_account(client):
    a = Account(client, "del@example.com")
    assert a.delete("/api/v1/auth/me", json={"password": "wrong"}).status_code == 400
    assert a.delete("/api/v1/auth/me", json={"password": a.password}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "del@example.com", "password": a.password}).status_code == 401


def test_production_requires_secret(monkeypatch):
    import pytest
    from app.config import Settings, resolve_secret_key
    with pytest.raises(RuntimeError):
        resolve_secret_key(Settings(environment="production", secret_key="short"))
