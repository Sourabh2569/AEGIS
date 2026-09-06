from __future__ import annotations

import dataclasses
import json

import aegis_api.main as main_module
from aegis.auth.hashing import hash_password
from aegis.auth.service import AuthService
from aegis_api.main import app
from fastapi.testclient import TestClient


def _client() -> TestClient:
    return TestClient(app)


def _auth_service_with_user(username: str, password: str, role: str) -> AuthService:
    entry = {"username": username, "password_hash": hash_password(password), "role": role}
    return AuthService(jwt_secret="test-jwt-secret", ttl_minutes=10, users_json=json.dumps([entry]))


def test_login_succeeds_with_correct_credentials(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "auth_service",
        _auth_service_with_user("sourabh", "correct-password-123", "FOUNDER"),
    )

    response = _client().post(
        "/api/v1/auth/login", json={"username": "sourabh", "password": "correct-password-123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "FOUNDER"
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_rejects_wrong_password(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "auth_service",
        _auth_service_with_user("sourabh", "correct-password-123", "FOUNDER"),
    )

    response = _client().post(
        "/api/v1/auth/login", json={"username": "sourabh", "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_login_rejects_unknown_user(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "auth_service", AuthService(jwt_secret="s", ttl_minutes=10))

    response = _client().post(
        "/api/v1/auth/login", json={"username": "nobody", "password": "anything"}
    )
    assert response.status_code == 401


def test_bearer_token_from_login_grants_role_based_access(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "auth_service",
        _auth_service_with_user("researcher1", "correct-password-123", "RESEARCHER"),
    )
    client = _client()

    login = client.post(
        "/api/v1/auth/login", json={"username": "researcher1", "password": "correct-password-123"}
    )
    token = login.json()["access_token"]

    response = client.post(
        "/api/v1/backtest-runs",
        json={"name": "Token-authed run", "starting_cash": "100000"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_token_role_without_permission_is_forbidden(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "auth_service",
        _auth_service_with_user("readonly1", "correct-password-123", "READ_ONLY"),
    )
    client = _client()

    login = client.post(
        "/api/v1/auth/login", json={"username": "readonly1", "password": "correct-password-123"}
    )
    token = login.json()["access_token"]

    response = client.post(
        "/api/v1/backtest-runs",
        json={"name": "Should be forbidden", "starting_cash": "100000"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_invalid_token_is_rejected_even_with_spoofed_role_header(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "auth_service", AuthService(jwt_secret="s", ttl_minutes=10))

    response = _client().post(
        "/api/v1/backtest-runs",
        json={"name": "Should fail", "starting_cash": "100000"},
        headers={"Authorization": "Bearer not-a-real-token", "X-AEGIS-Role": "FOUNDER"},
    )
    assert response.status_code == 401


def test_role_header_alone_is_rejected_when_insecure_fallback_disabled(monkeypatch) -> None:
    """The core regression test: closes the vulnerability where any caller
    could self-declare a role via a plain header with zero verification."""
    locked_down = dataclasses.replace(
        main_module.settings, auth_allow_insecure_header_fallback=False
    )
    monkeypatch.setattr(main_module, "settings", locked_down)

    response = _client().post(
        "/api/v1/backtest-runs",
        json={"name": "Should be rejected", "starting_cash": "100000"},
        headers={"X-AEGIS-Role": "FOUNDER"},
    )
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


def test_role_header_alone_still_works_when_fallback_explicitly_enabled(monkeypatch) -> None:
    permissive = dataclasses.replace(main_module.settings, auth_allow_insecure_header_fallback=True)
    monkeypatch.setattr(main_module, "settings", permissive)

    response = _client().post(
        "/api/v1/backtest-runs",
        json={"name": "Dev convenience path", "starting_cash": "100000"},
        headers={"X-AEGIS-Role": "FOUNDER"},
    )
    assert response.status_code == 200
