from __future__ import annotations

from typing import Any

from aegis.configuration.settings import Settings
from aegis.data_activation.service import DataActivationService
from aegis.data_ingestion.service import InMemoryRepository
from aegis.data_quality.validation import validate_eod_ohlcv
from aegis.domain.models import DataProvider, ProviderLicense, ProviderLicenseStatus


def _settings(**overrides: object) -> Settings:
    values: dict[str, Any] = {
        "environment": "development",
        "database_url": "sqlite://",
        "redis_url": "redis://localhost:6379/0",
        "minio_endpoint": "http://localhost:9000",
        "minio_access_key": "access",
        "minio_secret_key": "secret",
        "minio_bucket": "bucket",
        "jwt_secret": "jwt",
        "log_level": "INFO",
    }
    values.update(overrides)
    return Settings(**values)


def test_missing_provider_configuration_maps_to_setup_required() -> None:
    settings = _settings()
    provider = DataProvider(
        name="live_readonly_market_data", provider_type="LIVE_READONLY_MARKET_DATA"
    )
    license_ = ProviderLicense(
        provider_id=provider.id,
        license_status=ProviderLicenseStatus.PENDING,
        permitted_use="pending",
        automation_rights=False,
        backtesting_rights=False,
        model_training_rights=False,
        dashboard_display_rights=False,
        data_retention_period="not-recorded",
    )
    service = DataActivationService(
        settings=settings,
        repository=InMemoryRepository(),
        providers={provider.id: provider},
        licenses={provider.id: license_},
    )

    state = service.provider_state(provider.id)
    summary = service.truth_summary()

    assert state["state"] == "NOT_CONFIGURED"
    assert state["label"] == "Provider setup required"
    assert summary["data_source"]["fixture_data_visible"] is True
    assert summary["safety"]["broker_order_access"] is False


def test_settings_redacts_provider_secrets() -> None:
    settings = _settings(
        market_data_provider_name="approved-provider",
        market_data_provider_environment="sandbox",
        market_data_provider_api_key="super-secret",
        market_data_provider_client_secret="client-secret",
    )
    redacted = settings.redacted()

    assert redacted["market_data_provider_api_key"] == "***"
    assert redacted["market_data_provider_client_secret"] == "***"
    assert settings.market_data_provider_configured() is True


def test_eod_validation_blocks_missing_market_calendar_date() -> None:
    accepted, rejected, results = validate_eod_ohlcv(
        [
            {
                "aegis_instrument_id": "AEGIS-IN-000001",
                "trade_date": "2026-06-26",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 1000,
                "event_time": "2026-06-26T15:30:00+05:30",
                "available_time": "2026-06-26T18:00:00+05:30",
                "ingested_time": "2026-06-26T18:05:00+05:30",
            }
        ],
        {"AEGIS-IN-000001"},
        "dataset-version",
        approved_calendar_dates={"2026-06-25"},
    )

    assert accepted == []
    assert rejected
    assert any("MARKET_CALENDAR" in reason for reason in rejected[0]["reasons"])
    assert results[0].passed is False
