from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from aegis.audit.service import AuditLog
from aegis.backtesting.domain import BacktestRunStatus, OrderSide, SPRINT_1A_LABELS
from aegis.backtesting.engine import BacktestService
from aegis.backtesting.fixtures import load_calendar, load_market_data
from aegis.backtesting.repositories import BacktestRepository
from aegis.backtesting.sprint2 import Sprint2ResearchScenarioRunner
from aegis.configuration.settings import Settings
from aegis.data_ingestion.service import InMemoryRepository, LocalObjectStore, ProviderIngestionService
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
from aegis.provider_adapters.csv_provider import CsvFileProvider
from aegis.provider_adapters.live_readonly_provider import LiveReadOnlyMarketDataProvider
from aegis.provider_adapters.mock_provider import MockMarketDataProvider
from aegis.paper_trading.domain import PAPER_LABELS, IncidentType, PaperPortfolioStatus
from aegis.paper_trading.persistence import SqlitePaperTradingRepository
from aegis.paper_trading.queue import PaperSessionJob, SqlitePaperSessionQueue
from aegis.paper_trading.services import (
    PaperTradingCalendarService,
    PaperTradingOrchestrator,
    all_admission_evidence,
    all_readiness_green,
)
from aegis.research_registry.sprint2 import RESEARCH_LABELS
from aegis.risk.engine import KillSwitchType, RiskProfileVersion


settings = Settings.from_env()
settings.validate_startup()

app = FastAPI(title="AEGIS Sprint 0 API", version="0.1.0")
audit_log = AuditLog()
repo = InMemoryRepository()
backtest_repo = BacktestRepository()
object_store = LocalObjectStore(Path("work/object_store"))
ingestion_service = ProviderIngestionService(
    object_store=object_store,
    repository=repo,
    audit_log=audit_log,
)
instrument_master = InstrumentMasterService()
backtest_service = BacktestService(backtest_repo, audit_log)
paper_store_path = Path("work/paper_trading.sqlite")
paper_store_path.parent.mkdir(parents=True, exist_ok=True)
paper_queue_path = Path("work/paper_session_queue.sqlite")
paper_calendar = PaperTradingCalendarService.from_csv(Path("sample_data/sprint_3/forward_market_calendar.csv"))
paper_repo = SqlitePaperTradingRepository(paper_store_path)
paper_orchestrator = PaperTradingOrchestrator(paper_repo, audit_log, calendar=paper_calendar)
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
    license_status=ProviderLicenseStatus.APPROVED,
    permitted_use="Read-only instrument, EOD, quote, and calendar ingestion",
    automation_rights=True,
    backtesting_rights=True,
    model_training_rights=False,
    dashboard_display_rights=True,
    data_retention_period="provider-contract-controlled",
    legal_review_status="APPROVED_READONLY_DATA",
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
seed_instrument = Instrument(
    aegis_instrument_id="AEGIS-IN-000001",
    isin="INE002A01018",
    company_legal_name="Reliance Industries Limited",
    security_type="EQUITY",
    current_symbol="RELIANCE",
    primary_exchange="NSE",
    listing_date=date(1995, 1, 1),
    trading_status="ACTIVE",
    sector="Energy",
    industry="Oil, Gas and Consumable Fuels",
    mapping_confidence_score=0.99,
)
instrument_master.add_instrument(seed_instrument)
fixture_calendar = load_calendar(Path("sample_data/backtesting/market_calendar.csv"))
fixture_market_data = load_market_data(Path("sample_data/backtesting/valid_eod_prices.csv"), "dataset-version-1")
backtest_service.attach_calendar_for_intent_creation(fixture_calendar)
sprint2_runner = Sprint2ResearchScenarioRunner(Path("sample_data/sprint_2"))
sprint2_reports: list[dict[str, Any]] = []


def correlation_id(request: Request) -> str:
    return request.headers.get("X-Correlation-ID", str(uuid4()))


def require_role(*allowed: Role):
    def dependency(x_aegis_role: str = Header(default=Role.READ_ONLY.value)) -> Role:
        role = Role(x_aegis_role)
        if role not in allowed:
            raise HTTPException(status_code=403, detail=f"Role {role} cannot perform this action.")
        return role

    return dependency


