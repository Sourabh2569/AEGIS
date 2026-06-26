from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class StrEnum(str, Enum):
    pass


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ProviderLicenseStatus(StrEnum):
    APPROVED = "APPROVED"
    CONDITIONAL = "CONDITIONAL"
    PENDING = "PENDING"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class ValidationStatus(StrEnum):
    GREEN = "GREEN"
    GREEN_CAUTION = "GREEN_CAUTION"
    AMBER = "AMBER"
    RED = "RED"


class IngestionStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class QualityCategory(StrEnum):
    SCHEMA = "SCHEMA"
    STRUCTURAL = "STRUCTURAL"
    BUSINESS_RULE = "BUSINESS_RULE"
    TEMPORAL = "TEMPORAL"
    INSTRUMENT_MAPPING = "INSTRUMENT_MAPPING"
    CORPORATE_ACTION = "CORPORATE_ACTION"
    LICENSE = "LICENSE"
    LINEAGE = "LINEAGE"
    FRESHNESS = "FRESHNESS"
    DUPLICATE = "DUPLICATE"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class CorporateActionType(StrEnum):
    CASH_DIVIDEND = "CASH_DIVIDEND"
    STOCK_DIVIDEND = "STOCK_DIVIDEND"
    SPLIT = "SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    BONUS_ISSUE = "BONUS_ISSUE"
    RIGHTS_ISSUE = "RIGHTS_ISSUE"
    BUYBACK = "BUYBACK"
    MERGER = "MERGER"
    ACQUISITION = "ACQUISITION"
    DEMERGER = "DEMERGER"
    SPIN_OFF = "SPIN_OFF"
    SYMBOL_CHANGE = "SYMBOL_CHANGE"
    FACE_VALUE_CHANGE = "FACE_VALUE_CHANGE"
    DELISTING = "DELISTING"
    SUSPENSION = "SUSPENSION"
    OTHER = "OTHER"


class CorporateActionVerificationStatus(StrEnum):
    RAW = "RAW"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    AMBER = "AMBER"
    REJECTED = "REJECTED"


class Role(StrEnum):
    FOUNDER = "FOUNDER"
    DATA_STEWARD = "DATA_STEWARD"
    RESEARCHER = "RESEARCHER"
    RISK_REVIEWER = "RISK_REVIEWER"
    PAPER_TRADING_OPERATOR = "PAPER_TRADING_OPERATOR"
    ENGINEER = "ENGINEER"
    READ_ONLY = "READ_ONLY"
    SYSTEM_SERVICE = "SYSTEM_SERVICE"


@dataclass(frozen=True)
class DataProvider:
    name: str
    provider_type: str
    status: str = "REGISTERED"
    priority: int = 100
    base_url_or_reference: str | None = None
    is_active: bool = True
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)


@dataclass(frozen=True)
class ProviderLicense:
    provider_id: str
    license_status: ProviderLicenseStatus
    permitted_use: str
    automation_rights: bool
    backtesting_rights: bool
    model_training_rights: bool
    dashboard_display_rights: bool
    data_retention_period: str
    expiry_date: date | None = None
    legal_review_status: str = "PENDING"
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)


@dataclass(frozen=True)
class RawDataObject:
    provider_id: str
    source_reference: str
    content_hash: str
    schema_version: str
    ingestion_run_id: str
    storage_uri: str
    processing_status: str
    id: str = field(default_factory=lambda: str(uuid4()))
    retrieval_timestamp: datetime = field(default_factory=now_utc)


@dataclass(frozen=True)
class Dataset:
    name: str
    domain: str
    description: str
    owner: str
    criticality: str
    status: str = "REGISTERED"
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)


@dataclass(frozen=True)
class DatasetVersion:
    dataset_id: str
    provider_id: str
    schema_version: str
    raw_snapshot_hash: str
    transformation_version: str
    instrument_master_version: str
    corporate_action_version: str
    validation_status: ValidationStatus
    quality_score: float
    lineage_record_exists: bool
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=now_utc)
    approved_at: datetime | None = None


@dataclass(frozen=True)
class DataQualityResult:
    dataset_version_id: str
    check_name: str
    check_category: QualityCategory
    severity: Severity
    passed: bool
    message: str
    affected_record_count: int = 0
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=now_utc)


@dataclass(frozen=True)
class ProviderIngestionRun:
    provider_id: str
    dataset_name: str
    source_reference: str
    status: IngestionStatus
    correlation_id: str
    raw_object_hash: str | None = None
    records_received: int = 0
    records_accepted: int = 0
    records_rejected: int = 0
    validation_summary: dict[str, Any] = field(default_factory=dict)
    error_summary: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))
    started_at: datetime = field(default_factory=now_utc)
    completed_at: datetime | None = None


@dataclass(frozen=True)
class Instrument:
    aegis_instrument_id: str
    isin: str
    company_legal_name: str
    security_type: str
    current_symbol: str
    primary_exchange: str
    listing_date: date
    trading_status: str
    sector: str
    industry: str
    currency: str = "INR"
    lot_size: int = 1
    tick_size: float = 0.05
    liquidity_classification: str = "UNKNOWN"
    mapping_confidence_score: float = 0.0
    delisting_date: date | None = None
    last_verified_at: datetime | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)


@dataclass(frozen=True)
class InstrumentAlias:
    instrument_id: str
    alias_type: str
    alias_value: str
    source_provider: str
    valid_from: date
    valid_to: date | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=now_utc)


@dataclass(frozen=True)
class CorporateAction:
    instrument_id: str
    action_type: CorporateActionType
    announcement_time: datetime
    record_date: date | None
    ex_date: date | None
    effective_date: date | None
    ratio_or_amount: str
    currency: str
    source_reference: str
    verification_status: CorporateActionVerificationStatus
    adjustment_method: str
    adjustment_version: str
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    entity_type: str
    entity_id: str
    actor_type: str
    actor_id: str
    action: str
    before_state_json: dict[str, Any] | None
    after_state_json: dict[str, Any] | None
    metadata_json: dict[str, Any]
    correlation_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=now_utc)


@dataclass(frozen=True)
class ExperimentManifest:
    experiment_id: str
    dataset_version_id: str
    instrument_master_version: str
    corporate_action_version: str
    universe_version: str
    feature_versions_json: dict[str, str]
    backtest_engine_version: str
    transaction_cost_model_version: str
    slippage_model_version: str
    benchmark: str
    start_date: date
    end_date: date
    training_period: str
    validation_period: str
    holdout_period: str
    random_seed: int
    primary_metric: str
    secondary_metrics_json: list[str]
    rejection_criteria_json: dict[str, Any]
    is_frozen: bool = False
    frozen_at: datetime | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=now_utc)

    def freeze(self) -> "ExperimentManifest":
        return replace(self, is_frozen=True, frozen_at=now_utc())

    def update_metric(self, primary_metric: str) -> "ExperimentManifest":
        if self.is_frozen:
            raise ValueError("Experiment manifest is frozen and immutable.")
        return replace(self, primary_metric=primary_metric)
