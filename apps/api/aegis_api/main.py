from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import asdict, replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from aegis.audit.service import AuditLog
from aegis.auth.service import AuthenticatedUser, AuthService
from aegis.auth.tokens import TokenError
from aegis.auth.users import UserStoreError
from aegis.backtesting.domain import SPRINT_1A_LABELS, BacktestRunStatus, OrderSide
from aegis.backtesting.engine import BacktestService
from aegis.backtesting.fixtures import load_calendar, load_market_data
from aegis.backtesting.momentum_research import (
    RealMomentumResearchRunner,
    build_paper_strategy_resolver,
    load_real_eod_bars,
)
from aegis.backtesting.repositories import BacktestRepository
from aegis.backtesting.sprint2 import Sprint2ResearchScenarioRunner
from aegis.configuration.settings import Settings
from aegis.data_activation.service import DataActivationService
from aegis.data_ingestion.service import (
    InMemoryRepository,
    LocalObjectStore,
    ProviderIngestionService,
)
from aegis.domain.models import (
    CorporateAction,
    CorporateActionType,
    CorporateActionVerificationStatus,
    DataProvider,
    Dataset,
    DatasetVersion,
    Instrument,
    ProviderLicense,
    ProviderLicenseStatus,
    Role,
    ValidationStatus,
)
from aegis.instrument_master.service import InstrumentMasterService
from aegis.paper_trading.domain import PAPER_LABELS, IncidentType, PaperPortfolioStatus
from aegis.paper_trading.persistence import SqlitePaperTradingRepository
from aegis.paper_trading.queue import PaperSessionJob, SqlitePaperSessionQueue
from aegis.paper_trading.services import (
    PaperTradingCalendarService,
    PaperTradingOrchestrator,
    all_admission_evidence,
    all_readiness_green,
)
from aegis.provider_adapters.csv_provider import CsvFileProvider
from aegis.provider_adapters.kite_connect_provider import (
    CURATED_INSTRUMENT_METADATA,
    KiteConnectMarketDataProvider,
)
from aegis.provider_adapters.live_readonly_provider import LiveReadOnlyMarketDataProvider
from aegis.provider_adapters.mock_provider import MockMarketDataProvider
from aegis.research_activation.evidence_review import ResearchEvidenceReviewGate
from aegis.research_activation.service import HistoricalResearchActivationService
from aegis.research_registry.sprint2 import RESEARCH_LABELS
from aegis.risk.engine import KillSwitchType, RiskProfileVersion
from aegis.shared.money import money
from aegis.strategies.baselines import (
    BuyAndHoldBenchmarkStrategyV0,
    EqualWeightUniverseBenchmarkStrategyV0,
    TrendFollowingBaselineStrategyV0,
)
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

settings = Settings.from_env()
settings.validate_startup()

try:
    auth_service = AuthService(
        jwt_secret=settings.jwt_secret,
        ttl_minutes=settings.jwt_access_token_ttl_minutes,
        users_file=settings.auth_users_file,
        users_json=settings.auth_users_json,
    )
except UserStoreError as exc:
    raise RuntimeError(f"AEGIS auth configuration is invalid: {exc}") from exc

bearer_scheme = HTTPBearer(auto_error=False)

app = FastAPI(title="AEGIS Sprint 0 API", version="0.1.0")
# Scoped to the known local dev web origins -- the dashboard's first
# browser-initiated (not server-to-server) call, so a real cross-origin
# request now exists where none did before. Not a wildcard: only these
# specific dev origins may call the API from a browser. Port 3001 is the
# main dashboard (apps/web); 3002 is the Cockpit decision-support frontend
# (apps/cockpit), which sends real Bearer tokens rather than the dashboard's
# dev-only role header.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["X-Aegis-Role", "Content-Type", "Authorization"],
)
audit_log = AuditLog()
repo = InMemoryRepository()
backtest_repo = BacktestRepository()
# Overridable so tests (see tests/conftest.py) can point every persistent
# file this module owns at an isolated temp directory instead of the real
# dev/production one -- otherwise `from aegis_api.main import app` (used by
# every integration test) shares actual paper-trading/object-store state
# with the running dev server, permanently leaving test-only portfolios,
# intents, and frozen-by-design test fixtures in real data.
work_dir = Path(os.environ.get("AEGIS_WORK_DIR", "work"))
object_store = LocalObjectStore(work_dir / "object_store")
ingestion_service = ProviderIngestionService(
    object_store=object_store,
    repository=repo,
    audit_log=audit_log,
)
instrument_master = InstrumentMasterService()
backtest_service = BacktestService(backtest_repo, audit_log)
paper_store_path = work_dir / "paper_trading.sqlite"
paper_store_path.parent.mkdir(parents=True, exist_ok=True)
paper_queue_path = work_dir / "paper_session_queue.sqlite"
paper_calendar = PaperTradingCalendarService.from_csv(
    Path("sample_data/market_calendar/market_calendar.csv")
)
paper_repo = SqlitePaperTradingRepository(paper_store_path)
paper_session_queue = SqlitePaperSessionQueue(paper_queue_path)

providers: dict[str, DataProvider] = {}
licenses: dict[str, ProviderLicense] = {}
datasets: dict[str, Dataset] = {}
corporate_actions: dict[str, CorporateAction] = {}

seed_provider = DataProvider(name="mock_market_data", provider_type="MOCK")
providers[seed_provider.id] = seed_provider
licenses[seed_provider.id] = ProviderLicense(
    provider_id=seed_provider.id,
    license_status=ProviderLicenseStatus.APPROVED,
    permitted_use="Sprint 0 mock data",
    automation_rights=True,
    backtesting_rights=True,
    model_training_rights=False,
    dashboard_display_rights=True,
    data_retention_period="indefinite-local",
)
live_readonly_provider_record = DataProvider(
    name="live_readonly_market_data",
    provider_type="LIVE_READONLY_MARKET_DATA",
    base_url_or_reference="provider-adapter://live-readonly",
)
providers[live_readonly_provider_record.id] = live_readonly_provider_record
licenses[live_readonly_provider_record.id] = ProviderLicense(
    provider_id=live_readonly_provider_record.id,
    license_status=ProviderLicenseStatus.PENDING,
    permitted_use="Read-only market-data activation pending provider setup and legal approval",
    automation_rights=False,
    backtesting_rights=False,
    model_training_rights=False,
    dashboard_display_rights=False,
    data_retention_period="not-recorded",
    legal_review_status="PENDING_PROVIDER_SETUP",
)
kite_connect_provider_record = DataProvider(
    name="kite_connect",
    provider_type="LIVE_READONLY_MARKET_DATA",
    base_url_or_reference="provider-adapter://kite-connect",
)
providers[kite_connect_provider_record.id] = kite_connect_provider_record
licenses[kite_connect_provider_record.id] = ProviderLicense(
    provider_id=kite_connect_provider_record.id,
    license_status=ProviderLicenseStatus.APPROVED,
    permitted_use="Read-only Kite Connect market-data ingestion, backtesting/research, "
    "and dashboard display under an active Kite Connect subscription",
    automation_rights=True,
    backtesting_rights=True,
    model_training_rights=False,
    dashboard_display_rights=True,
    data_retention_period="provider-contract-controlled",
    legal_review_status="APPROVED",
)
seed_dataset = Dataset(
    name="eod_prices",
    domain="market_data",
    description="End-of-day OHLCV bars",
    owner="DATA_STEWARD",
    criticality="CRITICAL",
)
datasets[seed_dataset.id] = seed_dataset
live_quote_dataset = Dataset(
    name="live_quotes",
    domain="market_data",
    description="Read-only live quote snapshots",
    owner="DATA_STEWARD",
    criticality="CRITICAL",
)
datasets[live_quote_dataset.id] = live_quote_dataset
seed_dataset_version = DatasetVersion(
    dataset_id=seed_dataset.id,
    provider_id=seed_provider.id,
    schema_version="eod_ohlcv.v1",
    raw_snapshot_hash="fixture-hash",
    transformation_version="fixture.v1",
    instrument_master_version="instrument-master.v1",
    corporate_action_version="corporate-actions.v1",
    validation_status=ValidationStatus.GREEN,
    quality_score=100.0,
    lineage_record_exists=True,
    id="dataset-version-1",
)
# Seeded from CURATED_INSTRUMENT_METADATA -- the same NSE-cross-verified
# Nifty 50 table (see the Kite adapter's module comment for provenance) that
# sector_by_instrument_id and the paper-trading/research universe already
# draw from. instrument_master is in-memory and reset on every restart, so
# this must seed the *whole* real universe up front: seeding only RELIANCE
# here left every other real, already-ingested instrument (their EOD bars
# exist for real in the durable object store) permanently invisible to
# GET /api/v1/instruments and every endpoint that resolves a symbol through
# it, even though the backend could compute real signals for all 50.
# sync_instrument_master() skips instruments it already knows about, so a
# wrong value here would never get corrected by a later real sync -- these
# are exactly the same verified values as CURATED_INSTRUMENT_METADATA, not
# placeholders.
curated_instruments: dict[str, Instrument] = {
    symbol: Instrument(
        aegis_instrument_id=metadata.aegis_instrument_id,
        isin=metadata.isin,
        company_legal_name=metadata.company_legal_name,
        security_type=metadata.security_type,
        current_symbol=symbol,
        primary_exchange="NSE",
        listing_date=metadata.listing_date,
        trading_status="ACTIVE",
        sector=metadata.sector,
        industry=metadata.industry,
        mapping_confidence_score=0.99,
    )
    for symbol, metadata in CURATED_INSTRUMENT_METADATA.items()
}
for instrument in curated_instruments.values():
    instrument_master.add_instrument(instrument)
# RELIANCE is the example instrument behind the Sprint 1a fixture-CSV
# backtest flow further down (sample_data/backtesting/valid_eod_prices.csv)
# -- keep a direct reference for those defaults.
seed_instrument = curated_instruments["RELIANCE"]
fixture_calendar = load_calendar(Path("sample_data/backtesting/market_calendar.csv"))
fixture_market_data = load_market_data(
    Path("sample_data/backtesting/valid_eod_prices.csv"), "dataset-version-1"
)
repo.dataset_versions[seed_dataset_version.id] = seed_dataset_version
repo.dataset_origins[seed_dataset_version.id] = "FIXTURE_DATA"
backtest_service.attach_calendar_for_intent_creation(fixture_calendar)
sprint2_runner = Sprint2ResearchScenarioRunner(Path("sample_data/sprint_2"))
sprint2_reports: list[dict[str, Any]] = []
real_momentum_reports: list[dict[str, Any]] = []
sector_by_instrument_id: dict[str, str] = {
    metadata.aegis_instrument_id: metadata.sector
    for metadata in CURATED_INSTRUMENT_METADATA.values()
}
symbol_by_instrument_id: dict[str, str] = {
    metadata.aegis_instrument_id: symbol for symbol, metadata in CURATED_INSTRUMENT_METADATA.items()
}
paper_strategy_resolver = build_paper_strategy_resolver(object_store.root, sector_by_instrument_id)
paper_orchestrator = PaperTradingOrchestrator(
    paper_repo,
    audit_log,
    calendar=paper_calendar,
    sector_by_instrument=sector_by_instrument_id,
    strategy_target_resolver=paper_strategy_resolver,
)
research_activation_manifests: dict[str, dict[str, Any]] = {}
actual_feature_runs: dict[str, dict[str, Any]] = {}
actual_experiments: dict[str, dict[str, Any]] = {}


def correlation_id(request: Request) -> str:
    return request.headers.get("X-Correlation-ID", str(uuid4()))


def authenticated_role(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_aegis_role: str = Header(default=Role.READ_ONLY.value),
) -> Role:
    """Resolve the caller's role. A verified Bearer token always wins.

    The X-AEGIS-Role header is only trusted when
    AUTH_ALLOW_INSECURE_HEADER_FALLBACK is true -- which validate_startup()
    refuses to allow outside development/test. Anywhere else, a request with
    no valid token is rejected outright: the header alone proves nothing,
    since any caller can set it to anything.
    """
    if credentials is not None:
        try:
            user: AuthenticatedUser = auth_service.verify(credentials.credentials)
        except TokenError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        try:
            return Role(user.role)
        except ValueError as exc:
            raise HTTPException(
                status_code=401, detail=f"Token role '{user.role}' is not a known role."
            ) from exc
    if settings.auth_allow_insecure_header_fallback:
        return Role(x_aegis_role)
    raise HTTPException(
        status_code=401,
        detail="Authentication required: provide a Bearer token from POST /api/v1/auth/login.",
    )


def require_role(*allowed: Role):
    def dependency(role: Role = Depends(authenticated_role)) -> Role:
        if role not in allowed:
            raise HTTPException(status_code=403, detail=f"Role {role} cannot perform this action.")
        return role

    return dependency


@app.post("/api/v1/auth/login")
def login(payload: dict[str, Any]) -> dict[str, Any]:
    username = str(payload.get("username", ""))
    password = str(payload.get("password", ""))
    user = auth_service.authenticate(username, password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = auth_service.issue_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "expires_in_minutes": settings.jwt_access_token_ttl_minutes,
    }


def as_dict(value: Any) -> dict[str, Any]:
    return asdict(value)


def activation_service() -> DataActivationService:
    return DataActivationService(
        settings=settings, repository=repo, providers=providers, licenses=licenses
    )


def research_activation_service() -> HistoricalResearchActivationService:
    return HistoricalResearchActivationService(
        settings=settings, repository=repo, licenses=licenses
    )


def research_evidence_review_gate() -> ResearchEvidenceReviewGate:
    return ResearchEvidenceReviewGate(research_activation_service())


def actual_research_blocked_detail() -> dict[str, Any]:
    readiness = research_activation_service().status()
    return {
        "status": "BLOCKED",
        "status_label": "Research blocked",
        "classification": [
            "ACTUAL_HISTORICAL_RESEARCH_ONLY",
            "NOT_VALIDATED",
            "NOT_PAPER_TRADING_ELIGIBLE",
            "NOT_LIVE_TRADING_ELIGIBLE",
            "NO_REAL_CAPITAL_DEPLOYED",
        ],
        "readiness": readiness,
        "reason_codes": readiness["reason_codes"],
        "blockers": readiness["blockers"],
    }


def _build_kite_client(current_settings: Settings) -> Any | None:
    if not (
        current_settings.market_data_provider_api_key
        and current_settings.market_data_provider_access_token
    ):
        return None
    from kiteconnect import KiteConnect  # optional runtime dependency, imported lazily

    client = KiteConnect(api_key=current_settings.market_data_provider_api_key)
    client.set_access_token(current_settings.market_data_provider_access_token)
    return client


