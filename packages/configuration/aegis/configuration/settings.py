from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    redis_url: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    jwt_secret: str
    log_level: str
    live_execution_enabled: bool = False
    broker_order_access: bool = False
    data_source_mode: str = "LIVE_READONLY"
    paper_trading_enabled: bool = False
    human_approval_required: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            environment=os.getenv("ENVIRONMENT", "development"),
            database_url=os.getenv("DATABASE_URL", "sqlite:///aegis-dev.db"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            minio_endpoint=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
            minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            minio_secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            minio_bucket=os.getenv("MINIO_BUCKET", "aegis-local"),
            jwt_secret=os.getenv("JWT_SECRET", "development-only-change-me"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            live_execution_enabled=_as_bool(os.getenv("LIVE_EXECUTION_ENABLED"), False),
            broker_order_access=_as_bool(os.getenv("BROKER_ORDER_ACCESS"), False),
            data_source_mode=os.getenv("DATA_SOURCE_MODE", "LIVE_READONLY"),
            paper_trading_enabled=_as_bool(os.getenv("PAPER_TRADING_ENABLED"), False),
            human_approval_required=_as_bool(os.getenv("HUMAN_APPROVAL_REQUIRED"), True),
        )

    def validate_startup(self) -> None:
        if self.environment not in {"development", "test", "staging", "production"}:
            raise ValueError(f"Unknown ENVIRONMENT: {self.environment}")
        if self.environment != "development":
            missing = [
                name
                for name, value in {
                    "DATABASE_URL": self.database_url,
                    "REDIS_URL": self.redis_url,
                    "MINIO_ENDPOINT": self.minio_endpoint,
                    "MINIO_ACCESS_KEY": self.minio_access_key,
                    "MINIO_SECRET_KEY": self.minio_secret_key,
                    "MINIO_BUCKET": self.minio_bucket,
                    "JWT_SECRET": self.jwt_secret,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(f"Missing required configuration: {', '.join(missing)}")
        if self.live_execution_enabled:
            raise ValueError("LIVE_EXECUTION_ENABLED must remain false in Sprint 0.")
        if self.broker_order_access:
            raise ValueError("BROKER_ORDER_ACCESS must remain false for read-only market data mode.")
        if self.data_source_mode not in {"LOCAL_FIXTURE", "LIVE_READONLY"}:
            raise ValueError(f"Unsupported DATA_SOURCE_MODE: {self.data_source_mode}")
        if self.paper_trading_enabled:
            raise ValueError("PAPER_TRADING_ENABLED must remain false in Sprint 0.")
        if not self.human_approval_required:
            raise ValueError("HUMAN_APPROVAL_REQUIRED must remain true in Sprint 0.")

    def redacted(self) -> dict[str, str | bool]:
        return {
            "environment": self.environment,
            "database_url": self.database_url,
            "redis_url": self.redis_url,
            "minio_endpoint": self.minio_endpoint,
            "minio_access_key": "***",
            "minio_secret_key": "***",
            "minio_bucket": self.minio_bucket,
            "jwt_secret": "***",
            "log_level": self.log_level,
            "live_execution_enabled": self.live_execution_enabled,
            "broker_order_access": self.broker_order_access,
            "data_source_mode": self.data_source_mode,
            "paper_trading_enabled": self.paper_trading_enabled,
            "human_approval_required": self.human_approval_required,
        }