def as_dict(value: Any) -> dict[str, Any]:
    return asdict(value)


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
        "critical_incidents_count": 0,
        "configuration": settings.redacted(),
    }


@app.get("/api/v1/data-source/mode")
def data_source_mode() -> dict[str, Any]:
    return {
        "data_source_mode": settings.data_source_mode,
        "live_execution_enabled": settings.live_execution_enabled,
        "broker_order_access": settings.broker_order_access,
        "allowed_operations": [
            "instrument_master_sync",
            "historical_eod_ohlcv_ingestion",
            "live_quote_ingestion",
            "market_calendar_sync",
            "provider_health_check",
            "data_freshness_check",
        ],
        "prohibited_operations": ["place_order", "submit_order", "cancel_order", "modify_order", "holdings_mutation", "live_trading"],
    }


@app.get("/api/v1/system/incidents")
def incidents() -> list[dict[str, Any]]:
    return []


@app.get("/api/v1/providers")
def list_providers() -> list[dict[str, Any]]:
    return [as_dict(provider) for provider in providers.values()]


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
    return as_dict(providers[provider_id])


@app.post("/api/v1/providers/{provider_id}/health-check")
def provider_health(provider_id: str) -> dict[str, Any]:
    provider = providers[provider_id]
    if provider_id == live_readonly_provider_record.id:
        adapter = LiveReadOnlyMarketDataProvider(licenses[provider_id])
        return ingestion_service.check_provider_health(provider=adapter, provider_id=provider_id)
    return {"provider_id": provider.id, "healthy": provider.is_active, "message": "registered", "order_access": False}