def live_readonly_adapter() -> LiveReadOnlyMarketDataProvider | KiteConnectMarketDataProvider:
    if settings.market_data_provider_name == "kite_connect":
        client = _build_kite_client(settings)
        return KiteConnectMarketDataProvider(
            client=client,
            tradingsymbols=list(CURATED_INSTRUMENT_METADATA.keys()),
            license_=licenses[kite_connect_provider_record.id],
            configured=client is not None,
        )
    return LiveReadOnlyMarketDataProvider(
        licenses[live_readonly_provider_record.id],
        configured=settings.market_data_provider_configured(),
    )


def current_market_data_provider_id() -> str:
    """The id of whichever DataProvider record backs live_readonly_adapter()
    right now -- kite_connect when configured, the generic live-readonly
    record otherwise. Every ingestion/health-tracking call site below must
    use this instead of the hardcoded live_readonly_provider_record.id, or
    Kite-sourced activity gets misattributed to the wrong provider record."""
    provider, _ = activation_service().selected_provider()
    return provider.id if provider else live_readonly_provider_record.id


def real_reference_prices(instrument_ids: Iterable[str]) -> dict[str, Decimal]:
    """Latest real EOD close per instrument, from repo.latest_eod_prices --
    populated only by an actual provider ingestion (see
    ProviderIngestionService.ingest_eod_prices). Silently skips any
    instrument with no real price yet rather than fabricating one; callers
    must handle a partial or empty result, never assume every id is present.
    """
    prices: dict[str, Decimal] = {}
    for instrument_id in instrument_ids:
        record = repo.latest_eod_prices.get(instrument_id)
        if record is not None:
            prices[instrument_id] = Decimal(str(record["close"]))
    return prices


def jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, Any]:
    return {
        "status": "ready",
        "database": "configured",
        "redis": "configured",
        "object_storage": "configured",
        "worker": "configured",
    }


@app.get("/api/v1/system/overview")
def system_overview() -> dict[str, Any]:
    truth = activation_service().truth_summary()
    return {
        "backend_health": "ok",
        "database_health": "configured",
        "redis_health": "configured",
        "object_storage_health": "configured",
        "worker_health": "configured",
        "environment": settings.environment,
        "data_source_mode": settings.data_source_mode,
        "broker_order_access": settings.broker_order_access,
        "live_execution_enabled": settings.live_execution_enabled,
        "data_truth": truth,
        "critical_incidents_count": 0,
        "configuration": settings.redacted(),
    }


@app.get("/api/v1/data-source/mode")
def data_source_mode() -> dict[str, Any]:
    truth = activation_service().truth_summary()
    return {
        "data_source_mode": settings.data_source_mode,
        "market_data_enabled": settings.market_data_enabled,
        "market_data_provider_configured": settings.market_data_provider_configured(),
        "provider_state": truth["provider"]["state"],
        "provider_state_label": truth["provider"]["label"],
        "fixture_data_visible": truth["data_source"]["fixture_data_visible"],
        "actual_data_ingested": truth["data_source"]["actual_data_ingested"],
        "live_execution_enabled": settings.live_execution_enabled,
        "broker_order_access": settings.broker_order_access,
        "paper_trading_use_live_data": settings.paper_trading_use_live_data,
        "allowed_operations": [
            "instrument_master_sync",
            "historical_eod_ohlcv_ingestion",
            "live_quote_ingestion",
            "market_calendar_sync",
            "provider_health_check",
            "data_freshness_check",
        ],
        "prohibited_operations": [
            "place_order",
            "submit_order",
            "cancel_order",
            "modify_order",
            "holdings_mutation",
            "live_trading",
        ],
    }


@app.get("/api/v1/system/incidents")
def incidents() -> list[dict[str, Any]]:
    return []


@app.get("/api/v1/system/data-mode")
def system_data_mode() -> dict[str, Any]:
    return data_source_mode()


@app.get("/api/v1/system/data-truth-summary")
def system_data_truth_summary() -> dict[str, Any]:
    return jsonable(activation_service().truth_summary())


@app.get("/api/v1/system/provider-readiness")
def system_provider_readiness() -> dict[str, Any]:
    activation = activation_service()
    provider, _license = activation.selected_provider()
    return jsonable(
        {
            "provider": activation.provider_state(provider.id if provider else None),
            "capabilities": asdict(activation.capability(provider.id)) if provider else None,
            "blockers": activation.blockers(),
        }
    )


@app.get("/api/v1/system/latest-ingestion-summary")
def system_latest_ingestion_summary() -> dict[str, Any]:
    latest = activation_service().latest_successful_ingestion()
    return {
        "latest_ingestion": jsonable(latest) if latest else None,
        "last_updated_at": datetime.now().astimezone().isoformat(),
    }


@app.get("/api/v1/system/data-coverage-summary")
def system_data_coverage_summary() -> dict[str, Any]:
    return activation_service().coverage_summary()


@app.get("/api/v1/system/data-freshness-summary")
def system_data_freshness_summary() -> dict[str, Any]:
    return {
        "freshness": list(repo.data_freshness.values()),
        "last_updated_at": datetime.now().astimezone().isoformat(),
    }


@app.get("/api/v1/system/data-blockers")
def system_data_blockers() -> list[dict[str, Any]]:
    return activation_service().blockers()


@app.get("/api/v1/research-activation/status")
def research_activation_status() -> dict[str, Any]:
    return jsonable(research_activation_service().status())


@app.get("/api/v1/research-activation/eligible-datasets")
def research_activation_eligible_datasets() -> dict[str, Any]:
    service = research_activation_service()
    return jsonable(
        {
            "eligible_datasets": service.eligible_dataset_versions(),
            "dataset_diagnostics": service.dataset_diagnostics(),
            "labels": service.status()["labels"],
        }
    )


@app.get("/api/v1/research-activation/manifests")
def list_research_activation_manifests() -> list[dict[str, Any]]:
    return list(research_activation_manifests.values())


@app.get("/api/v1/research-activation/manifests/{activation_id}")
def get_research_activation_manifest(activation_id: str) -> dict[str, Any]:
    if activation_id not in research_activation_manifests:
        raise HTTPException(status_code=404, detail="Research activation manifest not found.")
    return research_activation_manifests[activation_id]


@app.post("/api/v1/research-activation/activate-historical")
def activate_historical_research(
    payload: dict[str, Any],
    cid: str = Depends(correlation_id),
    role: Role = Depends(require_role(Role.FOUNDER, Role.DATA_STEWARD, Role.RESEARCHER)),
) -> dict[str, Any]:
    manifest = research_activation_service().activate_historical_dataset(
        payload.get("dataset_version_id")
    )
    manifest_payload = jsonable(manifest)
    research_activation_manifests[manifest.activation_id] = manifest_payload
    audit_log.record(
        event_type="RESEARCH_ACTIVATION_ATTEMPT",
        entity_type="ResearchActivationManifest",
        entity_id=manifest.activation_id,
        action="ACTIVATE_HISTORICAL_RESEARCH",
        actor_type="USER",
        actor_id=role.value,
        correlation_id=cid,
        before_state={},
        after_state=manifest_payload,
        metadata={"labels": manifest.labels},
    )
    if manifest.status != "ACTIVE":
        raise HTTPException(status_code=409, detail=manifest_payload)
    return manifest_payload


@app.get("/api/v1/research/actual-data/readiness")
def actual_data_research_readiness() -> dict[str, Any]:
    return jsonable(research_activation_service().status())


@app.get("/api/v1/research/actual-data/blockers")
def actual_data_research_blockers() -> list[dict[str, Any]]:
    return jsonable(research_activation_service().status()["blockers"])


@app.get("/api/v1/research/actual-data/universe-readiness")
def actual_data_universe_readiness() -> dict[str, Any]:
    readiness = research_activation_service().status()
    return {
        "universe_version_id": readiness["universe_version_id"],
        "universe_name": "AEGIS_LIQUID_EQUITY_RESEARCH_UNIVERSE_V0",
        "data_origin": "ACTUAL_PROVIDER_DATA_OR_APPROVED_FILE_IMPORT_REQUIRED",
        "eligible_instrument_count": 0 if readiness["overall_status"] == "BLOCKED" else 1,
        "excluded_instruments": [],
        "exclusion_reasons": readiness["reason_codes"],
        "coverage_percentage": 0 if readiness["overall_status"] == "BLOCKED" else 100,
        "latest_valid_eod_date": None,
        "corporate_action_exceptions": [],
        "research_readiness_status": readiness["overall_status"],
    }


@app.get("/api/v1/research/actual-data/benchmark-readiness")
def actual_data_benchmark_readiness() -> dict[str, Any]:
    readiness = research_activation_service().status()
    return {
        "benchmark_version_id": readiness["benchmark_version_id"],
        "status": "BLOCKED" if readiness["overall_status"] == "BLOCKED" else "READY",
        "reason_codes": ["BENCHMARK_ACTUAL_DATA_NOT_CONFIGURED"]
        if readiness["overall_status"] == "BLOCKED"
        else [],
        "classification": "ACTUAL_HISTORICAL_RESEARCH_ONLY",
    }


@app.get("/api/v1/research/actual-data/feature-readiness")
def actual_data_feature_readiness() -> dict[str, Any]:
    readiness = research_activation_service().status()
    return {
        "feature_readiness_status": readiness["feature_readiness_status"],
        "required_features": [
            "Daily Return",
            "Rolling Return",
            "Simple Moving Average",
            "Exponential Moving Average",
            "Relative Strength Index",
            "Average True Range",
            "Rolling Volatility",
            "Rolling Average Daily Volume",
            "Rolling Average Daily Value Traded",
            "Momentum",
            "Price-to-Moving-Average Distance",
        ],
        "point_in_time_rule": "feature_available_time <= decision_time",
        "same_close_execution_allowed": False,
        "reason_codes": readiness["reason_codes"],
    }


@app.get("/api/v1/research/actual-data/evidence-reviews/baselines")
def actual_data_baseline_evidence_reviews() -> dict[str, Any]:
    return jsonable(research_evidence_review_gate().review_all_baselines())


@app.get("/api/v1/research/actual-data/evidence-reviews/{strategy_version}")
def actual_data_strategy_evidence_review(strategy_version: str) -> dict[str, Any]:
    try:
        return jsonable(research_evidence_review_gate().review_baseline_strategy(strategy_version))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": str(exc)}) from exc


@app.get("/api/v1/providers")
def list_providers() -> list[dict[str, Any]]:
    activation = activation_service()
    return [
        as_dict(provider)
        | {
            "activation": activation.provider_state(provider.id),
            "capabilities": asdict(activation.capability(provider.id)),
        }
        for provider in providers.values()
    ]


@app.post("/api/v1/providers")
def create_provider(
    payload: dict[str, Any],
    cid: str = Depends(correlation_id),
    role: Role = Depends(require_role(Role.FOUNDER, Role.DATA_STEWARD)),
) -> dict[str, Any]:
    provider = DataProvider(**payload)
    providers[provider.id] = provider
    audit_log.record(
        event_type="PROVIDER_CREATED",
        entity_type="DataProvider",
        entity_id=provider.id,
        actor_type="USER",
        actor_id=role.value,
        action="CREATE",
        before_state=None,
        after_state=as_dict(provider),
        correlation_id=cid,
    )
    return as_dict(provider)


@app.get("/api/v1/providers/{provider_id}")
def get_provider(provider_id: str) -> dict[str, Any]:
    activation = activation_service()
    return as_dict(providers[provider_id]) | {
        "activation": activation.provider_state(provider_id),
        "capabilities": asdict(activation.capability(provider_id)),
    }


@app.post("/api/v1/providers/{provider_id}/health-check")
def provider_health(provider_id: str) -> dict[str, Any]:
    provider = providers[provider_id]
    if provider_id == current_market_data_provider_id():
        adapter = live_readonly_adapter()
        return ingestion_service.check_provider_health(provider=adapter, provider_id=provider_id)
    return {
        "provider_id": provider.id,
        "healthy": provider.is_active,
        "message": "registered",
        "order_access": False,
    }


@app.get("/api/v1/providers/{provider_id}/health")
def get_provider_health(provider_id: str) -> dict[str, Any]:
    if provider_id not in repo.provider_health:
        return activation_service().provider_state(provider_id)
    return repo.provider_health[provider_id] | {
        "activation": activation_service().provider_state(provider_id)
    }


@app.post("/api/v1/providers/{provider_id}/run-health-check")
def run_provider_health_check(
    provider_id: str,
    role: Role = Depends(require_role(Role.FOUNDER, Role.DATA_STEWARD, Role.ENGINEER)),
) -> dict[str, Any]:
    return provider_health(provider_id)


@app.get("/api/v1/providers/{provider_id}/capabilities")
def get_provider_capabilities(provider_id: str) -> dict[str, Any]:
    return asdict(activation_service().capability(provider_id))


@app.post("/api/v1/providers/{provider_id}/verify-read-only-connection")
def verify_provider_read_only_connection(
    provider_id: str,
    cid: str = Depends(correlation_id),
    role: Role = Depends(require_role(Role.FOUNDER, Role.DATA_STEWARD, Role.ENGINEER)),
) -> dict[str, Any]:
    selected_provider, _ = activation_service().selected_provider()
    if selected_provider is None or provider_id != selected_provider.id:
        raise HTTPException(
            status_code=404, detail="Provider adapter is not available for verification."
        )
    adapter = live_readonly_adapter()
    adapter.validate_read_only_scope()
    health = ingestion_service.check_provider_health(
        provider=adapter, provider_id=provider_id, correlation_id=cid
    )
    if not settings.market_data_provider_configured():
        raise HTTPException(
            status_code=409, detail=activation_service().provider_state(provider_id)
        )
    return health | {"read_only_verified": health["order_access"] is False}


@app.get("/api/v1/providers/{provider_id}/ingestion-runs")
def get_provider_ingestion_runs(provider_id: str) -> list[dict[str, Any]]:
    return [as_dict(run) for run in repo.ingestion_runs.values() if run.provider_id == provider_id]


