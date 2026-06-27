from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

from aegis.audit.service import AuditLog
from aegis.data_quality.validation import (
    derive_validation_status,
    freshness_snapshot,
    quality_score,
    validate_eod_ohlcv,
    validate_live_quotes,
)
from aegis.domain.models import (
    DatasetVersion,
    IngestionStatus,
    Instrument,
    ProviderIngestionRun,
    RawDataObject,
)
from aegis.instrument_master.service import InstrumentMasterService
from aegis.provider_adapters.base import MarketDataProvider, ProviderResponseEnvelope
from aegis.provider_adapters.license_guard import ProviderLicenseGuard


def stable_payload_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        for prefix in ("raw", "normalized", "validated", "curated", "archive", "reports"):
            (self.root / prefix).mkdir(parents=True, exist_ok=True)

    def put_raw_once(self, object_name: str, payload: Any) -> str:
        return self.put_layer_once("raw", object_name, payload)

    def put_layer_once(self, layer: str, object_name: str, payload: Any) -> str:
        if layer not in {"raw", "normalized", "validated", "curated", "archive", "reports"}:
            raise ValueError(f"Unknown object-store layer: {layer}")
        target = self.root / layer / object_name
        if target.exists():
            raise FileExistsError(
                f"{layer} object already exists and will not be overwritten: {target}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        return f"file://{target}"


class InMemoryRepository:
    def __init__(self) -> None:
        self.ingestion_runs: dict[str, ProviderIngestionRun] = {}
        self.raw_objects: dict[str, RawDataObject] = {}
        self.dataset_versions: dict[str, DatasetVersion] = {}
        self.dataset_origins: dict[str, str] = {}
        self.quality_results: dict[str, list[Any]] = {}
        self.idempotency_keys: set[str] = set()
        self.layer_objects: dict[str, list[dict[str, Any]]] = {"normalized": [], "curated": []}
        self.provider_health: dict[str, dict[str, Any]] = {}
        self.data_freshness: dict[str, dict[str, Any]] = {}
        self.live_quotes: dict[str, dict[str, Any]] = {}
        self.market_calendar: dict[str, dict[str, Any]] = {}


class ProviderIngestionService:
    def __init__(
        self,
        *,
        object_store: LocalObjectStore,
        repository: InMemoryRepository,
        audit_log: AuditLog,
        license_guard: ProviderLicenseGuard | None = None,
    ) -> None:
        self.object_store = object_store
        self.repository = repository
        self.audit_log = audit_log
        self.license_guard = license_guard or ProviderLicenseGuard()

    def ingest_eod_prices(
        self,
        *,
        provider: MarketDataProvider,
        provider_id: str,
        dataset_id: str,
        dataset_name: str,
        known_instrument_ids: set[str],
        critical_dataset: bool = True,
        correlation_id: str | None = None,
    ) -> ProviderIngestionRun:
        correlation_id = correlation_id or str(uuid4())
        run = ProviderIngestionRun(
            provider_id=provider_id,
            dataset_name=dataset_name,
            source_reference="pending",
            status=IngestionStatus.RUNNING,
            correlation_id=correlation_id,
        )
        self.repository.ingestion_runs[run.id] = run

        try:
            self.license_guard.assert_ingestion_allowed(provider.get_license_status())
            envelope = provider.fetch_eod_prices()
            payload_hash = stable_payload_hash(envelope.payload)
            idempotency_key = f"{provider_id}:{envelope.source_reference}:{payload_hash}"
            if idempotency_key in self.repository.idempotency_keys:
                blocked = ProviderIngestionRun(
                    provider_id=provider_id,
                    dataset_name=dataset_name,
                    source_reference=envelope.source_reference,
                    status=IngestionStatus.BLOCKED,
                    correlation_id=correlation_id,
                    raw_object_hash=payload_hash,
                    records_received=len(envelope.payload),
                    error_summary=["Duplicate raw payload detected; no records created."],
                )
                self.repository.ingestion_runs[blocked.id] = blocked
                self.audit_log.record(
                    event_type="INGESTION_DUPLICATE",
                    entity_type="ProviderIngestionRun",
                    entity_id=blocked.id,
                    actor_type="SYSTEM_SERVICE",
                    actor_id="ingestion-service",
                    action="BLOCK_DUPLICATE",
                    before_state=None,
                    after_state=asdict(blocked),
                    metadata={"idempotency_key": idempotency_key},
                    correlation_id=correlation_id,
                )
                return blocked

            raw_uri = self._capture_raw(provider_id, run.id, envelope, payload_hash)
            dataset_version = DatasetVersion(
                dataset_id=dataset_id,
                provider_id=provider_id,
                schema_version=envelope.schema_version,
                raw_snapshot_hash=payload_hash,
                transformation_version="normalization.v1",
                instrument_master_version="instrument-master.v1",
                corporate_action_version="corporate-actions.v1",
                validation_status="GREEN",  # replaced below
                quality_score=100.0,
                lineage_record_exists=True,
            )
            accepted, rejected, quality_results = validate_eod_ohlcv(
                envelope.payload,
                known_instrument_ids,
                dataset_version.id,
            )
            validation_status = derive_validation_status(quality_results, critical_dataset)
            score = quality_score(quality_results)
            dataset_version = DatasetVersion(
                dataset_id=dataset_version.dataset_id,
                provider_id=dataset_version.provider_id,
                schema_version=dataset_version.schema_version,
                raw_snapshot_hash=dataset_version.raw_snapshot_hash,
                transformation_version=dataset_version.transformation_version,
                instrument_master_version=dataset_version.instrument_master_version,
                corporate_action_version=dataset_version.corporate_action_version,
                validation_status=validation_status,
                quality_score=score,
                lineage_record_exists=True,
                id=dataset_version.id,
            )
            self.repository.dataset_versions[dataset_version.id] = dataset_version
            self.repository.quality_results[dataset_version.id] = quality_results
            self.repository.idempotency_keys.add(idempotency_key)
            normalized_uri, curated_uri = self._capture_normalized_and_curated(
                provider_id, envelope.endpoint, payload_hash, accepted
            )

            completed = ProviderIngestionRun(
                provider_id=provider_id,
                dataset_name=dataset_name,
                source_reference=envelope.source_reference,
                status=IngestionStatus.COMPLETED
                if not rejected
                else IngestionStatus.COMPLETED_WITH_WARNINGS,
                correlation_id=correlation_id,
                raw_object_hash=payload_hash,
                records_received=len(envelope.payload),
                records_accepted=len(accepted),
                records_rejected=len(rejected),
                validation_summary={
                    "dataset_version_id": dataset_version.id,
                    "status": validation_status,
                },
                error_summary=[reason for item in rejected for reason in item["reasons"]],
            )
            self.repository.ingestion_runs[completed.id] = completed
            self.audit_log.record(
                event_type="INGESTION_COMPLETED",
                entity_type="ProviderIngestionRun",
                entity_id=completed.id,
                actor_type="SYSTEM_SERVICE",
                actor_id="ingestion-service",
                action="INGEST_EOD_PRICES",
                before_state=None,
                after_state=asdict(completed),
                metadata={
                    "raw_uri": raw_uri,
                    "normalized_uri": normalized_uri,
                    "curated_uri": curated_uri,
                    "dataset_version_id": dataset_version.id,
                },
                correlation_id=correlation_id,
            )
            return completed
        except PermissionError as exc:
            blocked = ProviderIngestionRun(
                provider_id=provider_id,
                dataset_name=dataset_name,
                source_reference="blocked-before-fetch",
                status=IngestionStatus.BLOCKED,
                correlation_id=correlation_id,
                error_summary=[str(exc)],
            )
            self.repository.ingestion_runs[blocked.id] = blocked
            self.audit_log.record(
                event_type="INGESTION_BLOCKED",
                entity_type="ProviderIngestionRun",
                entity_id=blocked.id,
                actor_type="SYSTEM_SERVICE",
                actor_id="ingestion-service",
                action="BLOCK_LICENSE",
                before_state=None,
                after_state=asdict(blocked),
                metadata={},
                correlation_id=correlation_id,
            )
            return blocked

    def sync_instrument_master(
        self,
        *,
        provider: MarketDataProvider,
        provider_id: str,
        instrument_master: InstrumentMasterService,
        correlation_id: str | None = None,
    ) -> ProviderIngestionRun:
        correlation_id = correlation_id or str(uuid4())
        self.license_guard.assert_ingestion_allowed(provider.get_license_status())
        envelope = provider.fetch_instruments()
        payload_hash = stable_payload_hash(envelope.payload)
        run = self._start_layer_run(
            provider_id, "instrument_master", envelope, payload_hash, correlation_id
        )
        raw_uri = self._capture_raw(provider_id, run.id, envelope, payload_hash)
        normalized = [self._normalize_instrument(record) for record in envelope.payload]
        normalized_uri, curated_uri = self._capture_normalized_and_curated(
            provider_id, envelope.endpoint, payload_hash, normalized
        )

        known = instrument_master.known_aegis_ids()
        accepted = 0
        for record in normalized:
            if record["aegis_instrument_id"] in known:
                continue
            instrument_master.add_instrument(Instrument(**record))
            accepted += 1
        completed = self._complete_layer_run(
            run,
            envelope,
            payload_hash,
            records_accepted=accepted,
            records_rejected=0,
            validation_summary={
                "status": "GREEN",
                "layer": "curated",
                "instrument_master_count": len(instrument_master.instruments),
            },
        )
        self._audit_layer_event(
            "INSTRUMENT_MASTER_SYNCED",
            completed,
            "SYNC_INSTRUMENT_MASTER",
            {"raw_uri": raw_uri, "normalized_uri": normalized_uri, "curated_uri": curated_uri},
        )
        return completed

    def sync_market_calendar(
        self,
        *,
        provider: MarketDataProvider,
        provider_id: str,
        correlation_id: str | None = None,
    ) -> ProviderIngestionRun:
        correlation_id = correlation_id or str(uuid4())
        self.license_guard.assert_ingestion_allowed(provider.get_license_status())
        envelope = provider.fetch_market_calendar()
        payload_hash = stable_payload_hash(envelope.payload)
        run = self._start_layer_run(
            provider_id, "market_calendar", envelope, payload_hash, correlation_id
        )
        raw_uri = self._capture_raw(provider_id, run.id, envelope, payload_hash)
        normalized = [dict(record) for record in envelope.payload]
        normalized_uri, curated_uri = self._capture_normalized_and_curated(
            provider_id, envelope.endpoint, payload_hash, normalized
        )
        for record in normalized:
            key = f"{record.get('exchange')}:{record.get('session_date')}"
            self.repository.market_calendar[key] = record
        completed = self._complete_layer_run(
            run,
            envelope,
            payload_hash,
            records_accepted=len(normalized),
            records_rejected=0,
            validation_summary={"status": "GREEN", "governs_execution_dates": True},
        )
        self._audit_layer_event(
            "MARKET_CALENDAR_SYNCED",
            completed,
            "SYNC_MARKET_CALENDAR",
            {"raw_uri": raw_uri, "normalized_uri": normalized_uri, "curated_uri": curated_uri},
        )
        return completed

    def ingest_live_quotes(
        self,
        *,
        provider: MarketDataProvider,
        provider_id: str,
        dataset_id: str,
        known_instrument_ids: set[str],
        correlation_id: str | None = None,
    ) -> ProviderIngestionRun:
        correlation_id = correlation_id or str(uuid4())
        self.license_guard.assert_ingestion_allowed(provider.get_license_status())
        envelope = provider.fetch_live_quotes()
        payload_hash = stable_payload_hash(envelope.payload)
        run = self._start_layer_run(
            provider_id, "live_quotes", envelope, payload_hash, correlation_id
        )
        raw_uri = self._capture_raw(provider_id, run.id, envelope, payload_hash)
        dataset_version = DatasetVersion(
            dataset_id=dataset_id,
            provider_id=provider_id,
            schema_version=envelope.schema_version,
            raw_snapshot_hash=payload_hash,
            transformation_version="quote-normalization.v1",
            instrument_master_version="instrument-master.v1",
            corporate_action_version="corporate-actions.v1",
            validation_status="GREEN",
            quality_score=100.0,
            lineage_record_exists=True,
        )
        accepted, rejected, quality_results = validate_live_quotes(
            envelope.payload, known_instrument_ids, dataset_version.id
        )
        validation_status = derive_validation_status(quality_results, critical_dataset=True)
        version = DatasetVersion(
            dataset_id=dataset_version.dataset_id,
            provider_id=dataset_version.provider_id,
            schema_version=dataset_version.schema_version,
            raw_snapshot_hash=dataset_version.raw_snapshot_hash,
            transformation_version=dataset_version.transformation_version,
            instrument_master_version=dataset_version.instrument_master_version,
            corporate_action_version=dataset_version.corporate_action_version,
            validation_status=validation_status,
            quality_score=quality_score(quality_results),
            lineage_record_exists=True,
            id=dataset_version.id,
        )
        self.repository.dataset_versions[version.id] = version
        self.repository.quality_results[version.id] = quality_results
        normalized_uri, curated_uri = self._capture_normalized_and_curated(
            provider_id, envelope.endpoint, payload_hash, accepted
        )
        for record in accepted:
            self.repository.live_quotes[str(record["aegis_instrument_id"])] = record
        self.repository.data_freshness["live_quotes"] = freshness_snapshot(
            records=accepted, dataset_name="live_quotes", max_age_seconds=900
        )
        completed = self._complete_layer_run(
            run,
            envelope,
            payload_hash,
            records_accepted=len(accepted),
            records_rejected=len(rejected),
            validation_summary={
                "dataset_version_id": version.id,
                "status": validation_status,
                "freshness": self.repository.data_freshness["live_quotes"],
            },
            error_summary=[reason for item in rejected for reason in item["reasons"]],
        )
        self._audit_layer_event(
            "LIVE_QUOTES_INGESTED_READONLY",
            completed,
            "INGEST_LIVE_QUOTES_READONLY",
            {
                "raw_uri": raw_uri,
                "normalized_uri": normalized_uri,
                "curated_uri": curated_uri,
                "dataset_version_id": version.id,
            },
        )
        return completed

    def check_provider_health(
        self,
        *,
        provider: MarketDataProvider,
        provider_id: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        correlation_id = correlation_id or str(uuid4())
        result = provider.get_health_status()
        snapshot = {
            "provider_id": provider_id,
            "provider_name": provider.name,
            "healthy": result.healthy,
            "message": result.message,
            "checked_at": result.checked_at.isoformat() if result.checked_at else None,
            "latency_ms": result.latency_ms,
            "mode": result.mode,
            "order_access": result.order_access,
        }
        self.repository.provider_health[provider_id] = snapshot
        self.audit_log.record(
            event_type="PROVIDER_HEALTH_CHECKED",
            entity_type="DataProvider",
            entity_id=provider_id,
            actor_type="SYSTEM_SERVICE",
            actor_id="ingestion-service",
            action="CHECK_PROVIDER_HEALTH",
            before_state=None,
            after_state=snapshot,
            metadata={"read_only": not result.order_access},
            correlation_id=correlation_id,
        )
        return snapshot

    def _capture_raw(
        self,
        provider_id: str,
        ingestion_run_id: str,
        envelope: ProviderResponseEnvelope,
        payload_hash: str,
    ) -> str:
        object_name = f"{provider_id}/{envelope.endpoint}/{payload_hash}.json"
        uri = self.object_store.put_raw_once(object_name, envelope.payload)
        raw = RawDataObject(
            provider_id=provider_id,
            source_reference=envelope.source_reference,
            content_hash=payload_hash,
            schema_version=envelope.schema_version,
            ingestion_run_id=ingestion_run_id,
            storage_uri=uri,
            processing_status="CAPTURED",
        )
        self.repository.raw_objects[raw.id] = raw
        return uri

    def _capture_normalized_and_curated(
        self, provider_id: str, endpoint: str, payload_hash: str, payload: Any
    ) -> tuple[str, str]:
        object_name = f"{provider_id}/{endpoint}/{payload_hash}.json"
        normalized_uri = self.object_store.put_layer_once("normalized", object_name, payload)
        curated_uri = self.object_store.put_layer_once("curated", object_name, payload)
        self.repository.layer_objects["normalized"].append(
            {
                "provider_id": provider_id,
                "endpoint": endpoint,
                "content_hash": payload_hash,
                "storage_uri": normalized_uri,
            }
        )
        self.repository.layer_objects["curated"].append(
            {
                "provider_id": provider_id,
                "endpoint": endpoint,
                "content_hash": payload_hash,
                "storage_uri": curated_uri,
            }
        )
        return normalized_uri, curated_uri

    def _start_layer_run(
        self,
        provider_id: str,
        dataset_name: str,
        envelope: ProviderResponseEnvelope,
        payload_hash: str,
        correlation_id: str,
    ) -> ProviderIngestionRun:
        run = ProviderIngestionRun(
            provider_id=provider_id,
            dataset_name=dataset_name,
            source_reference=envelope.source_reference,
            status=IngestionStatus.RUNNING,
            correlation_id=correlation_id,
            raw_object_hash=payload_hash,
            records_received=len(envelope.payload),
        )
        self.repository.ingestion_runs[run.id] = run
        return run

    def _complete_layer_run(
        self,
        run: ProviderIngestionRun,
        envelope: ProviderResponseEnvelope,
        payload_hash: str,
        *,
        records_accepted: int,
        records_rejected: int,
        validation_summary: dict[str, Any],
        error_summary: list[str] | None = None,
    ) -> ProviderIngestionRun:
        completed = ProviderIngestionRun(
            provider_id=run.provider_id,
            dataset_name=run.dataset_name,
            source_reference=envelope.source_reference,
            status=IngestionStatus.COMPLETED
            if records_rejected == 0
            else IngestionStatus.COMPLETED_WITH_WARNINGS,
            correlation_id=run.correlation_id,
            raw_object_hash=payload_hash,
            records_received=len(envelope.payload),
            records_accepted=records_accepted,
            records_rejected=records_rejected,
            validation_summary=validation_summary,
            error_summary=error_summary or [],
            id=run.id,
            started_at=run.started_at,
        )
        self.repository.ingestion_runs[completed.id] = completed
        return completed

    def _audit_layer_event(
        self, event_type: str, run: ProviderIngestionRun, action: str, metadata: dict[str, Any]
    ) -> None:
        self.audit_log.record(
            event_type=event_type,
            entity_type="ProviderIngestionRun",
            entity_id=run.id,
            actor_type="SYSTEM_SERVICE",
            actor_id="ingestion-service",
            action=action,
            before_state=None,
            after_state=asdict(run),
            metadata=metadata,
            correlation_id=run.correlation_id,
        )

    def _normalize_instrument(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "aegis_instrument_id": str(record["aegis_instrument_id"]),
            "isin": str(record["isin"]),
            "company_legal_name": str(record["company_legal_name"]),
            "security_type": str(record.get("security_type", "EQUITY")),
            "current_symbol": str(record["current_symbol"]),
            "primary_exchange": str(record.get("primary_exchange", "NSE")),
            "listing_date": date.fromisoformat(str(record["listing_date"])),
            "trading_status": str(record.get("trading_status", "ACTIVE")),
            "sector": str(record.get("sector", "UNKNOWN")),
            "industry": str(record.get("industry", "UNKNOWN")),
            "currency": str(record.get("currency", "INR")),
            "lot_size": int(record.get("lot_size", 1)),
            "tick_size": float(record.get("tick_size", 0.05)),
            "liquidity_classification": str(record.get("liquidity_classification", "UNKNOWN")),
            "mapping_confidence_score": float(record.get("mapping_confidence_score", 0.0)),
        }
