from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


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
    market_data_enabled: bool = True
    market_data_provider_name: str = ""
    market_data_provider_environment: str = ""
    market_data_provider_base_url: str = ""
    market_data_provider_client_id: str = ""
    market_data_provider_client_secret: str = ""
    market_data_provider_api_key: str = ""
    market_data_provider_access_token: str = ""
    market_data_provider_redirect_uri: str = ""
    market_data_eod_enabled: bool = True
    market_data_quotes_enabled: bool = False
    market_data_corporate_actions_enabled: bool = True
    market_data_calendar_enabled: bool = True
    market_data_benchmark_enabled: bool = True
    # Real HTTP access to NSE's public fundamentals archive is a plain,
    # unauthenticated GET (see fundamentals_nse_provider.py) -- there's no
    # credential to configure. This flag exists purely so the pipeline stays
    # off by default until the founder's NSE Terms-of-Use review is done; the
    # provider's ProviderLicense also stays PENDING regardless of this flag,
    # so ingestion is blocked either way until both are true.
    fundamentals_nse_enabled: bool = False
    live_broker_connection_enabled: bool = False
    paper_trading_use_live_data: bool = False
    paper_trading_enabled: bool = False
    human_approval_required: bool = True
    jwt_access_token_ttl_minutes: int = 720
    auth_users_file: str = ""
    auth_users_json: str = ""
    # SECURITY: when true, requests with no valid Bearer token fall back to
    # trusting the client-supplied X-AEGIS-Role header -- i.e. no real
    # authentication. validate_startup() refuses to let this be true outside
    # development/test. See docs/security/authentication.md.
    auth_allow_insecure_header_fallback: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        # Finds and loads a real .env by walking up from the current working
        # directory -- so `uvicorn`/any script picks up local config the
        # same way regardless of whether the operator remembered to
        # `source .env` first. Never overrides a variable already set in the
        # real environment (e.g. a deployed process's own env vars).
        # Skipped entirely under pytest (see tests/conftest.py): tests rely
        # on the plain code defaults for provider/data-source config to
        # exercise fail-closed behavior, and a real developer .env's actual
        # provider settings would silently defeat that.
        if not os.getenv("AEGIS_SKIP_DOTENV"):
            load_dotenv(override=False)
        environment = os.getenv("ENVIRONMENT", "development")
        # Only development/test get the insecure header fallback by default,
        # and only when the operator hasn't set the flag explicitly.
        default_header_fallback = environment in {"development", "test"}
        return cls(
            environment=environment,
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
            market_data_enabled=_as_bool(os.getenv("MARKET_DATA_ENABLED"), True),
            market_data_provider_name=os.getenv("MARKET_DATA_PROVIDER_NAME", ""),
            market_data_provider_environment=os.getenv("MARKET_DATA_PROVIDER_ENVIRONMENT", ""),
            market_data_provider_base_url=os.getenv("MARKET_DATA_PROVIDER_BASE_URL", ""),
            market_data_provider_client_id=os.getenv("MARKET_DATA_PROVIDER_CLIENT_ID", ""),
            market_data_provider_client_secret=os.getenv("MARKET_DATA_PROVIDER_CLIENT_SECRET", ""),
            market_data_provider_api_key=os.getenv("MARKET_DATA_PROVIDER_API_KEY", ""),
            market_data_provider_access_token=os.getenv("MARKET_DATA_PROVIDER_ACCESS_TOKEN", ""),
            market_data_provider_redirect_uri=os.getenv("MARKET_DATA_PROVIDER_REDIRECT_URI", ""),
            market_data_eod_enabled=_as_bool(os.getenv("MARKET_DATA_EOD_ENABLED"), True),
            market_data_quotes_enabled=_as_bool(os.getenv("MARKET_DATA_QUOTES_ENABLED"), False),
            market_data_corporate_actions_enabled=_as_bool(
                os.getenv("MARKET_DATA_CORPORATE_ACTIONS_ENABLED"), True
            ),
            market_data_calendar_enabled=_as_bool(os.getenv("MARKET_DATA_CALENDAR_ENABLED"), True),
            market_data_benchmark_enabled=_as_bool(
                os.getenv("MARKET_DATA_BENCHMARK_ENABLED"), True
            ),
            fundamentals_nse_enabled=_as_bool(os.getenv("FUNDAMENTALS_NSE_ENABLED"), False),
            live_broker_connection_enabled=_as_bool(
                os.getenv("LIVE_BROKER_CONNECTION_ENABLED"), False
            ),
            paper_trading_use_live_data=_as_bool(os.getenv("PAPER_TRADING_USE_LIVE_DATA"), False),
            paper_trading_enabled=_as_bool(os.getenv("PAPER_TRADING_ENABLED"), False),
            human_approval_required=_as_bool(os.getenv("HUMAN_APPROVAL_REQUIRED"), True),
            jwt_access_token_ttl_minutes=int(os.getenv("JWT_ACCESS_TOKEN_TTL_MINUTES", "720")),
            auth_users_file=os.getenv("AUTH_USERS_FILE", ""),
            auth_users_json=os.getenv("AUTH_USERS_JSON", ""),
            auth_allow_insecure_header_fallback=_as_bool(
                os.getenv("AUTH_ALLOW_INSECURE_HEADER_FALLBACK"), default_header_fallback
            ),
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
            raise ValueError("LIVE_EXECUTION_ENABLED must remain false.")
        if self.broker_order_access:
            raise ValueError(
                "BROKER_ORDER_ACCESS must remain false for read-only market data mode."
            )
        if self.live_broker_connection_enabled:
            raise ValueError("LIVE_BROKER_CONNECTION_ENABLED must remain false.")
        # PAPER_TRADING_USE_LIVE_DATA / PAPER_TRADING_ENABLED were hard-blocked
        # here during the Data Activation Sprint ("must remain false for Data
        # Activation" -- i.e. not yet, this sprint). That sprint is done: real
        # EOD prices and a real trading calendar now feed paper trading (see
        # real_reference_prices() in main.py). Deliberately enabling these
        # only lets *simulated* paper positions use real prices -- it does
        # not touch LIVE_EXECUTION_ENABLED, BROKER_ORDER_ACCESS, or
        # LIVE_BROKER_CONNECTION_ENABLED above, which remain unconditionally
        # forced false. No real order, real broker connection, or real
        # capital is reachable through this flag.
        if self.data_source_mode not in {
            "FIXTURE",
            "LOCAL_FIXTURE",
            "CSV_IMPORT",
            "LIVE_READONLY",
            "DISABLED",
            "BLOCKED",
        }:
            raise ValueError(f"Unsupported DATA_SOURCE_MODE: {self.data_source_mode}")
        if not self.human_approval_required:
            raise ValueError("HUMAN_APPROVAL_REQUIRED must remain true.")
        if self.auth_allow_insecure_header_fallback and self.environment not in {
            "development",
            "test",
        }:
            raise ValueError(
                "AUTH_ALLOW_INSECURE_HEADER_FALLBACK must remain false outside "
                "development/test -- it lets any caller self-declare a role via a "
                "plain header with no verification."
            )
        if self.environment not in {"development", "test"}:
            if not (self.auth_users_file or self.auth_users_json):
                raise ValueError(
                    "AUTH_USERS_FILE or AUTH_USERS_JSON must be configured outside "
                    "development/test -- there is no other way to authenticate."
                )
            if self.jwt_secret == "development-only-change-me":
                raise ValueError("JWT_SECRET must be changed from its development default.")
            if len(self.jwt_secret) < 32:
                raise ValueError(
                    "JWT_SECRET must be at least 32 characters outside development/test "
                    "-- a short secret makes tokens forgeable. Generate one with, e.g., "
                    '`python -c "import secrets; print(secrets.token_urlsafe(48))"`.'
                )

    def market_data_provider_configured(self) -> bool:
        if not self.market_data_enabled:
            return False
        return bool(
            self.market_data_provider_name
            and self.market_data_provider_environment
            and (
                self.market_data_provider_api_key
                or (self.market_data_provider_client_id and self.market_data_provider_client_secret)
            )
        )

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
            "market_data_enabled": self.market_data_enabled,
            "market_data_provider_name": self.market_data_provider_name or "",
            "market_data_provider_environment": self.market_data_provider_environment or "",
            "market_data_provider_base_url": self.market_data_provider_base_url or "",
            "market_data_provider_client_id": "***" if self.market_data_provider_client_id else "",
            "market_data_provider_client_secret": "***"
            if self.market_data_provider_client_secret
            else "",
            "market_data_provider_api_key": "***" if self.market_data_provider_api_key else "",
            "market_data_provider_access_token": "***"
            if self.market_data_provider_access_token
            else "",
            "market_data_provider_redirect_uri": self.market_data_provider_redirect_uri or "",
            "market_data_provider_configured": self.market_data_provider_configured(),
            "market_data_eod_enabled": self.market_data_eod_enabled,
            "market_data_quotes_enabled": self.market_data_quotes_enabled,
            "market_data_corporate_actions_enabled": self.market_data_corporate_actions_enabled,
            "market_data_calendar_enabled": self.market_data_calendar_enabled,
            "market_data_benchmark_enabled": self.market_data_benchmark_enabled,
            "live_broker_connection_enabled": self.live_broker_connection_enabled,
            "paper_trading_use_live_data": self.paper_trading_use_live_data,
            "paper_trading_enabled": self.paper_trading_enabled,
            "human_approval_required": self.human_approval_required,
            "jwt_access_token_ttl_minutes": self.jwt_access_token_ttl_minutes,
            "auth_users_file": "***" if self.auth_users_file else "",
            "auth_users_json": "***" if self.auth_users_json else "",
            "auth_allow_insecure_header_fallback": self.auth_allow_insecure_header_fallback,
        }