@app.post("/api/v1/data-source/live-readonly/sync")
def sync_live_readonly_data(
    cid: str = Depends(correlation_id),
    role: Role = Depends(require_role(Role.FOUNDER, Role.DATA_STEWARD)),
) -> dict[str, Any]:
    if not settings.market_data_provider_configured():
        state = activation_service().provider_state(current_market_data_provider_id())
        audit_log.record(
            event_type="DATA_ACTIVATION_BLOCKED",
            entity_type="DataProvider",
            entity_id=current_market_data_provider_id(),
            actor_type="USER",
            actor_id=role.value,
            action="BLOCK_INGESTION_PROVIDER_SETUP_REQUIRED",
            before_state=None,
            after_state=state,
            correlation_id=cid,
        )
        raise HTTPException(status_code=409, detail=state)
    adapter = live_readonly_adapter()
    health = ingestion_service.check_provider_health(
        provider=adapter, provider_id=current_market_data_provider_id(), correlation_id=cid
    )
    instrument_run = ingestion_service.sync_instrument_master(
        provider=adapter,
        provider_id=current_market_data_provider_id(),
        instrument_master=instrument_master,
        correlation_id=cid,
    )
    eod_run = ingestion_service.ingest_eod_prices(
        provider=adapter,
        provider_id=current_market_data_provider_id(),
        dataset_id=seed_dataset.id,
        dataset_name=seed_dataset.name,
        known_instrument_ids=instrument_master.known_aegis_ids(),
        correlation_id=cid,
    )
    quote_run = ingestion_service.ingest_live_quotes(
        provider=adapter,
        provider_id=current_market_data_provider_id(),
        dataset_id=live_quote_dataset.id,
        known_instrument_ids=instrument_master.known_aegis_ids(),
        correlation_id=cid,
    )
    calendar_run = ingestion_service.sync_market_calendar(
        provider=adapter,
        provider_id=current_market_data_provider_id(),
        correlation_id=cid,
    )
    return jsonable(
        {
            "mode": settings.data_source_mode,
            "live_execution_enabled": settings.live_execution_enabled,
            "broker_order_access": settings.broker_order_access,
            "health": health,
            "runs": {
                "instrument_master": instrument_run,
                "historical_eod_ohlcv": eod_run,
                "live_quotes": quote_run,
                "market_calendar": calendar_run,
            },
        }
    )


@app.get("/api/v1/provider-health")
def list_provider_health() -> list[dict[str, Any]]:
    if current_market_data_provider_id() not in repo.provider_health:
        adapter = live_readonly_adapter()
        ingestion_service.check_provider_health(
            provider=adapter, provider_id=current_market_data_provider_id()
        )
    return list(repo.provider_health.values())


@app.get("/api/v1/data-freshness")
def list_data_freshness() -> list[dict[str, Any]]:
    return list(repo.data_freshness.values())


@app.get("/api/v1/live-quotes")
def list_live_quotes() -> list[dict[str, Any]]:
    if not settings.market_data_provider_configured():
        return []
    return list(repo.live_quotes.values())


@app.get("/api/v1/market-calendar")
def list_market_calendar() -> list[dict[str, Any]]:
    return list(repo.market_calendar.values())


@app.get("/api/v1/providers/{provider_id}/license")
def get_license(provider_id: str) -> dict[str, Any]:
    return as_dict(licenses[provider_id])


@app.post("/api/v1/providers/{provider_id}/license")
def set_license(
    provider_id: str,
    payload: dict[str, Any],
    cid: str = Depends(correlation_id),
    role: Role = Depends(require_role(Role.FOUNDER, Role.DATA_STEWARD)),
) -> dict[str, Any]:
    before = as_dict(licenses[provider_id]) if provider_id in licenses else None
    license_ = ProviderLicense(provider_id=provider_id, **payload)
    licenses[provider_id] = license_
    audit_log.record(
        event_type="PROVIDER_LICENSE_UPDATED",
        entity_type="ProviderLicense",
        entity_id=license_.id,
        actor_type="USER",
        actor_id=role.value,
        action="UPSERT",
        before_state=before,
        after_state=as_dict(license_),
        correlation_id=cid,
    )
    return as_dict(license_)


@app.get("/api/v1/datasets")
def list_datasets() -> list[dict[str, Any]]:
    return [as_dict(dataset) for dataset in datasets.values()]


@app.post("/api/v1/datasets")
def create_dataset(payload: dict[str, Any], cid: str = Depends(correlation_id)) -> dict[str, Any]:
    dataset = Dataset(**payload)
    datasets[dataset.id] = dataset
    audit_log.record(
        event_type="DATASET_CREATED",
        entity_type="Dataset",
        entity_id=dataset.id,
        actor_type="USER",
        actor_id="DATA_STEWARD",
        action="CREATE",
        before_state=None,
        after_state=as_dict(dataset),
        correlation_id=cid,
    )
    return as_dict(dataset)


@app.get("/api/v1/datasets/{dataset_id}")
def get_dataset(dataset_id: str) -> dict[str, Any]:
    return as_dict(datasets[dataset_id])


@app.get("/api/v1/datasets/{dataset_id}/versions")
def dataset_versions(dataset_id: str) -> list[dict[str, Any]]:
    return [as_dict(v) for v in repo.dataset_versions.values() if v.dataset_id == dataset_id]


@app.get("/api/v1/dataset-versions/{dataset_version_id}/quality")
def dataset_quality(dataset_version_id: str) -> list[dict[str, Any]]:
    return [as_dict(result) for result in repo.quality_results.get(dataset_version_id, [])]


@app.get("/api/v1/dataset-versions/{dataset_version_id}")
def get_dataset_version(dataset_version_id: str) -> dict[str, Any]:
    versions = {version["id"]: version for version in activation_service().dataset_versions()}
    return versions[dataset_version_id]


@app.get("/api/v1/dataset-versions/{dataset_version_id}/lineage")
def dataset_lineage(dataset_version_id: str) -> dict[str, Any]:
    version = repo.dataset_versions[dataset_version_id]
    raw = next(
        obj for obj in repo.raw_objects.values() if obj.content_hash == version.raw_snapshot_hash
    )
    return {"dataset_version": as_dict(version), "raw_object": as_dict(raw)}


@app.get("/api/v1/dataset-versions/{dataset_version_id}/coverage")
def dataset_coverage(dataset_version_id: str) -> dict[str, Any]:
    return activation_service().coverage_summary() | {"dataset_version_id": dataset_version_id}


@app.get("/api/v1/data-quality/issues")
def data_quality_issues() -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for results in repo.quality_results.values():
        issues.extend(as_dict(result) for result in results if not result.passed)
    return issues


@app.get("/api/v1/data-quality/summary")
def data_quality_summary() -> dict[str, Any]:
    results = [result for group in repo.quality_results.values() for result in group]
    failed = [result for result in results if not result.passed]
    return {
        "total_checks": len(results),
        "failed_checks": len(failed),
        "status": "GREEN" if not failed else "RED",
        "label": "Ready" if not failed else "Blocked",
    }


@app.post("/api/v1/ingestions/mock")
def ingest_mock(cid: str = Depends(correlation_id)) -> dict[str, Any]:
    provider = MockMarketDataProvider(licenses[seed_provider.id])
    run = ingestion_service.ingest_eod_prices(
        provider=provider,
        provider_id=seed_provider.id,
        dataset_id=seed_dataset.id,
        dataset_name=seed_dataset.name,
        known_instrument_ids=instrument_master.known_aegis_ids(),
        correlation_id=cid,
    )
    return as_dict(run)


@app.post("/api/v1/ingestions/instruments/run")
def run_instrument_ingestion(
    cid: str = Depends(correlation_id),
    role: Role = Depends(require_role(Role.FOUNDER, Role.DATA_STEWARD, Role.SYSTEM_SERVICE)),
) -> dict[str, Any]:
    if not settings.market_data_provider_configured():
        raise HTTPException(
            status_code=409,
            detail=activation_service().provider_state(current_market_data_provider_id()),
        )
    run = ingestion_service.sync_instrument_master(
        provider=live_readonly_adapter(),
        provider_id=current_market_data_provider_id(),
        instrument_master=instrument_master,
        correlation_id=cid,
    )
    return jsonable(run)


@app.post("/api/v1/ingestions/eod/run")
def run_eod_ingestion(
    cid: str = Depends(correlation_id),
    role: Role = Depends(require_role(Role.FOUNDER, Role.DATA_STEWARD, Role.SYSTEM_SERVICE)),
) -> dict[str, Any]:
    if not settings.market_data_provider_configured():
        raise HTTPException(
            status_code=409,
            detail=activation_service().provider_state(current_market_data_provider_id()),
        )
    run = ingestion_service.ingest_eod_prices(
        provider=live_readonly_adapter(),
        provider_id=current_market_data_provider_id(),
        dataset_id=seed_dataset.id,
        dataset_name=seed_dataset.name,
        known_instrument_ids=instrument_master.known_aegis_ids(),
        correlation_id=cid,
    )
    return jsonable(run)


@app.post("/api/v1/ingestions/market-calendar/run")
def run_market_calendar_ingestion(
    cid: str = Depends(correlation_id),
    role: Role = Depends(require_role(Role.FOUNDER, Role.DATA_STEWARD, Role.SYSTEM_SERVICE)),
) -> dict[str, Any]:
    if not settings.market_data_provider_configured():
        raise HTTPException(
            status_code=409,
            detail=activation_service().provider_state(current_market_data_provider_id()),
        )
    return jsonable(
        ingestion_service.sync_market_calendar(
            provider=live_readonly_adapter(),
            provider_id=current_market_data_provider_id(),
            correlation_id=cid,
        )
    )


@app.post("/api/v1/ingestions/corporate-actions/run")
def run_corporate_actions_ingestion(
    role: Role = Depends(require_role(Role.FOUNDER, Role.DATA_STEWARD, Role.SYSTEM_SERVICE)),
) -> dict[str, Any]:
    return {
        "status": "BLOCKED",
        "label": "Provider setup required",
        "reason": "Corporate-action provider source is not configured.",
    }


@app.post("/api/v1/ingestions/benchmark/run")
def run_benchmark_ingestion(
    role: Role = Depends(require_role(Role.FOUNDER, Role.DATA_STEWARD, Role.SYSTEM_SERVICE)),
) -> dict[str, Any]:
    return {
        "status": "BLOCKED",
        "label": "Provider setup required",
        "reason": "Benchmark provider source is not configured.",
    }


@app.post("/api/v1/ingestions/csv")
def ingest_csv(cid: str = Depends(correlation_id)) -> dict[str, Any]:
    provider = CsvFileProvider(Path("sample_data"), licenses[seed_provider.id])
    run = ingestion_service.ingest_eod_prices(
        provider=provider,
        provider_id=seed_provider.id,
        dataset_id=seed_dataset.id,
        dataset_name=seed_dataset.name,
        known_instrument_ids=instrument_master.known_aegis_ids(),
        correlation_id=cid,
    )
    return as_dict(run)


@app.get("/api/v1/ingestions")
def list_ingestions() -> list[dict[str, Any]]:
    return [as_dict(run) for run in repo.ingestion_runs.values()]


@app.get("/api/v1/ingestions/{ingestion_run_id}")
def get_ingestion(ingestion_run_id: str) -> dict[str, Any]:
    return as_dict(repo.ingestion_runs[ingestion_run_id])


@app.get("/api/v1/ingestions/{ingestion_run_id}/errors")
def get_ingestion_errors(ingestion_run_id: str) -> list[str]:
    return repo.ingestion_runs[ingestion_run_id].error_summary


@app.get("/api/v1/instruments")
def list_instruments() -> list[dict[str, Any]]:
    return [as_dict(instrument) for instrument in instrument_master.instruments.values()]


@app.post("/api/v1/instruments")
def create_instrument(
    payload: dict[str, Any], cid: str = Depends(correlation_id)
) -> dict[str, Any]:
    instrument = Instrument(**payload)
    instrument_master.add_instrument(instrument)
    audit_log.record(
        event_type="INSTRUMENT_CREATED",
        entity_type="Instrument",
        entity_id=instrument.id,
        actor_type="USER",
        actor_id="DATA_STEWARD",
        action="CREATE",
        before_state=None,
        after_state=as_dict(instrument),
        correlation_id=cid,
    )
    return as_dict(instrument)


@app.get("/api/v1/instruments/{instrument_id}")
def get_instrument(instrument_id: str) -> dict[str, Any]:
    return as_dict(instrument_master.instruments[instrument_id])


@app.get("/api/v1/instruments/{instrument_id}/source-mappings")
def instrument_source_mappings(instrument_id: str) -> list[dict[str, Any]]:
    instrument = instrument_master.instruments[instrument_id]
    return [
        {
            "instrument_id": instrument_id,
            "provider_id": current_market_data_provider_id(),
            "external_symbol": instrument.current_symbol,
            "external_instrument_id": instrument.aegis_instrument_id,
            "external_exchange_code": instrument.primary_exchange,
            "external_isin": instrument.isin,
            "mapping_status": "VERIFIED"
            if instrument.mapping_confidence_score >= 0.95
            else "PROVISIONAL",
            "mapping_confidence_score": instrument.mapping_confidence_score,
            "source_reference": "instrument-master-local",
            "last_verified_at": instrument.last_verified_at,
        }
    ]


@app.get("/api/v1/instrument-mapping-exceptions")
def instrument_mapping_exceptions() -> list[dict[str, Any]]:
    return []


@app.post("/api/v1/instrument-mapping-exceptions/{exception_id}/resolve")
def resolve_instrument_mapping_exception(
    exception_id: str,
    role: Role = Depends(require_role(Role.FOUNDER, Role.DATA_STEWARD)),
) -> dict[str, Any]:
    return {"exception_id": exception_id, "status": "NO_OPEN_EXCEPTION", "resolved_by": role.value}


@app.get("/api/v1/universes")
def universes() -> list[dict[str, Any]]:
    return [
        {
            "universe_id": "AEGIS_LIQUID_EQUITY_RESEARCH_UNIVERSE_V0",
            "name": "AEGIS liquid equity research universe",
            "status": "NOT_PROMOTED",
            "data_source_label": "Provider setup required"
            if not settings.market_data_provider_configured()
            else "Read-only data source",
        }
    ]


@app.get("/api/v1/universes/{universe_id}")
def universe(universe_id: str) -> dict[str, Any]:
    return universes()[0] | {"universe_id": universe_id}


@app.get("/api/v1/universes/{universe_id}/members")
def universe_members(universe_id: str) -> list[dict[str, Any]]:
    return [
        as_dict(instrument)
        | {
            "universe_id": universe_id,
            "membership_status": "INCLUDED"
            if instrument.mapping_confidence_score >= 0.95
            else "EXCLUDED",
            "exclusion_reason": None
            if instrument.mapping_confidence_score >= 0.95
            else "Mapping confidence below verified threshold",
        }
        for instrument in instrument_master.instruments.values()
    ]


