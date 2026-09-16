from __future__ import annotations

import pytest
from aegis.configuration.settings import Settings


def _base_settings(**overrides: object) -> Settings:
    return Settings(
        environment="development",
        database_url="sqlite://",
        redis_url="redis://localhost:6379/0",
        minio_endpoint="http://localhost:9000",
        minio_access_key="x",
        minio_secret_key="y",
        minio_bucket="bucket",
        jwt_secret="secret",
        log_level="INFO",
        **overrides,
    )


def test_live_execution_enabled_is_rejected_at_startup() -> None:
    """The live-trading package built from here on must remain categorically
    unreachable until the founder personally edits this guard -- this test
    is the tripwire that catches any future change that weakens it."""
    settings = _base_settings(live_execution_enabled=True)
    with pytest.raises(ValueError, match="LIVE_EXECUTION_ENABLED"):
        settings.validate_startup()


def test_broker_order_access_is_rejected_at_startup() -> None:
    settings = _base_settings(broker_order_access=True, data_source_mode="LIVE_READONLY")
    with pytest.raises(ValueError, match="BROKER_ORDER_ACCESS"):
        settings.validate_startup()


def test_live_broker_connection_enabled_is_rejected_at_startup() -> None:
    settings = _base_settings(live_broker_connection_enabled=True)
    with pytest.raises(ValueError, match="LIVE_BROKER_CONNECTION_ENABLED"):
        settings.validate_startup()


def test_all_three_live_flags_together_still_raise_on_the_first_check() -> None:
    """Belt and suspenders: even if a future change reordered these checks,
    setting all three at once must still fail closed, not pass because one
    check happens to short-circuit past the others."""
    settings = _base_settings(
        live_execution_enabled=True,
        broker_order_access=True,
        live_broker_connection_enabled=True,
    )
    with pytest.raises(ValueError):
        settings.validate_startup()