@app.post("/api/v1/data-source/live-readonly/sync")
def sync_live_readonly_data(
    cid: str = Depends(correlation_id),
    role: Role = Depends(require_role(Role.FOUNDER, Role.DATA_STEWARD)),
) -> dict[str, Any]:
    adapter = LiveReadOnlyMarketDataProvider(licenses[live_readonly_provider_record.id])
    health = ingestion_service.check_provider_health(provider=adapter, provider_id=live_readonly_provider_record.id, correlation_id=cid)
    instrument_run = ingestion_service.sync_instrument_master(
        provider=adapter,
        provider_id=live_readonly_provider_record.id,
        instrument_master=instrument_master,
        correlation_id=cid,
    )
    eod_run = ingestion_service.ingest_eod_prices(
        provider=adapter,
        provider_id=live_readonly_provider_record.id,
        dataset_id=seed_dataset.id,
        dataset_name=seed_dataset.name,
        known_instrument_ids=instrument_master.known_aegis_ids(),
        correlation_id=cid,
    )
    quote_run = ingestion_service.ingest_live_quotes(
        provider=adapter,
        provider_id=live_readonly_provider_record.id,
        dataset_id=live_quote_dataset.id,
        known_instrument_ids=instrument_master.known_aegis_ids(),
        correlation_id=cid,
    )
    calendar_run = ingestion_service.sync_market_calendar(
        provider=adapter,
        provider_id=live_readonly_provider_record.id,
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
    if live_readonly_provider_record.id not in repo.provider_health:
        adapter = LiveReadOnlyMarketDataProvider(licenses[live_readonly_provider_record.id])
        ingestion_service.check_provider_health(provider=adapter, provider_id=live_readonly_provider_record.id)
    return list(repo.provider_health.values())


@app.get("/api/v1/data-freshness")
def list_data_freshness() -> list[dict[str, Any]]:
    return list(repo.data_freshness.values())


@app.get("/api/v1/live-quotes")
def list_live_quotes() -> list[dict[str, Any]]:
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


@app.get("/api/v1/dataset-versions/{dataset_version_id}/lineage")
def dataset_lineage(dataset_version_id: str) -> dict[str, Any]:
    version = repo.dataset_versions[dataset_version_id]
    raw = next(obj for obj in repo.raw_objects.values() if obj.content_hash == version.raw_snapshot_hash)
    return {"dataset_version": as_dict(version), "raw_object": as_dict(raw)}


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


@app.get("/api/v1/instruments")
def list_instruments() -> list[dict[str, Any]]:
    return [as_dict(instrument) for instrument in instrument_master.instruments.values()]


@app.post("/api/v1/instruments")
def create_instrument(payload: dict[str, Any], cid: str = Depends(correlation_id)) -> dict[str, Any]:
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
        verification_status=CorporateActionVerificationStatus(payload.get("verification_status", "RAW")),
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


@app.post("/api/v1/experiments/{experiment_id}/freeze-manifest")
def freeze_manifest(experiment_id: str) -> dict[str, Any]:
    return {"experiment_id": experiment_id, "is_frozen": True}


@app.get("/api/v1/backtest-runs")
def list_backtest_runs(
    role: Role = Depends(
        require_role(Role.FOUNDER, Role.RESEARCHER, Role.RISK_REVIEWER, Role.READ_ONLY)
    ),
) -> list[dict[str, Any]]:
    return [jsonable(run) | {"labels": list(SPRINT_1A_LABELS)} for run in backtest_repo.runs.values()]


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
        raise HTTPException(status_code=409, detail="Completed runs cannot be modified or cancelled.")
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


@app.get("/api/v1/feature-runs/{feature_run_id}")
def get_feature_run(feature_run_id: str) -> dict[str, Any]:
    return {"feature_run_id": feature_run_id, "status": "FIXTURE_ONLY", "classification": list(RESEARCH_LABELS)}


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
        raise HTTPException(status_code=400, detail="Sprint 2 strategies must remain RESEARCH_ONLY.")
    return {"strategy_id": str(uuid4()), **payload, "status": "RESEARCH_ONLY"}


@app.get("/api/v1/risk-profiles")
def get_risk_profiles() -> list[dict[str, Any]]:
    return [jsonable(RiskProfileVersion())]


@app.get("/api/v1/risk-profile-versions")
def get_risk_profile_versions() -> list[dict[str, Any]]:
    return [jsonable(RiskProfileVersion())]


@app.get("/api/v1/risk-assessments")
def get_sprint2_risk_assessments() -> list[dict[str, Any]]:
    return [assessment for report in sprint2_reports for assessment in report.get("risk_assessments", [])]


@app.get("/api/v1/risk-events")
def get_risk_events() -> list[dict[str, Any]]:
    return []


@app.get("/api/v1/kill-switches")
def get_kill_switches() -> list[dict[str, Any]]:
    return [jsonable(item) for item in paper_repo.kill_switches.values()]


@app.post("/api/v1/sprint-2/scenario-a")
def run_sprint2_scenario_a(role: Role = Depends(require_role(Role.FOUNDER, Role.RESEARCHER))) -> dict[str, Any]:
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


@app.get("/api/v1/paper-portfolios")
def list_paper_portfolios() -> list[dict[str, Any]]:
    return [jsonable(portfolio) | {"labels": list(PAPER_LABELS)} for portfolio in paper_repo.portfolios.values()]


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
def activate_paper_portfolio(paper_portfolio_id: str, role: Role = Depends(require_role(Role.FOUNDER))) -> dict[str, Any]:
    config = paper_orchestrator.create_strategy_config(paper_portfolio_id)
    paper_orchestrator.admit_and_activate_strategy(config.paper_strategy_config_id, all_admission_evidence(), role.value)
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
    resumed = replace(portfolio, status=PaperPortfolioStatus.ACTIVE, updated_at=datetime.now().astimezone())
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
    completed = replace(portfolio, status=PaperPortfolioStatus.COMPLETED, completed_at_nullable=datetime.now().astimezone())
    paper_repo.save_portfolio(completed)
    return jsonable(completed)


@app.get("/api/v1/paper-portfolios/{paper_portfolio_id}/summary")
def paper_portfolio_summary(paper_portfolio_id: str) -> dict[str, Any]:
    return {
        "portfolio": jsonable(paper_repo.portfolios[paper_portfolio_id]),
        "latest_nav": jsonable((paper_repo.nav.get(paper_portfolio_id) or [None])[-1]),
        "open_incidents": [jsonable(i) for i in paper_repo.incidents.values() if i.paper_portfolio_id == paper_portfolio_id and i.status == "OPEN"],
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
    return jsonable(paper_orchestrator.create_strategy_config(payload["paper_portfolio_id"]))


@app.post("/api/v1/paper-strategy-configurations/{paper_strategy_config_id}/admission-review")
def paper_admission_review(paper_strategy_config_id: str) -> dict[str, Any]:
    failures = paper_orchestrator.admission.review(all_admission_evidence())
    return {"paper_strategy_config_id": paper_strategy_config_id, "failures": failures, "ready": not failures}


@app.post("/api/v1/paper-strategy-configurations/{paper_strategy_config_id}/freeze")
def freeze_paper_strategy_configuration(paper_strategy_config_id: str) -> dict[str, Any]:
    config = paper_repo.strategy_configs[paper_strategy_config_id].freeze()
    paper_repo.save_strategy_config(config)
    return jsonable(config)


@app.post("/api/v1/paper-strategy-configurations/{paper_strategy_config_id}/activate")
def activate_paper_strategy_configuration(paper_strategy_config_id: str, role: Role = Depends(require_role(Role.FOUNDER, Role.RISK_REVIEWER, Role.DATA_STEWARD))) -> dict[str, Any]:
    return jsonable(paper_orchestrator.admit_and_activate_strategy(paper_strategy_config_id, all_admission_evidence(), role.value))


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
    job = PaperSessionJob(
        paper_portfolio_id=payload["paper_portfolio_id"],
        session_date=date.fromisoformat(payload.get("session_date", "2026-06-26")),
        readiness_flags=payload.get("readiness_flags", all_readiness_green()),
        reference_prices={
            instrument_id: Decimal(str(price))
            for instrument_id, price in payload.get("reference_prices", {"AEGIS-IN-000001": "112"}).items()
        },
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
    session = paper_orchestrator.run_decision_cycle(
        paper_portfolio_id=payload["paper_portfolio_id"],
        session_date=date.fromisoformat(payload.get("session_date", "2026-06-26")),
        readiness_flags=all_readiness_green(),
        reference_prices={"AEGIS-IN-000001": Decimal("112")},
    )
    return jsonable(session)


@app.get("/api/v1/paper-trade-intents")
def paper_trade_intents() -> list[dict[str, Any]]:
    return [jsonable(item) for item in paper_repo.intents.values()]


@app.post("/api/v1/paper-trade-intents/{paper_trade_intent_id}/approve")
def approve_paper_intent(paper_trade_intent_id: str, role: Role = Depends(require_role(Role.FOUNDER, Role.RISK_REVIEWER, Role.PAPER_TRADING_OPERATOR))) -> dict[str, Any]:
    return jsonable(paper_orchestrator.approvals.approve(paper_trade_intent_id, role.value))


@app.post("/api/v1/paper-trade-intents/{paper_trade_intent_id}/reject")
def reject_paper_intent(paper_trade_intent_id: str, payload: dict[str, Any], role: Role = Depends(require_role(Role.FOUNDER, Role.RISK_REVIEWER, Role.PAPER_TRADING_OPERATOR))) -> dict[str, Any]:
    return jsonable(paper_orchestrator.approvals.reject(paper_trade_intent_id, role.value, payload["reason"]))


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
def create_paper_corporate_action_review(payload: dict[str, Any], role: Role = Depends(require_role(Role.FOUNDER, Role.DATA_STEWARD, Role.RISK_REVIEWER))) -> dict[str, Any]:
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
    resolved = replace(incident, status="RESOLVED", resolved_at_nullable=datetime.now().astimezone())
    paper_repo.incidents[paper_incident_id] = resolved
    return jsonable(resolved)


@app.post("/api/v1/kill-switches/{kill_switch_id}/activate")
def activate_kill_switch(kill_switch_id: str) -> dict[str, Any]:
    switch = paper_orchestrator.activate_kill_switch(KillSwitchType.PORTFOLIO_KILL_SWITCH, kill_switch_id, "API activation")
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