@app.get("/api/v1/instruments/{instrument_id}/aliases")
def list_aliases(instrument_id: str) -> list[dict[str, Any]]:
    return [as_dict(alias) for alias in instrument_master.aliases.get(instrument_id, [])]


@app.post("/api/v1/instruments/{instrument_id}/aliases")
def add_alias(instrument_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from aegis.domain.models import InstrumentAlias

    alias = InstrumentAlias(instrument_id=instrument_id, **payload)
    instrument_master.add_alias(alias)
    return as_dict(alias)


@app.get("/api/v1/corporate-actions")
def list_corporate_actions() -> list[dict[str, Any]]:
    return [as_dict(action) for action in corporate_actions.values()]


@app.post("/api/v1/corporate-actions")
def create_corporate_action(payload: dict[str, Any]) -> dict[str, Any]:
    action = CorporateAction(
        action_type=CorporateActionType(payload["action_type"]),
        verification_status=CorporateActionVerificationStatus(
            payload.get("verification_status", "RAW")
        ),
        **{k: v for k, v in payload.items() if k not in {"action_type", "verification_status"}},
    )
    corporate_actions[action.id] = action
    return as_dict(action)


@app.get("/api/v1/corporate-actions/{corporate_action_id}")
def get_corporate_action(corporate_action_id: str) -> dict[str, Any]:
    return as_dict(corporate_actions[corporate_action_id])


@app.post("/api/v1/corporate-actions/{corporate_action_id}/verify")
def verify_corporate_action(corporate_action_id: str) -> dict[str, Any]:
    action = corporate_actions[corporate_action_id]
    verified = CorporateAction(
        **{**as_dict(action), "verification_status": CorporateActionVerificationStatus.VERIFIED}
    )
    corporate_actions[corporate_action_id] = verified
    return as_dict(verified)


@app.get("/api/v1/research-families")
def research_families() -> list[dict[str, Any]]:
    return []


@app.post("/api/v1/research-families")
def create_research_family(payload: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(uuid4()), **payload}


@app.get("/api/v1/hypotheses")
def hypotheses() -> list[dict[str, Any]]:
    return []


@app.post("/api/v1/hypotheses")
def create_hypothesis(payload: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(uuid4()), **payload}


@app.get("/api/v1/experiments")
def experiments() -> list[dict[str, Any]]:
    return []


@app.post("/api/v1/experiments")
def create_experiment(payload: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(uuid4()), **payload}


@app.post("/api/v1/experiments/actual-data/baseline")
def create_actual_data_baseline_experiment(
    payload: dict[str, Any],
    cid: str = Depends(correlation_id),
    role: Role = Depends(require_role(Role.FOUNDER, Role.RESEARCHER)),
) -> dict[str, Any]:
    readiness = research_activation_service().status()
    allowed_strategies = {
        "BuyAndHoldBenchmarkStrategyV0",
        "EqualWeightUniverseBenchmarkStrategyV0",
        "TrendFollowingBaselineStrategyV0",
    }
    strategy = payload.get("strategy_version_id")
    if strategy not in allowed_strategies:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "BASELINE_STRATEGY_ONLY",
                "allowed_strategies": sorted(allowed_strategies),
            },
        )
    if readiness["overall_status"] == "BLOCKED":
        detail = actual_research_blocked_detail()
        audit_log.record(
            event_type="ACTUAL_BASELINE_EXPERIMENT_BLOCKED",
            entity_type="Experiment",
            entity_id="blocked",
            action="CREATE_ACTUAL_BASELINE_EXPERIMENT",
            actor_type="USER",
            actor_id=role.value,
            correlation_id=cid,
            before_state=payload,
            after_state=detail,
            metadata={"labels": detail["classification"]},
        )
        raise HTTPException(status_code=409, detail=detail)
    experiment_id = f"actual-experiment-{uuid4()}"
    experiment = {
        "experiment_id": experiment_id,
        "experiment_name": payload.get("experiment_name", strategy),
        "classification": "ACTUAL_HISTORICAL_RESEARCH_ONLY",
        "promotion_state": [
            "NOT_VALIDATED",
            "NOT_PAPER_TRADING_ELIGIBLE",
            "NOT_LIVE_TRADING_ELIGIBLE",
        ],
        "data_origin": payload.get("data_origin", "ACTUAL_PROVIDER_DATA"),
        "strategy_version_id": strategy,
        "dataset_version_id": readiness["dataset_version_id"],
        "manifest_status": "DRAFT",
        "is_frozen": False,
        "created_by": role.value,
        "created_at": datetime.now().astimezone().isoformat(),
    }
    actual_experiments[experiment_id] = experiment
    return experiment


@app.get("/api/v1/experiments/{experiment_id}")
def get_experiment(experiment_id: str) -> dict[str, Any]:
    if experiment_id in actual_experiments:
        return actual_experiments[experiment_id]
    raise HTTPException(status_code=404, detail="Experiment not found.")


@app.post("/api/v1/experiments/{experiment_id}/freeze-manifest")
def freeze_manifest(experiment_id: str) -> dict[str, Any]:
    if experiment_id in actual_experiments:
        experiment = actual_experiments[experiment_id]
        if experiment["is_frozen"]:
            return experiment
        frozen = experiment | {
            "manifest_status": "FROZEN",
            "is_frozen": True,
            "frozen_at": datetime.now().astimezone().isoformat(),
        }
        actual_experiments[experiment_id] = frozen
        return frozen
    return {"experiment_id": experiment_id, "is_frozen": True}


@app.post("/api/v1/experiments/{experiment_id}/run")
def run_actual_data_experiment(
    experiment_id: str,
    cid: str = Depends(correlation_id),
    role: Role = Depends(require_role(Role.FOUNDER, Role.RESEARCHER, Role.SYSTEM_SERVICE)),
) -> dict[str, Any]:
    if experiment_id not in actual_experiments:
        raise HTTPException(status_code=404, detail="Actual-data experiment not found.")
    experiment = actual_experiments[experiment_id]
    if not experiment["is_frozen"]:
        raise HTTPException(
            status_code=409,
            detail={"code": "FROZEN_MANIFEST_REQUIRED", "experiment_id": experiment_id},
        )
    detail = actual_research_blocked_detail()
    audit_log.record(
        event_type="ACTUAL_BACKTEST_BLOCKED",
        entity_type="Experiment",
        entity_id=experiment_id,
        action="RUN_ACTUAL_DATA_EXPERIMENT",
        actor_type="USER",
        actor_id=role.value,
        correlation_id=cid,
        before_state=experiment,
        after_state=detail,
        metadata={"labels": detail["classification"]},
    )
    raise HTTPException(status_code=409, detail=detail)


@app.get("/api/v1/experiments/{experiment_id}/partitions")
def get_experiment_partitions(experiment_id: str) -> dict[str, Any]:
    return {
        "experiment_id": experiment_id,
        "status": "DRAFT_OR_BLOCKED",
        "partitions": {
            "warmup": None,
            "training": None,
            "validation": None,
            "holdout": None,
        },
        "rule": "Warmup -> training -> validation -> locked holdout",
    }


@app.get("/api/v1/experiments/{experiment_id}/holdout-usage")
def get_experiment_holdout_usage(experiment_id: str) -> dict[str, Any]:
    return {
        "experiment_id": experiment_id,
        "holdout_usage_records": [],
        "reuse_for_tuning_allowed": False,
    }


@app.get("/api/v1/experiments/{experiment_id}/evidence-package")
def get_experiment_evidence_package(experiment_id: str) -> dict[str, Any]:
    if experiment_id not in actual_experiments:
        raise HTTPException(status_code=404, detail="Actual-data experiment not found.")
    return {
        "experiment_id": experiment_id,
        "status": "NOT_AVAILABLE",
        "reason": "No completed actual-data backtest exists.",
        "classification": [
            "ACTUAL_HISTORICAL_RESEARCH_ONLY",
            "NOT_VALIDATED",
            "NOT_PAPER_TRADING_ELIGIBLE",
            "NOT_LIVE_TRADING_ELIGIBLE",
            "NO_REAL_CAPITAL_DEPLOYED",
        ],
    }


@app.get("/api/v1/backtest-runs")
def list_backtest_runs(
    data_origin: str | None = None,
    role: Role = Depends(
        require_role(Role.FOUNDER, Role.RESEARCHER, Role.RISK_REVIEWER, Role.READ_ONLY)
    ),
) -> list[dict[str, Any]]:
    if data_origin in {"ACTUAL_PROVIDER_DATA", "APPROVED_FILE_IMPORT"}:
        return []
    return [
        jsonable(run) | {"labels": list(SPRINT_1A_LABELS)} for run in backtest_repo.runs.values()
    ]


@app.post("/api/v1/backtest-runs")
def create_backtest_run(
    payload: dict[str, Any],
    cid: str = Depends(correlation_id),
    role: Role = Depends(require_role(Role.FOUNDER, Role.RESEARCHER)),
) -> dict[str, Any]:
    run = backtest_service.create_run(
        name=payload["name"],
        description=payload.get("description", "Foundation simulation only"),
        dataset_version_id=payload.get("dataset_version_id", seed_dataset_version.id),
        instrument_master_version=payload.get("instrument_master_version", "instrument-master.v1"),
        instrument_id=payload.get("instrument_id", seed_instrument.aegis_instrument_id),
        start_date=date.fromisoformat(payload.get("start_date", "2026-06-25")),
        end_date=date.fromisoformat(payload.get("end_date", "2026-06-29")),
        starting_cash=Decimal(str(payload.get("starting_cash", "100000"))),
        created_by=role.value,
        correlation_id=cid,
    )
    return jsonable(run) | {"labels": list(SPRINT_1A_LABELS)}


@app.get("/api/v1/backtest-runs/{backtest_run_id}")
def get_backtest_run(backtest_run_id: str) -> dict[str, Any]:
    return jsonable(backtest_repo.runs[backtest_run_id]) | {"labels": list(SPRINT_1A_LABELS)}


@app.post("/api/v1/backtest-runs/{backtest_run_id}/start")
def start_backtest_run(
    backtest_run_id: str,
    cid: str = Depends(correlation_id),
    role: Role = Depends(require_role(Role.FOUNDER, Role.RESEARCHER, Role.SYSTEM_SERVICE)),
) -> dict[str, Any]:
    run = backtest_service.start_run(
        backtest_run_id=backtest_run_id,
        dataset_version=seed_dataset_version,
        provider_license=licenses[seed_provider.id],
        instrument=seed_instrument,
        calendar=fixture_calendar,
        market_data=fixture_market_data,
        correlation_id=cid,
    )
    return jsonable(run) | {"labels": list(SPRINT_1A_LABELS)}


@app.post("/api/v1/backtest-runs/{backtest_run_id}/cancel")
def cancel_backtest_run(
    backtest_run_id: str,
    cid: str = Depends(correlation_id),
    role: Role = Depends(require_role(Role.FOUNDER, Role.RESEARCHER)),
) -> dict[str, Any]:
    run = backtest_repo.runs[backtest_run_id]
    if run.status == BacktestRunStatus.COMPLETED:
        raise HTTPException(
            status_code=409, detail="Completed runs cannot be modified or cancelled."
        )
    cancelled = run.mark_failed("CANCELLED_BY_USER")
    object.__setattr__(cancelled, "status", BacktestRunStatus.CANCELLED)
    backtest_repo.save_run(cancelled)
    audit_log.record(
        event_type="BACKTEST_CANCELLED",
        entity_type="BacktestRun",
        entity_id=backtest_run_id,
        actor_type="USER",
        actor_id=role.value,
        action="CANCEL",
        before_state=jsonable(run),
        after_state=jsonable(cancelled),
        correlation_id=cid,
    )
    return jsonable(cancelled) | {"labels": list(SPRINT_1A_LABELS)}


@app.get("/api/v1/backtest-runs/{backtest_run_id}/events")
def get_backtest_events(backtest_run_id: str) -> list[dict[str, Any]]:
    return [jsonable(event) for event in backtest_repo.events.get(backtest_run_id, [])]


@app.get("/api/v1/backtest-runs/{backtest_run_id}/summary")
def get_backtest_summary(backtest_run_id: str) -> dict[str, Any]:
    run = backtest_repo.runs[backtest_run_id]
    portfolio = backtest_repo.portfolios[backtest_run_id]
    latest_nav = (backtest_repo.nav_snapshots.get(backtest_run_id) or [None])[-1]
    return {
        "run": jsonable(run),
        "portfolio": jsonable(portfolio),
        "latest_nav": jsonable(latest_nav) if latest_nav else None,
        "realized_pnl": str(backtest_repo.realized_pnl(backtest_run_id)),
        "labels": list(SPRINT_1A_LABELS),
    }


@app.get("/api/v1/backtest-runs/{backtest_run_id}/metrics")
def get_backtest_metrics(backtest_run_id: str) -> dict[str, Any]:
    if backtest_run_id not in backtest_repo.runs:
        raise HTTPException(status_code=404, detail="Backtest run not found.")
    return {
        "backtest_run_id": backtest_run_id,
        "classification": list(SPRINT_1A_LABELS),
        "metrics": {
            "total_return": None,
            "maximum_drawdown": None,
            "gross_exposure": None,
            "turnover": None,
            "total_transaction_cost": None,
        },
        "note": "Actual-data metrics are available only after a completed actual-data research run.",
    }


@app.get("/api/v1/backtest-runs/{backtest_run_id}/attribution")
def get_backtest_attribution(backtest_run_id: str) -> dict[str, Any]:
    if backtest_run_id not in backtest_repo.runs:
        raise HTTPException(status_code=404, detail="Backtest run not found.")
    return {
        "backtest_run_id": backtest_run_id,
        "attribution": {},
        "note": "No actual-data attribution package exists for this foundation run.",
    }


@app.get("/api/v1/backtest-runs/{backtest_run_id}/stress-results")
def get_backtest_stress_results(backtest_run_id: str) -> dict[str, Any]:
    if backtest_run_id not in backtest_repo.runs:
        raise HTTPException(status_code=404, detail="Backtest run not found.")
    return {
        "backtest_run_id": backtest_run_id,
        "stress_results": [],
        "note": "Stress scenarios are retained only for actual-data baseline evidence packages.",
    }


