from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import aegis_api.main as main_module
from aegis.auth.hashing import hash_password
from aegis.auth.rate_limit import LoginRateLimiter
from aegis.auth.service import AuthService
from aegis_api.main import app
from fastapi.testclient import TestClient


def _client() -> TestClient:
    return TestClient(app)


def _auth_service_with_user(username: str, password: str, role: str) -> AuthService:
    entry = {"username": username, "password_hash": hash_password(password), "role": role}
    return AuthService(jwt_secret="test-jwt-secret", ttl_minutes=10, users_json=json.dumps([entry]))


def test_sixth_wrong_password_in_a_row_is_rate_limited(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "auth_service",
        _auth_service_with_user("sourabh", "correct-password-123", "FOUNDER"),
    )
    client = _client()

    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login", json={"username": "sourabh", "password": "wrong"}
        )
        assert response.status_code == 401

    response = client.post("/api/v1/auth/login", json={"username": "sourabh", "password": "wrong"})
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0
    assert "Too many failed login attempts" in response.json()["detail"]


def test_lockout_is_scoped_to_the_one_username(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "auth_service",
        _auth_service_with_user("victim", "correct-password-123", "FOUNDER"),
    )
    client = _client()

    for _ in range(6):
        client.post("/api/v1/auth/login", json={"username": "victim", "password": "wrong"})

    # A different username must be completely unaffected by "victim"'s lockout.
    response = client.post(
        "/api/v1/auth/login", json={"username": "someone-else", "password": "also-wrong"}
    )
    assert response.status_code == 401


def test_a_correct_login_resets_the_failure_count(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "auth_service",
        _auth_service_with_user("sourabh", "correct-password-123", "FOUNDER"),
    )
    client = _client()

    for _ in range(4):
        client.post("/api/v1/auth/login", json={"username": "sourabh", "password": "wrong"})

    ok = client.post(
        "/api/v1/auth/login", json={"username": "sourabh", "password": "correct-password-123"}
    )
    assert ok.status_code == 200

    # A fresh run of 5 failures after the reset -- not "1 more on top of the
    # old 4" -- must be what it takes to trip the limiter again.
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login", json={"username": "sourabh", "password": "wrong"}
        )
        assert response.status_code == 401

    response = client.post("/api/v1/auth/login", json={"username": "sourabh", "password": "wrong"})
    assert response.status_code == 429


def test_limiter_unit_sliding_window_ages_out_old_failures() -> None:
    limiter = LoginRateLimiter(max_attempts=3, window=timedelta(minutes=15))
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    limiter.record_failure("u", base)
    limiter.record_failure("u", base + timedelta(minutes=1))
    limiter.record_failure("u", base + timedelta(minutes=2))
    assert limiter.seconds_until_allowed("u", base + timedelta(minutes=2)) > 0

    # 16 minutes after the *first* failure, that one has aged out of the
    # 15-minute window, leaving only 2 real recent failures -- under the
    # threshold again.
    later = base + timedelta(minutes=16)
    assert limiter.seconds_until_allowed("u", later) == 0
