from __future__ import annotations

import json
from pathlib import Path

import pytest
from aegis.auth.hashing import hash_password, verify_password
from aegis.auth.service import AuthService
from aegis.auth.tokens import TokenError, issue_token, verify_token
from aegis.auth.users import UserStoreError, load_users
from aegis.configuration.settings import Settings


def base_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "environment": "development",
        "database_url": "sqlite://",
        "redis_url": "redis://localhost:6379/0",
        "minio_endpoint": "http://localhost:9000",
        "minio_access_key": "x",
        "minio_secret_key": "y",
        "minio_bucket": "bucket",
        "jwt_secret": "test-secret",
        "log_level": "INFO",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_password_hash_roundtrip_and_rejects_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_password_hash_never_stores_plaintext() -> None:
    hashed = hash_password("supersecret123")
    assert "supersecret123" not in hashed


def test_token_roundtrip() -> None:
    token = issue_token(username="sourabh", role="FOUNDER", secret="s3cret", ttl_minutes=10)
    claims = verify_token(token, secret="s3cret")
    assert claims.username == "sourabh"
    assert claims.role == "FOUNDER"


def test_expired_token_is_rejected() -> None:
    token = issue_token(username="sourabh", role="FOUNDER", secret="s3cret", ttl_minutes=-1)
    with pytest.raises(TokenError, match="expired"):
        verify_token(token, secret="s3cret")


def test_token_signed_with_wrong_secret_is_rejected() -> None:
    token = issue_token(username="sourabh", role="FOUNDER", secret="secret-a", ttl_minutes=10)
    with pytest.raises(TokenError, match="Invalid"):
        verify_token(token, secret="secret-b")


def test_load_users_empty_when_unconfigured() -> None:
    assert load_users() == {}


def test_load_users_missing_file_raises() -> None:
    with pytest.raises(UserStoreError, match="not found"):
        load_users(users_file="/nonexistent/path/auth_users.json")


def test_load_users_malformed_json_raises() -> None:
    with pytest.raises(UserStoreError, match="Invalid auth users JSON"):
        load_users(users_json="not json")


def test_load_users_missing_field_raises() -> None:
    with pytest.raises(UserStoreError, match="missing required field"):
        load_users(users_json=json.dumps([{"username": "a", "role": "FOUNDER"}]))


def test_auth_service_authenticate_and_issue_token(tmp_path: Path) -> None:
    users_file = tmp_path / "auth_users.json"
    users_file.write_text(
        json.dumps(
            [
                {
                    "username": "sourabh",
                    "password_hash": hash_password("correct-password-123"),
                    "role": "FOUNDER",
                }
            ]
        )
    )
    service = AuthService(jwt_secret="s3cret", ttl_minutes=10, users_file=str(users_file))

    assert service.authenticate("sourabh", "wrong-password") is None
    assert service.authenticate("unknown-user", "anything") is None

    user = service.authenticate("sourabh", "correct-password-123")
    assert user is not None
    assert user.role == "FOUNDER"

    token = service.issue_token(user)
    verified = service.verify(token)
    assert verified.username == "sourabh"
    assert verified.role == "FOUNDER"


def test_settings_blocks_insecure_header_fallback_outside_dev_test() -> None:
    settings = base_settings(
        environment="production",
        auth_allow_insecure_header_fallback=True,
        auth_users_file="somewhere.json",
        jwt_secret="a-real-production-secret",
    )
    with pytest.raises(ValueError, match="AUTH_ALLOW_INSECURE_HEADER_FALLBACK"):
        settings.validate_startup()


def test_settings_requires_real_users_outside_dev_test() -> None:
    settings = base_settings(environment="production", jwt_secret="a-real-production-secret")
    with pytest.raises(ValueError, match="AUTH_USERS_FILE or AUTH_USERS_JSON"):
        settings.validate_startup()


def test_settings_rejects_default_jwt_secret_outside_dev_test() -> None:
    settings = base_settings(
        environment="production",
        auth_users_file="somewhere.json",
        jwt_secret="development-only-change-me",
    )
    with pytest.raises(ValueError, match="JWT_SECRET"):
        settings.validate_startup()


def test_settings_rejects_short_jwt_secret_outside_dev_test() -> None:
    settings = base_settings(
        environment="production", auth_users_file="somewhere.json", jwt_secret="too-short"
    )
    with pytest.raises(ValueError, match="at least 32 characters"):
        settings.validate_startup()


def test_settings_allows_insecure_fallback_in_development() -> None:
    settings = base_settings(environment="development", auth_allow_insecure_header_fallback=True)
    settings.validate_startup()  # should not raise