@app.get("/api/v1/backtest-runs/{backtest_run_id}/lineage")
def get_backtest_lineage(backtest_run_id: str) -> dict[str, Any]:
    run = backtest_repo.runs.get(backtest_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found.")
    return {
        "backtest_run_id": backtest_run_id,
        "dataset_version_id": run.dataset_version_id,
        "instrument_master_version": run.instrument_master_version,
        "classification": list(SPRINT_1A_LABELS),
    }


@app.get("/api/v1/backtest-runs/{backtest_run_id}/report")
def get_backtest_report(backtest_run_id: str) -> dict[str, Any]:
    if backtest_run_id not in backtest_repo.runs:
        raise HTTPException(status_code=404, detail="Backtest run not found.")
    return {
        "backtest_run_id": backtest_run_id,
        "report_status": "FOUNDATION_RUN_ONLY",
        "disclaimer": "Historical research evidence is not validated, paper-ready, or live-ready.",
    }


@app.get("/api/v1/backtest-runs/{backtest_run_id}/order-intents")
def get_order_intents(backtest_run_id: str) -> list[dict[str, Any]]:
    return [jsonable(intent) for intent in backtest_repo.order_intents.get(backtest_run_id, [])]


@app.post("/api/v1/backtest-runs/{backtest_run_id}/order-intents")
def create_order_intent(
    backtest_run_id: str,
    payload: dict[str, Any],
    role: Role = Depends(require_role(Role.FOUNDER, Role.RESEARCHER)),
) -> dict[str, Any]:
    intent = backtest_service.create_order_intent(
        backtest_run_id=backtest_run_id,
        side=OrderSide(payload["side"]),
        requested_quantity=Decimal(str(payload["requested_quantity"])),
        decision_time=datetime.fromisoformat(payload["decision_time"]),
        available_data_cutoff=datetime.fromisoformat(payload["available_data_cutoff"]),
        created_by=role.value,
    )
    return jsonable(intent)


@app.get("/api/v1/backtest-runs/{backtest_run_id}/orders")
def get_orders(backtest_run_id: str) -> list[dict[str, Any]]:
    return [jsonable(order) for order in backtest_repo.orders.get(backtest_run_id, [])]


@app.get("/api/v1/backtest-runs/{backtest_run_id}/fills")
def get_fills(backtest_run_id: str) -> list[dict[str, Any]]:
    return [jsonable(fill) for fill in backtest_repo.fills.get(backtest_run_id, [])]


@app.get("/api/v1/backtest-runs/{backtest_run_id}/portfolio")
def get_backtest_portfolio(backtest_run_id: str) -> dict[str, Any]:
    return jsonable(backtest_repo.portfolios[backtest_run_id])


@app.get("/api/v1/backtest-runs/{backtest_run_id}/cash-ledger")
def get_cash_ledger(backtest_run_id: str) -> list[dict[str, Any]]:
    return [jsonable(entry) for entry in backtest_repo.cash_ledger.get(backtest_run_id, [])]


@app.get("/api/v1/backtest-runs/{backtest_run_id}/position-ledger")
def get_position_ledger(backtest_run_id: str) -> list[dict[str, Any]]:
    return [jsonable(entry) for entry in backtest_repo.position_ledger.get(backtest_run_id, [])]


@app.get("/api/v1/backtest-runs/{backtest_run_id}/nav-history")
def get_nav_history(backtest_run_id: str) -> list[dict[str, Any]]:
    return [jsonable(snapshot) for snapshot in backtest_repo.nav_snapshots.get(backtest_run_id, [])]


@app.get("/api/v1/feature-definitions")
def get_feature_definitions() -> list[dict[str, Any]]:
    from aegis.feature_engine.engine import default_feature_definitions

    return [jsonable(definition) for definition in default_feature_definitions()]


@app.post("/api/v1/feature-runs")
def create_feature_run() -> dict[str, Any]:
    return {"status": "AVAILABLE_VIA_FIXTURE_PIPELINE", "classification": list(RESEARCH_LABELS)}


@app.post("/api/v1/feature-runs/actual-data")
def create_actual_data_feature_run(
    payload: dict[str, Any],
    cid: str = Depends(correlation_id),
    role: Role = Depends(
        require_role(Role.FOUNDER, Role.DATA_STEWARD, Role.RESEARCHER, Role.SYSTEM_SERVICE)
    ),
) -> dict[str, Any]:
    readiness = research_activation_service().status()
    if readiness["overall_status"] == "BLOCKED":
        detail = actual_research_blocked_detail()
        audit_log.record(
            event_type="ACTUAL_FEATURE_RUN_BLOCKED",
            entity_type="FeatureRun",
            entity_id="blocked",
            action="CREATE_ACTUAL_FEATURE_RUN",
            actor_type="USER",
            actor_id=role.value,
            correlation_id=cid,
            before_state=payload,
            after_state=detail,
            metadata={"labels": detail["classification"]},
        )
        raise HTTPException(status_code=409, detail=detail)
    feature_run_id = f"actual-feature-run-{uuid4()}"
    record = {
        "feature_run_id": feature_run_id,
        "data_origin": payload.get("data_origin", "ACTUAL_PROVIDER_DATA"),
        "dataset_version_id": readiness["dataset_version_id"],
        "instrument_master_version_id": readiness["instrument_master_version_id"],
        "universe_version_id": readiness["universe_version_id"],
        "corporate_action_version_id": readiness["corporate_action_version_id"],
        "feature_definition_ids": payload.get("feature_definition_ids", []),
        "feature_versions": payload.get("feature_versions", {}),
        "validation_status": "PENDING",
        "classification": [
            "ACTUAL_HISTORICAL_RESEARCH_ONLY",
            "NOT_VALIDATED",
            "NOT_PAPER_TRADING_ELIGIBLE",
            "NOT_LIVE_TRADING_ELIGIBLE",
            "NO_REAL_CAPITAL_DEPLOYED",
        ],
        "created_by": role.value,
        "created_at": datetime.now().astimezone().isoformat(),
    }
    actual_feature_runs[feature_run_id] = record
    return record


@app.get("/api/v1/feature-runs/{feature_run_id}")
def get_feature_run(feature_run_id: str) -> dict[str, Any]:
    if feature_run_id in actual_feature_runs:
        return actual_feature_runs[feature_run_id]
    return {
        "feature_run_id": feature_run_id,
        "status": "FIXTURE_ONLY",
        "classification": list(RESEARCH_LABELS),
    }


@app.get("/api/v1/feature-runs/{feature_run_id}/coverage")
def get_feature_run_coverage(feature_run_id: str) -> dict[str, Any]:
    record = actual_feature_runs.get(feature_run_id)
    return {
        "feature_run_id": feature_run_id,
        "status": record["validation_status"] if record else "NOT_FOUND_OR_FIXTURE_ONLY",
        "coverage_summary": record.get("coverage_summary", {}) if record else {},
        "missing_data_summary": record.get("missing_data_summary", {}) if record else {},
    }


@app.get("/api/v1/feature-runs/{feature_run_id}/lineage")
def get_feature_run_lineage(feature_run_id: str) -> dict[str, Any]:
    record = actual_feature_runs.get(feature_run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Actual-data feature run not found.")
    return {
        "feature_run_id": feature_run_id,
        "data_origin": record["data_origin"],
        "dataset_version_id": record["dataset_version_id"],
        "instrument_master_version_id": record["instrument_master_version_id"],
        "universe_version_id": record["universe_version_id"],
        "corporate_action_version_id": record["corporate_action_version_id"],
    }


@app.get("/api/v1/feature-runs/{feature_run_id}/quality")
def get_feature_run_quality(feature_run_id: str) -> dict[str, Any]:
    record = actual_feature_runs.get(feature_run_id)
    return {
        "feature_run_id": feature_run_id,
        "validation_status": record["validation_status"] if record else "NOT_FOUND_OR_FIXTURE_ONLY",
        "point_in_time_pass": record is not None,
        "same_close_execution_allowed": False,
    }


@app.get("/api/v1/feature-values")
def get_feature_values() -> list[dict[str, Any]]:
    return []


@app.get("/api/v1/strategies")
def get_strategies() -> list[dict[str, Any]]:
    return [
        {"strategy_id": "BuyAndHoldBenchmarkStrategyV0", "status": "RESEARCH_ONLY"},
        {"strategy_id": "EqualWeightUniverseBenchmarkStrategyV0", "status": "RESEARCH_ONLY"},
        {"strategy_id": "TrendFollowingBaselineStrategyV0", "status": "RESEARCH_ONLY"},
    ]


@app.post("/api/v1/strategies")
def create_strategy_placeholder(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") in {"VALIDATED", "PAPER_TRADING", "LIVE_CANDIDATE", "LIVE_ENABLED"}:
        raise HTTPException(
            status_code=400, detail="Sprint 2 strategies must remain RESEARCH_ONLY."
        )
    return {"strategy_id": str(uuid4()), **payload, "status": "RESEARCH_ONLY"}


@app.get("/api/v1/risk-profiles")
def get_risk_profiles() -> list[dict[str, Any]]:
    return [jsonable(RiskProfileVersion())]


@app.get("/api/v1/risk-profile-versions")
def get_risk_profile_versions() -> list[dict[str, Any]]:
    return [jsonable(RiskProfileVersion())]


@app.get("/api/v1/risk-assessments")
def get_sprint2_risk_assessments() -> list[dict[str, Any]]:
    return [
        assessment
        for report in sprint2_reports
        for assessment in report.get("risk_assessments", [])
    ]


@app.get("/api/v1/risk-events")
def get_risk_events() -> list[dict[str, Any]]:
    return []


@app.get("/api/v1/kill-switches")
def get_kill_switches() -> list[dict[str, Any]]:
    return [jsonable(item) for item in paper_repo.kill_switches.values()]


@app.post("/api/v1/sprint-2/scenario-a")
def run_sprint2_scenario_a(
    role: Role = Depends(require_role(Role.FOUNDER, Role.RESEARCHER)),
) -> dict[str, Any]:
    report = sprint2_runner.run_equal_weight_scenario()
    payload = jsonable(report)
    sprint2_reports.append(payload)
    audit_log.record(
        event_type="SPRINT2_SCENARIO_COMPLETED",
        entity_type="ResearchBacktest",
        entity_id="scenario-a",
        actor_type="USER",
        actor_id=role.value,
        action="RUN_RESEARCH_ONLY_SCENARIO",
        before_state=None,
        after_state={"classification": list(RESEARCH_LABELS), "ending_nav": str(report.ending_nav)},
        correlation_id=str(uuid4()),
    )
    return payload


@app.get("/api/v1/sprint-2/reports")
def get_sprint2_reports() -> list[dict[str, Any]]:
    return sprint2_reports


@app.post("/api/v1/research/momentum/run")
def run_real_momentum_backtest(
    role: Role = Depends(require_role(Role.FOUNDER, Role.RESEARCHER, Role.DATA_STEWARD)),
) -> dict[str, Any]:
    capture = load_real_eod_bars(object_store.root)
    if capture is None:
        raise HTTPException(
            status_code=409,
            detail={
                "state": "NO_REAL_HISTORICAL_DATA_CAPTURED",
                "label": "No real historical EOD data has been captured yet",
                "remediation": "Run a provider sync (POST /api/v1/data-source/live-readonly/sync) first.",
            },
        )
    runner = RealMomentumResearchRunner(capture, sector_by_instrument_id)
    momentum_report = jsonable(
        runner.run(TrendFollowingBaselineStrategyV0(), "Real Nifty 50 Trend-Following Momentum")
    )
    benchmark_report = jsonable(
        runner.run(EqualWeightUniverseBenchmarkStrategyV0(), "Real Nifty 50 Equal-Weight Benchmark")
    )
    buy_and_hold_report = jsonable(
        runner.run(BuyAndHoldBenchmarkStrategyV0(), "Real Nifty 50 Buy-and-Hold Benchmark")
    )
    real_momentum_reports.append(momentum_report)
    real_momentum_reports.append(benchmark_report)
    real_momentum_reports.append(buy_and_hold_report)
    audit_log.record(
        event_type="REAL_MOMENTUM_BACKTEST_COMPLETED",
        entity_type="ResearchBacktest",
        entity_id="real-momentum",
        actor_type="USER",
        actor_id=role.value,
        action="RUN_RESEARCH_ONLY_SCENARIO",
        before_state=None,
        after_state={
            "raw_snapshot_hash": capture.raw_snapshot_hash,
            "bar_count": capture.bar_count,
            "instrument_count": capture.instrument_count,
        },
        correlation_id=str(uuid4()),
    )
    return {
        "momentum": momentum_report,
        "benchmark": benchmark_report,
        "buy_and_hold": buy_and_hold_report,
    }


@app.get("/api/v1/research/momentum/reports")
def get_real_momentum_reports() -> list[dict[str, Any]]:
    return real_momentum_reports


STRATEGY_LEADERBOARD_IDS = (
    "TrendFollowingBaselineStrategyV0",
    "EqualWeightUniverseBenchmarkStrategyV0",
    "BuyAndHoldBenchmarkStrategyV0",
)


def _latest_momentum_reports_by_strategy() -> dict[str, dict[str, Any]]:
    """real_momentum_reports is append-only across every POST .../run call --
    the last matching entry for a strategy_name is its latest real run."""
    latest: dict[str, dict[str, Any]] = {}
    for report in real_momentum_reports:
        latest[report["strategy_name"]] = report
    return latest


def _return_to_drawdown_ratio(report: dict[str, Any]) -> Decimal | None:
    total_return = Decimal(report["total_return"])
    max_drawdown = Decimal(report["max_drawdown"])
    return money(total_return / abs(max_drawdown)) if max_drawdown != 0 else None


def _strategy_rule_descriptions() -> dict[str, dict[str, Any]]:
    max_positions = RiskProfileVersion().maximum_position_count
    return {
        "TrendFollowingBaselineStrategyV0": {
            "eligibility": (
                "close > SMA_50 > SMA_200, and 60-day momentum > 0, minimum 20-day "
                "average value traded ₹100,000"
            ),
            "selection": (
                "eligible instruments ranked by descending 60-day momentum, then "
                "descending distance above SMA_200"
            ),
            "sizing": f"top {max_positions} ranked instruments, 80% of equity split equally",
            "stop": "close - 2 x ATR_14",
            "max_positions": max_positions,
        },
        "EqualWeightUniverseBenchmarkStrategyV0": {
            "eligibility": "any instrument with at least 200 real trading days of history -- no other filter",
            "selection": f"every eligible instrument, capped at {max_positions} positions",
            "sizing": "80% of equity split equally across the selected instruments",
            "stop": "not applicable -- this strategy carries no per-position stop",
            "max_positions": max_positions,
        },
        "BuyAndHoldBenchmarkStrategyV0": {
            "eligibility": "any instrument with at least 200 real trading days of history -- no other filter",
            "selection": (
                "exactly one instrument: whichever eligible candidate sorts first by its "
                "internal instrument id (in practice, the same one every period once it "
                "has enough history) -- a simple benchmark construction, not a claim to "
                "track the Nifty 50 index itself"
            ),
            "sizing": "80% of equity in that single instrument",
            "stop": "not applicable -- this strategy carries no per-position stop",
            # This strategy's own construction always holds exactly one
            # instrument -- its real cap is 1, not the platform-wide
            # maximum_position_count, which doesn't apply to it.
            "max_positions": 1,
        },
    }


@app.get("/api/v1/strategies/leaderboard")
def get_strategy_leaderboard() -> list[dict[str, Any]]:
    latest_report_by_strategy = _latest_momentum_reports_by_strategy()

    rows: list[dict[str, Any]] = []
    for strategy_id in STRATEGY_LEADERBOARD_IDS:
        report = latest_report_by_strategy.get(strategy_id)
        backtest: dict[str, Any] | None = None
        ratio: Decimal | None = None
        equity_curve_sparkline: list[str] | None = None
        if report is not None:
            ratio = _return_to_drawdown_ratio(report)
            backtest = {
                "scenario": report["scenario"],
                "dataset_origin": report["dataset_origin"],
                "start_date": report["start_date"],
                "end_date": report["end_date"],
                "total_return": report["total_return"],
                "max_drawdown": report["max_drawdown"],
                "rebalance_count": report["rebalance_count"],
                "position_count": report["position_count"],
                "universe_size": report["universe_size"],
                "bar_count": report["bar_count"],
                "raw_snapshot_hash": report["raw_snapshot_hash"],
                "warnings": report["warnings"],
            }
            # A light decimation of the same real equity curve Strategy Detail
            # shows in full -- just enough points for a card sparkline, kept
            # out of the full curve here to keep this list endpoint's payload
            # small. Always include the real final point so the sparkline
            # ends where the strategy actually currently stands.
            curve = report["equity_curve"]
            sparkline_points = curve[::4]
            if curve and (not sparkline_points or sparkline_points[-1] is not curve[-1]):
                sparkline_points = [*sparkline_points, curve[-1]]
            equity_curve_sparkline = [point["nav"] for point in sparkline_points]

        # Every paper portfolio actually running this strategy that has ever
        # completed a real session -- the honest full aggregate, including
        # dev-testing portfolios, rather than a guess at which ones "count".
        configs = [c for c in paper_repo.strategy_configs.values() if c.strategy_id == strategy_id]
        included_portfolio_ids = {
            c.paper_portfolio_id for c in configs if paper_repo.nav.get(c.paper_portfolio_id)
        }
        live: dict[str, Any] | None = None
        if included_portfolio_ids:
            combined_starting_capital = Decimal(0)
            combined_latest_nav = Decimal(0)
            worst_drawdown = Decimal(0)
            for portfolio_id in included_portfolio_ids:
                combined_starting_capital += paper_repo.portfolios[portfolio_id].starting_capital
                snapshots = paper_repo.nav[portfolio_id]
                combined_latest_nav += snapshots[-1].nav
                worst_drawdown = min(worst_drawdown, min(s.drawdown for s in snapshots))
            combined_return = (
                money((combined_latest_nav - combined_starting_capital) / combined_starting_capital)
                if combined_starting_capital != 0
                else None
            )
            live = {
                "portfolio_count": len(included_portfolio_ids),
                "combined_starting_capital": str(money(combined_starting_capital)),
                "combined_latest_nav": str(money(combined_latest_nav)),
                "combined_return": str(combined_return) if combined_return is not None else None,
                "worst_drawdown": str(money(worst_drawdown)),
            }

        rows.append(
            {
                "strategy_id": strategy_id,
                "return_to_drawdown_ratio": str(ratio) if ratio is not None else None,
                "backtest": backtest,
                "backtest_status": "AVAILABLE" if backtest is not None else "NOT_RUN_YET",
                "equity_curve_sparkline": equity_curve_sparkline,
                "live": live,
                "live_status": "AVAILABLE" if live is not None else "NO_LIVE_PORTFOLIOS_YET",
            }
        )

    rows.sort(
        key=lambda row: (
            Decimal(row["return_to_drawdown_ratio"])
            if row["return_to_drawdown_ratio"] is not None
            else Decimal("-Infinity")
        ),
        reverse=True,
    )
    return rows


@app.get("/api/v1/strategies/{strategy_id}/detail")
def get_strategy_detail(strategy_id: str) -> dict[str, Any]:
    if strategy_id not in STRATEGY_LEADERBOARD_IDS:
        raise HTTPException(status_code=404, detail=f"Unknown strategy_id: {strategy_id}")

    latest_report_by_strategy = _latest_momentum_reports_by_strategy()
    report = latest_report_by_strategy.get(strategy_id)
    backtest: dict[str, Any] | None = None
    ratio: Decimal | None = None
    if report is not None:
        ratio = _return_to_drawdown_ratio(report)
        backtest = {
            "scenario": report["scenario"],
            "dataset_origin": report["dataset_origin"],
            "start_date": report["start_date"],
            "end_date": report["end_date"],
            "total_return": report["total_return"],
            "max_drawdown": report["max_drawdown"],
            "rebalance_count": report["rebalance_count"],
            "position_count": report["position_count"],
            "universe_size": report["universe_size"],
            "bar_count": report["bar_count"],
            "raw_snapshot_hash": report["raw_snapshot_hash"],
            "warnings": report["warnings"],
            "equity_curve": report["equity_curve"],
        }

    # The natural benchmark overlay -- skipped when detailing the benchmark
    # itself, since comparing its line to a copy of itself says nothing.
    benchmark_equity_curve: list[dict[str, str]] | None = None
    if strategy_id != "EqualWeightUniverseBenchmarkStrategyV0":
        benchmark_report = latest_report_by_strategy.get("EqualWeightUniverseBenchmarkStrategyV0")
        if benchmark_report is not None:
            benchmark_equity_curve = benchmark_report["equity_curve"]

    live_portfolios: list[dict[str, Any]] = []
    for config in paper_repo.strategy_configs.values():
        if config.strategy_id != strategy_id:
            continue
        portfolio = paper_repo.portfolios[config.paper_portfolio_id]
        snapshots = paper_repo.nav.get(config.paper_portfolio_id, [])
        live_portfolios.append(
            {
                "paper_portfolio_id": config.paper_portfolio_id,
                "name": portfolio.name,
                "status": portfolio.status,
                "starting_capital": str(portfolio.starting_capital),
                "session_count": len(snapshots),
                "latest_nav": str(snapshots[-1].nav) if snapshots else None,
                "latest_drawdown": str(snapshots[-1].drawdown) if snapshots else None,
                "run_status": "HAS_RUN" if snapshots else "HAS_NOT_RUN_YET",
            }
        )

    return {
        "strategy_id": strategy_id,
        "return_to_drawdown_ratio": str(ratio) if ratio is not None else None,
        "backtest": backtest,
        "backtest_status": "AVAILABLE" if backtest is not None else "NOT_RUN_YET",
        "benchmark_equity_curve": benchmark_equity_curve,
        "rules": _strategy_rule_descriptions()[strategy_id],
        "live_portfolios": live_portfolios,
    }


# ---------------------------------------------------------------------------
# Cockpit read endpoints -- real per-instrument price/indicator/signal data
# for the decision-support frontend (apps/cockpit). All reuse the exact same
# real bar capture, feature-engine formulas, and strategy logic the momentum
# backtest and paper-trading bridge already use above; nothing here
# reimplements a formula or a strategy rule.
# ---------------------------------------------------------------------------


def _resolve_symbol(symbol: str) -> tuple[str, str]:
    """Returns (canonical_symbol, aegis_instrument_id) or raises 404 -- never
    guesses a mapping for a symbol we haven't verified."""
    canonical = symbol.upper()
    metadata = CURATED_INSTRUMENT_METADATA.get(canonical)
    if metadata is None:
        raise HTTPException(status_code=404, detail=f"Unknown instrument symbol: {symbol}")
    return canonical, metadata.aegis_instrument_id


def _load_capture_or_409() -> Any:
    capture = load_real_eod_bars(object_store.root)
    if capture is None:
        raise HTTPException(
            status_code=409,
            detail={
                "state": "NO_REAL_HISTORICAL_DATA_CAPTURED",
                "label": "No real historical EOD data has been captured yet",
                "remediation": "Run a provider sync (POST /api/v1/data-source/live-readonly/sync) first.",
            },
        )
    return capture


def _date_range_or_default(
    capture: Any, from_date: str | None, to_date: str | None, default_days: int = 260
) -> tuple[date, date]:
    end = date.fromisoformat(to_date) if to_date else capture.end_date
    if from_date:
        start = date.fromisoformat(from_date)
    else:
        all_dates = sorted(
            {
                date.fromisoformat(bar["trade_date"])
                for bars in capture.bars_by_instrument.values()
                for bar in bars
                if date.fromisoformat(bar["trade_date"]) <= end
            }
        )
        start = all_dates[-default_days] if len(all_dates) > default_days else all_dates[0]
    return start, end


@app.get("/api/v1/instruments/{symbol}/ohlcv")
def get_instrument_ohlcv(
    symbol: str,
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
) -> dict[str, Any]:
    canonical, aegis_instrument_id = _resolve_symbol(symbol)
    capture = _load_capture_or_409()
    bars = capture.bars_by_instrument.get(aegis_instrument_id, [])
    start, end = _date_range_or_default(capture, from_date, to_date)
    windowed = [bar for bar in bars if start.isoformat() <= bar["trade_date"] <= end.isoformat()]
    return {
        "symbol": canonical,
        "aegis_instrument_id": aegis_instrument_id,
        "dataset_origin": "ACTUAL_PROVIDER_DATA",
        "raw_snapshot_hash": capture.raw_snapshot_hash,
        "bars": [
            {
                "date": bar["trade_date"],
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "volume": bar["volume"],
            }
            for bar in windowed
        ],
    }


@app.get("/api/v1/instruments/{symbol}/indicators")
def get_instrument_indicators(
    symbol: str,
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
) -> dict[str, Any]:
    canonical, aegis_instrument_id = _resolve_symbol(symbol)
    capture = _load_capture_or_409()
    runner = RealMomentumResearchRunner(capture, sector_by_instrument_id)
    start, end = _date_range_or_default(capture, from_date, to_date)
    trading_dates = [d for d in runner.trading_dates if start <= d <= end]
    series = runner.build_candidate_series(aegis_instrument_id, trading_dates)
    points: list[dict[str, Any]] = []
    for as_of in trading_dates:
        candidate = series[as_of]
        points.append(
            {
                "date": as_of.isoformat(),
                "close": str(candidate.close) if candidate else None,
                "sma_50": str(candidate.sma_50)
                if candidate and candidate.sma_50 is not None
                else None,
                "sma_200": str(candidate.sma_200)
                if candidate and candidate.sma_200 is not None
                else None,
                "momentum_60": str(candidate.momentum_60)
                if candidate and candidate.momentum_60 is not None
                else None,
                "atr_14": str(candidate.atr_14)
                if candidate and candidate.atr_14 is not None
                else None,
            }
        )
    return {
        "symbol": canonical,
        "aegis_instrument_id": aegis_instrument_id,
        "dataset_origin": "ACTUAL_PROVIDER_DATA",
        "raw_snapshot_hash": capture.raw_snapshot_hash,
        "points": points,
    }


@app.get("/api/v1/instruments/{symbol}/signal")
def get_instrument_signal(
    symbol: str, paper_portfolio_id: str | None = Query(default=None)
) -> dict[str, Any]:
    canonical, aegis_instrument_id = _resolve_symbol(symbol)
    capture = _load_capture_or_409()
    runner = RealMomentumResearchRunner(capture, sector_by_instrument_id)
    as_of = capture.end_date
    candidates = runner.build_candidates(as_of)
    strategy = TrendFollowingBaselineStrategyV0()
    ranked = strategy.rank_candidates(candidates)
    eligible_ids = {c.instrument_id for c in ranked}
    candidate = next((c for c in candidates if c.instrument_id == aegis_instrument_id), None)
    eligible = aegis_instrument_id in eligible_ids

    held_quantity = None
    held = False
    if paper_portfolio_id is not None:
        research_portfolio = paper_repo.paper_portfolios.get(paper_portfolio_id)
        if research_portfolio is not None:
            qty = research_portfolio.positions.get(aegis_instrument_id, Decimal(0))
            held = qty > 0
            held_quantity = str(qty)

    if eligible and not held:
        signal = "BUY"
    elif eligible and held:
        signal = "HOLD"
    elif not eligible and held:
        signal = "SELL"
    else:
        signal = "NO_POSITION"

    invalidation_price = None
    if candidate is not None and candidate.atr_14 is not None:
        invalidation_price = str(strategy.invalidation_price(candidate))

    return {
        "symbol": canonical,
        "aegis_instrument_id": aegis_instrument_id,
        "as_of": as_of.isoformat(),
        "dataset_origin": "ACTUAL_PROVIDER_DATA",
        "raw_snapshot_hash": capture.raw_snapshot_hash,
        "signal": signal,
        "eligible": eligible,
        "held": held,
        "held_quantity": held_quantity,
        "paper_portfolio_id": paper_portfolio_id,
        "inputs": None
        if candidate is None
        else {
            "close": str(candidate.close),
            "sma_50": str(candidate.sma_50) if candidate.sma_50 is not None else None,
            "sma_200": str(candidate.sma_200) if candidate.sma_200 is not None else None,
            "momentum_60": str(candidate.momentum_60)
            if candidate.momentum_60 is not None
            else None,
            "atr_14": str(candidate.atr_14) if candidate.atr_14 is not None else None,
            "average_daily_value_traded_20": str(candidate.average_daily_value_traded_20)
            if candidate.average_daily_value_traded_20 is not None
            else None,
            "invalidation_price": invalidation_price,
        },
        "rule_thresholds": {
            "eligibility": "close > SMA_50 > SMA_200, and 60-day momentum > 0",
            "minimum_avg_daily_value_traded_20": "100000",
            "stop": "close - 2 x ATR_14",
        },
        "warnings": (
            []
            if paper_portfolio_id is not None
            else [
                "No paper_portfolio_id supplied -- held/HOLD/SELL cannot be determined, only BUY/NO_POSITION."
            ]
        ),
    }


def _signal_rows_for_universe(
    capture: Any, as_of: date, paper_portfolio_id: str | None
) -> list[dict[str, Any]]:
    """Real BUY/HOLD/SELL/NO_POSITION signal for every instrument in the
    universe, reusing the exact strategy ranking and held-position lookup
    that /instruments/{symbol}/signal already applies per-instrument -- one
    source of truth for the eligibility+holding branch, shared by
    /actionables (filtered to BUY/SELL) and /signals (unfiltered)."""
    runner = RealMomentumResearchRunner(capture, sector_by_instrument_id)
    candidates = runner.build_candidates(as_of)
    strategy = TrendFollowingBaselineStrategyV0()
    eligible_ids = {c.instrument_id for c in strategy.rank_candidates(candidates)}

    research_portfolio = (
        paper_repo.paper_portfolios.get(paper_portfolio_id)
        if paper_portfolio_id is not None
        else None
    )

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        eligible = candidate.instrument_id in eligible_ids
        held_quantity = Decimal(0)
        if research_portfolio is not None:
            held_quantity = research_portfolio.positions.get(candidate.instrument_id, Decimal(0))
        held = held_quantity > 0

        if eligible and not held:
            signal = "BUY"
        elif eligible and held:
            signal = "HOLD"
        elif not eligible and held:
            signal = "SELL"
        else:
            signal = "NO_POSITION"

        rows.append(
            {
                "symbol": symbol_by_instrument_id.get(
                    candidate.instrument_id, candidate.instrument_id
                ),
                "aegis_instrument_id": candidate.instrument_id,
                "signal": signal,
                "eligible": eligible,
                "held": held,
                "held_quantity": str(held_quantity),
                "close": str(candidate.close),
                "momentum_60": str(candidate.momentum_60)
                if candidate.momentum_60 is not None
                else None,
                "sma_50": str(candidate.sma_50) if candidate.sma_50 is not None else None,
                "sma_200": str(candidate.sma_200) if candidate.sma_200 is not None else None,
                "invalidation_price": (
                    str(strategy.invalidation_price(candidate))
                    if candidate.atr_14 is not None
                    else None
                ),
            }
        )
    return rows


@app.get("/api/v1/actionables")
def get_actionables(paper_portfolio_id: str | None = Query(default=None)) -> dict[str, Any]:
    capture = _load_capture_or_409()
    as_of = capture.end_date
    rows = _signal_rows_for_universe(capture, as_of, paper_portfolio_id)

    buys: list[dict[str, Any]] = []
    sells: list[dict[str, Any]] = []
    for signal_row in rows:
        if signal_row["signal"] not in ("BUY", "SELL"):
            continue  # HOLD/NO_POSITION -- steady state, not actionable

        row = {
            "symbol": signal_row["symbol"],
            "aegis_instrument_id": signal_row["aegis_instrument_id"],
            "close": signal_row["close"],
            "momentum_60": signal_row["momentum_60"],
            "sma_50": signal_row["sma_50"],
            "sma_200": signal_row["sma_200"],
        }
        if signal_row["signal"] == "BUY":
            row["action"] = "BUY"
            row["invalidation_price"] = signal_row["invalidation_price"]
            buys.append(row)
        else:
            row["action"] = "SELL"
            row["held_quantity"] = signal_row["held_quantity"]
            sells.append(row)

    buys.sort(key=lambda row: Decimal(row["momentum_60"] or 0), reverse=True)

    return {
        "as_of": as_of.isoformat(),
        "dataset_origin": "ACTUAL_PROVIDER_DATA",
        "raw_snapshot_hash": capture.raw_snapshot_hash,
        "paper_portfolio_id": paper_portfolio_id,
        "actionables": sells + buys,
        "warnings": (
            []
            if paper_portfolio_id is not None
            else [
                (
                    "No paper_portfolio_id supplied -- SELL signals cannot be determined "
                    "without a portfolio's real holdings, showing BUY-eligible instruments only."
                )
            ]
        ),
    }


@app.get("/api/v1/signals")
def get_universe_signals(paper_portfolio_id: str | None = Query(default=None)) -> dict[str, Any]:
    """Real BUY/HOLD/SELL/NO_POSITION signal for every instrument in the
    universe in one call -- the Cockpit home page uses this instead of one
    /instruments/{symbol}/signal round-trip per instrument."""
    capture = _load_capture_or_409()
    as_of = capture.end_date
    rows = _signal_rows_for_universe(capture, as_of, paper_portfolio_id)

    return {
        "as_of": as_of.isoformat(),
        "dataset_origin": "ACTUAL_PROVIDER_DATA",
        "raw_snapshot_hash": capture.raw_snapshot_hash,
        "paper_portfolio_id": paper_portfolio_id,
        "signals": [
            {
                "symbol": row["symbol"],
                "aegis_instrument_id": row["aegis_instrument_id"],
                "signal": row["signal"],
                "close": row["close"],
                "momentum_60": row["momentum_60"],
                "held": row["held"],
                "held_quantity": row["held_quantity"],
            }
            for row in rows
        ],
        "warnings": (
            []
            if paper_portfolio_id is not None
            else [
                "No paper_portfolio_id supplied -- HOLD/SELL cannot be determined, only BUY/NO_POSITION."
            ]
        ),
    }


# ---------------------------------------------------------------------------
# Achievements -- every one of these is a real, checkable condition over data
# that already exists elsewhere in this file (backtest equity curves, NAV
# history, approval timestamps). Nothing here is fabricated game state: each
# achievement's `detail` names the exact real number/date that earned it,
# and an unearned achievement says plainly why (no data yet, condition not
# met), never a vague "locked".
# ---------------------------------------------------------------------------


def _longest_leading_streak(
    leader_curve: list[dict[str, str]], other_curve: list[dict[str, str]]
) -> tuple[int, str | None, str | None]:
    """Longest run of consecutive real rebalance months where leader_curve's
    NAV exceeded other_curve's NAV on the same date. Returns
    (streak_length, start_date, end_date) for the longest such run."""
    other_nav_by_date = {point["date"]: Decimal(point["nav"]) for point in other_curve}
    best_len = 0
    best_start: str | None = None
    best_end: str | None = None
    current_len = 0
    current_start: str | None = None
    for point in leader_curve:
        other_nav = other_nav_by_date.get(point["date"])
        if other_nav is not None and Decimal(point["nav"]) > other_nav:
            if current_len == 0:
                current_start = point["date"]
            current_len += 1
            if current_len > best_len:
                best_len, best_start, best_end = current_len, current_start, point["date"]
        else:
            current_len = 0
            current_start = None
    return best_len, best_start, best_end


def _benchmark_beater_achievements() -> list[dict[str, Any]]:
    latest = _latest_momentum_reports_by_strategy()
    momentum = latest.get("TrendFollowingBaselineStrategyV0")
    achievements: list[dict[str, Any]] = []
    for benchmark_id in ("EqualWeightUniverseBenchmarkStrategyV0", "BuyAndHoldBenchmarkStrategyV0"):
        benchmark = latest.get(benchmark_id)
        description = (
            f"Beat {benchmark_id}'s real NAV for at least 3 consecutive real rebalance months."
        )
        if momentum is None or benchmark is None:
            achievements.append(
                {
                    "id": f"benchmark-beater-{benchmark_id}",
                    "category": "STRATEGY",
                    "title": f"Benchmark Beater: {benchmark_id}",
                    "description": description,
                    "achieved": False,
                    "achieved_at": None,
                    "detail": (
                        "No real backtest run yet for one or both strategies -- run one from "
                        "the Strategy Leaderboard."
                    ),
                }
            )
            continue
        streak, start, end = _longest_leading_streak(
            momentum["equity_curve"], benchmark["equity_curve"]
        )
        achieved = streak >= 3
        achievements.append(
            {
                "id": f"benchmark-beater-{benchmark_id}",
                "category": "STRATEGY",
                "title": f"Benchmark Beater: {benchmark_id}",
                "description": description,
                "achieved": achieved,
                "achieved_at": end if achieved else None,
                "detail": (
                    f"Beat {benchmark_id} for {streak} straight real rebalance months "
                    f"({start} to {end})"
                    if streak > 0
                    else f"Never led {benchmark_id} on a real rebalance month yet"
                ),
            }
        )
    return achievements


def _portfolio_nav_achievements(portfolio: Any, snapshots: list[Any]) -> list[dict[str, Any]]:
    hwm_id = f"new-high-water-mark-{portfolio.paper_portfolio_id}"
    recovery_id = f"drawdown-recovery-{portfolio.paper_portfolio_id}"
    hwm_description = "Portfolio NAV is at a real, current all-time high."
    recovery_description = (
        "Recovered from a real drawdown of 5% or worse back to within 1% of the high-water-mark."
    )
    if not snapshots:
        no_data = "No real trading sessions run yet for this portfolio."
        return [
            {
                "id": hwm_id,
                "category": "PORTFOLIO",
                "title": f"New High-Water Mark: {portfolio.name}",
                "description": hwm_description,
                "achieved": False,
                "achieved_at": None,
                "detail": no_data,
            },
            {
                "id": recovery_id,
                "category": "PORTFOLIO",
                "title": f"Recovered From Drawdown: {portfolio.name}",
                "description": recovery_description,
                "achieved": False,
                "achieved_at": None,
                "detail": no_data,
            },
        ]

    ordered = sorted(snapshots, key=lambda snapshot: snapshot.valuation_time)
    latest = ordered[-1]
    all_time_high_nav = max(snapshot.nav for snapshot in ordered)
    is_new_high = latest.nav == all_time_high_nav
    worst_drawdown = min(snapshot.drawdown for snapshot in ordered)
    recovered = worst_drawdown <= Decimal("-0.05") and latest.drawdown >= Decimal("-0.01")

    return [
        {
            "id": hwm_id,
            "category": "PORTFOLIO",
            "title": f"New High-Water Mark: {portfolio.name}",
            "description": hwm_description,
            "achieved": is_new_high,
            "achieved_at": latest.valuation_time.isoformat() if is_new_high else None,
            "detail": (
                f"₹{latest.nav} NAV on {latest.valuation_time.date().isoformat()} -- "
                "a real all-time high"
                if is_new_high
                else f"Current real NAV ₹{latest.nav}, all-time high ₹{all_time_high_nav}"
            ),
        },
        {
            "id": recovery_id,
            "category": "PORTFOLIO",
            "title": f"Recovered From Drawdown: {portfolio.name}",
            "description": recovery_description,
            "achieved": recovered,
            "achieved_at": latest.valuation_time.isoformat() if recovered else None,
            "detail": (
                f"Recovered from a real {worst_drawdown * 100:.1f}% drawdown back to "
                f"{latest.drawdown * 100:.1f}% as of {latest.valuation_time.date().isoformat()}"
                if recovered
                else (
                    f"Worst real drawdown so far: {worst_drawdown * 100:.1f}%, "
                    f"currently {latest.drawdown * 100:.1f}%"
                )
            ),
        },
    ]


def _first_live_approval_achievement(portfolio: Any) -> dict[str, Any]:
    approved_times = [
        approval.decision_time
        for intent in paper_repo.intents.values()
        if intent.paper_portfolio_id == portfolio.paper_portfolio_id
        for approval in [paper_repo.approvals.get(intent.paper_trade_intent_id)]
        if approval is not None and approval.decision == "APPROVED"
    ]
    achieved = len(approved_times) > 0
    first_time = min(approved_times) if achieved else None
    return {
        "id": f"first-live-approval-{portfolio.paper_portfolio_id}",
        "category": "PORTFOLIO",
        "title": f"First Live Approval: {portfolio.name}",
        "description": "A real paper-trade intent is approved for this portfolio for the first time.",
        "achieved": achieved,
        "achieved_at": first_time.isoformat() if first_time else None,
        "detail": (
            f"First real trade approved on {first_time.date().isoformat()}"
            if first_time is not None
            else "No real approvals yet for this portfolio."
        ),
    }


def _on_time_reviewer_achievement() -> dict[str, Any]:
    on_time = 0
    total = 0
    for intent_id, approval in paper_repo.approvals.items():
        intent = paper_repo.intents.get(intent_id)
        if intent is None:
            continue
        total += 1
        if approval.decision_time <= intent.eligible_execution_time:
            on_time += 1
    # Achieved means real good process, not mere participation -- a 0-of-36
    # on-time rate must never read as "achieved" just because decisions
    # exist at all. Integer comparison avoids any float/Decimal division.
    achieved = total > 0 and on_time * 2 >= total
    return {
        "id": "on-time-reviewer",
        "category": "PROCESS",
        "title": "On-Time Reviewer",
        "description": (
            "At least half of all real approval/rejection decisions made before the "
            "intent's eligible execution time."
        ),
        "achieved": achieved,
        "achieved_at": None,
        "detail": (
            f"{on_time} of {total} real decisions made before the eligible execution window"
            if total > 0
            else "No real approval decisions made yet."
        ),
    }


def _compute_achievements() -> list[dict[str, Any]]:
    achievements = _benchmark_beater_achievements()
    for portfolio in paper_repo.portfolios.values():
        achievements.extend(
            _portfolio_nav_achievements(portfolio, paper_repo.nav.get(portfolio.paper_portfolio_id, []))
        )
        achievements.append(_first_live_approval_achievement(portfolio))
    achievements.append(_on_time_reviewer_achievement())
    return achievements


@app.get("/api/v1/achievements")
def get_achievements() -> dict[str, Any]:
    return {"achievements": _compute_achievements()}


@app.get("/api/v1/instruments/{symbol}/rule-events")
def get_instrument_rule_events(
    symbol: str,
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
) -> dict[str, Any]:
    canonical, aegis_instrument_id = _resolve_symbol(symbol)
    capture = _load_capture_or_409()
    runner = RealMomentumResearchRunner(capture, sector_by_instrument_id)
    strategy = TrendFollowingBaselineStrategyV0()
    start, end = _date_range_or_default(capture, from_date, to_date)
    trading_dates = [d for d in runner.trading_dates if start <= d <= end]

    series = runner.build_candidate_series(aegis_instrument_id, trading_dates)
    events: list[dict[str, str]] = []
    was_eligible = False
    for as_of in trading_dates:
        candidate = series[as_of]
        # Eligibility is a pure per-candidate threshold check (see
        # rank_candidates) -- ranking a single-instrument list is equivalent
        # to checking membership against the whole universe's eligible set,
        # without paying to rebuild the other 49 instruments' candidates.
        is_eligible = candidate is not None and bool(strategy.rank_candidates([candidate]))
        if is_eligible and not was_eligible:
            events.append({"date": as_of.isoformat(), "type": "ELIGIBILITY_START"})
        elif was_eligible and not is_eligible:
            events.append({"date": as_of.isoformat(), "type": "ELIGIBILITY_END"})
        was_eligible = is_eligible

    return {
        "symbol": canonical,
        "aegis_instrument_id": aegis_instrument_id,
        "dataset_origin": "ACTUAL_PROVIDER_DATA",
        "raw_snapshot_hash": capture.raw_snapshot_hash,
        "events": events,
    }


@app.get("/api/v1/paper-portfolios")
def list_paper_portfolios() -> list[dict[str, Any]]:
    return [
        jsonable(portfolio) | {"labels": list(PAPER_LABELS)}
        for portfolio in paper_repo.portfolios.values()
    ]


@app.post("/api/v1/paper-portfolios")
def create_paper_portfolio(
    payload: dict[str, Any],
    role: Role = Depends(require_role(Role.FOUNDER)),
) -> dict[str, Any]:
    portfolio = paper_orchestrator.create_portfolio(
        name=payload["name"],
        description=payload.get("description", "Forward-only paper portfolio"),
        starting_capital=Decimal(str(payload.get("starting_capital", "100000"))),
        created_by=role.value,
    )
    return jsonable(portfolio) | {"labels": list(PAPER_LABELS)}


@app.get("/api/v1/paper-portfolios/{paper_portfolio_id}")
def get_paper_portfolio(paper_portfolio_id: str) -> dict[str, Any]:
    return jsonable(paper_repo.portfolios[paper_portfolio_id]) | {"labels": list(PAPER_LABELS)}


@app.post("/api/v1/paper-portfolios/{paper_portfolio_id}/activate")
def activate_paper_portfolio(
    paper_portfolio_id: str, role: Role = Depends(require_role(Role.FOUNDER))
) -> dict[str, Any]:
    config = paper_orchestrator.create_strategy_config(paper_portfolio_id)
    paper_orchestrator.admit_and_activate_strategy(
        config.paper_strategy_config_id, all_admission_evidence(), role.value
    )
    return jsonable(paper_repo.portfolios[paper_portfolio_id]) | {"labels": list(PAPER_LABELS)}


@app.post("/api/v1/paper-portfolios/{paper_portfolio_id}/pause")
def pause_paper_portfolio(paper_portfolio_id: str) -> dict[str, Any]:
    portfolio = paper_repo.portfolios[paper_portfolio_id].pause("PAUSED_BY_USER")
    paper_repo.save_portfolio(portfolio)
    return jsonable(portfolio)


@app.post("/api/v1/paper-portfolios/{paper_portfolio_id}/resume")
def resume_paper_portfolio(paper_portfolio_id: str) -> dict[str, Any]:
    portfolio = paper_repo.portfolios[paper_portfolio_id]
    if portfolio.status != PaperPortfolioStatus.PAUSED:
        raise HTTPException(status_code=400, detail=f"PORTFOLIO_NOT_PAUSED:{portfolio.status}")
    resumed = replace(portfolio, status=PaperPortfolioStatus.ACTIVE)
    paper_repo.save_portfolio(resumed)
    return jsonable(resumed)


@app.post("/api/v1/paper-portfolios/{paper_portfolio_id}/freeze")
def freeze_paper_portfolio(paper_portfolio_id: str) -> dict[str, Any]:
    portfolio = paper_repo.portfolios[paper_portfolio_id].freeze("FROZEN_BY_USER")
    paper_repo.save_portfolio(portfolio)
    return jsonable(portfolio)


@app.post("/api/v1/paper-portfolios/{paper_portfolio_id}/complete")
def complete_paper_portfolio(paper_portfolio_id: str) -> dict[str, Any]:
    from dataclasses import replace

    portfolio = paper_repo.portfolios[paper_portfolio_id]
    completed = replace(
        portfolio,
        status=PaperPortfolioStatus.COMPLETED,
        completed_at_nullable=datetime.now().astimezone(),
    )
    paper_repo.save_portfolio(completed)
    return jsonable(completed)


@app.get("/api/v1/paper-portfolios/{paper_portfolio_id}/summary")
def paper_portfolio_summary(paper_portfolio_id: str) -> dict[str, Any]:
    return {
        "portfolio": jsonable(paper_repo.portfolios[paper_portfolio_id]),
        "latest_nav": jsonable((paper_repo.nav.get(paper_portfolio_id) or [None])[-1]),
        "open_incidents": [
            jsonable(i)
            for i in paper_repo.incidents.values()
            if i.paper_portfolio_id == paper_portfolio_id and i.status == "OPEN"
        ],
        "labels": list(PAPER_LABELS),
    }


@app.get("/api/v1/paper-portfolios/{paper_portfolio_id}/nav-history")
def paper_nav_history(paper_portfolio_id: str) -> list[dict[str, Any]]:
    return [jsonable(item) for item in paper_repo.nav.get(paper_portfolio_id, [])]


@app.get("/api/v1/paper-portfolios/{paper_portfolio_id}/exposure-history")
def paper_exposure_history(paper_portfolio_id: str) -> list[dict[str, Any]]:
    return []


@app.get("/api/v1/paper-portfolios/{paper_portfolio_id}/risk-history")
def paper_risk_history(paper_portfolio_id: str) -> list[dict[str, Any]]:
    return []


@app.get("/api/v1/paper-portfolios/{paper_portfolio_id}/reconciliation")
def paper_reconciliation(paper_portfolio_id: str) -> list[dict[str, Any]]:
    return [jsonable(item) for item in paper_repo.reconciliations.get(paper_portfolio_id, [])]


@app.get("/api/v1/paper-strategy-configurations")
def paper_strategy_configurations() -> list[dict[str, Any]]:
    return [jsonable(item) for item in paper_repo.strategy_configs.values()]


@app.post("/api/v1/paper-strategy-configurations")
def create_paper_strategy_configuration(payload: dict[str, Any]) -> dict[str, Any]:
    kwargs = {}
    if "strategy_id" in payload:
        kwargs["strategy_id"] = payload["strategy_id"]
    return jsonable(
        paper_orchestrator.create_strategy_config(payload["paper_portfolio_id"], **kwargs)
    )


@app.post("/api/v1/paper-strategy-configurations/{paper_strategy_config_id}/admission-review")
def paper_admission_review(paper_strategy_config_id: str) -> dict[str, Any]:
    failures = paper_orchestrator.admission.review(all_admission_evidence())
    return {
        "paper_strategy_config_id": paper_strategy_config_id,
        "failures": failures,
        "ready": not failures,
    }


@app.post("/api/v1/paper-strategy-configurations/{paper_strategy_config_id}/freeze")
def freeze_paper_strategy_configuration(paper_strategy_config_id: str) -> dict[str, Any]:
    config = paper_repo.strategy_configs[paper_strategy_config_id].freeze()
    paper_repo.save_strategy_config(config)
    return jsonable(config)


@app.post("/api/v1/paper-strategy-configurations/{paper_strategy_config_id}/activate")
def activate_paper_strategy_configuration(
    paper_strategy_config_id: str,
    role: Role = Depends(require_role(Role.FOUNDER, Role.RISK_REVIEWER, Role.DATA_STEWARD)),
) -> dict[str, Any]:
    return jsonable(
        paper_orchestrator.admit_and_activate_strategy(
            paper_strategy_config_id, all_admission_evidence(), role.value
        )
    )


@app.get("/api/v1/paper-strategy-configurations/{paper_strategy_config_id}/evidence-package")
def paper_strategy_evidence(paper_strategy_config_id: str) -> dict[str, Any]:
    config = paper_repo.strategy_configs[paper_strategy_config_id]
    return jsonable(paper_orchestrator.evidence_package(config.paper_portfolio_id))


@app.get("/api/v1/paper-trading-sessions")
def paper_sessions() -> list[dict[str, Any]]:
    return [jsonable(item) for item in paper_repo.sessions.values()]


@app.get("/api/v1/paper-session-jobs")
def paper_session_jobs() -> list[dict[str, Any]]:
    return paper_session_queue.list_jobs()


@app.post("/api/v1/paper-session-jobs")
def enqueue_paper_session_job(payload: dict[str, Any]) -> dict[str, Any]:
    if "reference_prices" in payload:
        reference_prices = {
            instrument_id: Decimal(str(price))
            for instrument_id, price in payload["reference_prices"].items()
        }
    else:
        reference_prices = real_reference_prices(instrument_master.known_aegis_ids())
    job = PaperSessionJob(
        paper_portfolio_id=payload["paper_portfolio_id"],
        session_date=date.fromisoformat(payload.get("session_date", "2026-06-26")),
        readiness_flags=payload.get("readiness_flags", all_readiness_green()),
        reference_prices=reference_prices,
    )
    return jsonable(paper_session_queue.enqueue(job))


@app.post("/api/v1/paper-session-jobs/run-next")
def run_next_paper_session_job() -> dict[str, Any]:
    job = paper_session_queue.run_once(paper_orchestrator)
    if job is None:
        return {"status": "NO_QUEUED_JOB"}
    return {"status": "COMPLETED", "job_id": job.id}


@app.post("/api/v1/paper-trading-sessions/run")
def run_paper_session(payload: dict[str, Any]) -> dict[str, Any]:
    if "reference_prices" in payload:
        reference_prices = {
            instrument_id: Decimal(str(price))
            for instrument_id, price in payload["reference_prices"].items()
        }
    else:
        reference_prices = real_reference_prices(instrument_master.known_aegis_ids())
    session = paper_orchestrator.run_decision_cycle(
        paper_portfolio_id=payload["paper_portfolio_id"],
        session_date=date.fromisoformat(payload.get("session_date", "2026-06-26")),
        readiness_flags=all_readiness_green(),
        reference_prices=reference_prices,
    )
    return jsonable(session)


@app.get("/api/v1/paper-trade-intents")
def paper_trade_intents() -> list[dict[str, Any]]:
    return [jsonable(item) for item in paper_repo.intents.values()]


@app.post("/api/v1/paper-trade-intents/{paper_trade_intent_id}/approve")
def approve_paper_intent(
    paper_trade_intent_id: str,
    role: Role = Depends(
        require_role(Role.FOUNDER, Role.RISK_REVIEWER, Role.PAPER_TRADING_OPERATOR)
    ),
) -> dict[str, Any]:
    try:
        return jsonable(paper_orchestrator.approvals.approve(paper_trade_intent_id, role.value))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": str(exc)}) from exc


@app.post("/api/v1/paper-trade-intents/{paper_trade_intent_id}/reject")
def reject_paper_intent(
    paper_trade_intent_id: str,
    payload: dict[str, Any],
    role: Role = Depends(
        require_role(Role.FOUNDER, Role.RISK_REVIEWER, Role.PAPER_TRADING_OPERATOR)
    ),
) -> dict[str, Any]:
    try:
        return jsonable(
            paper_orchestrator.approvals.reject(
                paper_trade_intent_id, role.value, payload["reason"]
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": str(exc)}) from exc


@app.get("/api/v1/paper-approvals")
def paper_approvals() -> list[dict[str, Any]]:
    return [jsonable(item) for item in paper_repo.approvals.values()]


@app.get("/api/v1/paper-orders")
def paper_orders() -> list[dict[str, Any]]:
    return [jsonable(item) for item in paper_repo.orders.values()]


@app.get("/api/v1/paper-fills")
def paper_fills() -> list[dict[str, Any]]:
    return [jsonable(item) for item in paper_repo.fills.values()]


@app.get("/api/v1/paper-incidents")
def paper_incidents() -> list[dict[str, Any]]:
    return [jsonable(item) for item in paper_repo.incidents.values()]


@app.get("/api/v1/paper-corporate-action-reviews")
def paper_corporate_action_reviews() -> list[dict[str, Any]]:
    return [jsonable(item) for item in paper_repo.corporate_action_reviews.values()]


@app.post("/api/v1/paper-corporate-action-reviews")
def create_paper_corporate_action_review(
    payload: dict[str, Any],
    role: Role = Depends(require_role(Role.FOUNDER, Role.DATA_STEWARD, Role.RISK_REVIEWER)),
) -> dict[str, Any]:
    review = paper_orchestrator.corporate_actions.review(
        paper_portfolio_id=payload["paper_portfolio_id"],
        instrument_id=payload["instrument_id"],
        action_type=payload["action_type"],
        effective_date=date.fromisoformat(payload["effective_date"]),
        verification_status=payload.get("verification_status", "PENDING"),
        supported=bool(payload.get("supported", False)),
        reviewer_id=role.value,
        correlation_id=payload.get("correlation_id", "api-corporate-action-review"),
    )
    return jsonable(review)


@app.get("/api/v1/paper-drift-assessments")
def paper_drift() -> list[dict[str, Any]]:
    return [jsonable(item) for item in paper_repo.drift.values()]


@app.post("/api/v1/paper-incidents/{paper_incident_id}/resolve")
def resolve_paper_incident(paper_incident_id: str) -> dict[str, Any]:
    from dataclasses import replace

    incident = paper_repo.incidents[paper_incident_id]
    resolved = replace(
        incident, status="RESOLVED", resolved_at_nullable=datetime.now().astimezone()
    )
    paper_repo.incidents[paper_incident_id] = resolved
    return jsonable(resolved)


@app.post("/api/v1/kill-switches/{kill_switch_id}/activate")
def activate_kill_switch(kill_switch_id: str) -> dict[str, Any]:
    switch = paper_orchestrator.activate_kill_switch(
        KillSwitchType.PORTFOLIO_KILL_SWITCH, kill_switch_id, "API activation"
    )
    return jsonable(switch)


@app.post("/api/v1/kill-switches/{kill_switch_id}/deactivate")
def deactivate_kill_switch(kill_switch_id: str) -> dict[str, Any]:
    return {"kill_switch_id": kill_switch_id, "status": "DEACTIVATION_REQUIRES_DOCUMENTED_REVIEW"}


@app.get("/api/v1/audit-events")
def list_audit_events() -> list[dict[str, Any]]:
    return audit_log.as_dicts()


@app.get("/api/v1/audit-events/{event_id}")
def get_audit_event(event_id: str) -> dict[str, Any]:
    event = audit_log.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Audit event not found.")
    return as_dict(event)
