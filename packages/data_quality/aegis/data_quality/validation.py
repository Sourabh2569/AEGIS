from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from aegis.domain.models import DataQualityResult, QualityCategory, Severity, ValidationStatus


def validate_eod_ohlcv(
    records: list[dict[str, Any]],
    known_instrument_ids: set[str],
    dataset_version_id: str,
    seen_keys: set[tuple[str, str]] | None = None,
    approved_calendar_dates: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[DataQualityResult]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    results: list[DataQualityResult] = []
    seen = seen_keys or set()

    for record in records:
        reasons: list[str] = []
        try:
            open_ = float(record["open"])
            high = float(record["high"])
            low = float(record["low"])
            close = float(record["close"])
            volume = int(float(record["volume"]))
            trade_date = date.fromisoformat(str(record["trade_date"]))
        except (KeyError, TypeError, ValueError) as exc:
            reasons.append(f"SCHEMA: {exc}")
            open_ = high = low = close = 0.0
            volume = -1
            trade_date = None

        instrument_id = str(record.get("aegis_instrument_id", ""))
        if instrument_id not in known_instrument_ids:
            reasons.append("INSTRUMENT_MAPPING: unknown aegis_instrument_id")
        if high < open_ or high < close or high < low:
            reasons.append("BUSINESS_RULE: high must be >= open, close, and low")
        if low > open_ or low > close:
            reasons.append("BUSINESS_RULE: low must be <= open and close")
        if volume < 0:
            reasons.append("BUSINESS_RULE: volume must be >= 0")
        if min(open_, high, low, close) <= 0:
            reasons.append("BUSINESS_RULE: OHLC prices must be positive")
        if trade_date is None:
            reasons.append("TEMPORAL: trade_date must be an ISO date")
        elif (
            approved_calendar_dates is not None
            and trade_date.isoformat() not in approved_calendar_dates
        ):
            reasons.append("MARKET_CALENDAR: trade_date is not in approved market calendar")
        key = (instrument_id, str(record.get("trade_date", "")))
        if key in seen:
            reasons.append("DUPLICATE: duplicate instrument/date bar")
        else:
            seen.add(key)
        for required_ts in ("event_time", "available_time", "ingested_time"):
            if not record.get(required_ts):
                reasons.append(f"TEMPORAL: missing {required_ts}")

        if reasons:
            rejected.append({"record": record, "reasons": reasons})
        else:
            accepted.append(record)

    if rejected:
        results.append(
            DataQualityResult(
                dataset_version_id=dataset_version_id,
                check_name="eod_ohlcv_required_rules",
                check_category=QualityCategory.BUSINESS_RULE,
                severity=Severity.CRITICAL,
                passed=False,
                message="One or more EOD records failed validation.",
                affected_record_count=len(rejected),
            )
        )
    else:
        results.append(
            DataQualityResult(
                dataset_version_id=dataset_version_id,
                check_name="eod_ohlcv_required_rules",
                check_category=QualityCategory.BUSINESS_RULE,
                severity=Severity.INFO,
                passed=True,
                message="All EOD records passed required Sprint 0 checks.",
                affected_record_count=0,
            )
        )
    return accepted, rejected, results


def validate_live_quotes(
    records: list[dict[str, Any]],
    known_instrument_ids: set[str],
    dataset_version_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[DataQualityResult]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for record in records:
        reasons: list[str] = []
        instrument_id = str(record.get("aegis_instrument_id", ""))
        if instrument_id not in known_instrument_ids:
            reasons.append("INSTRUMENT_MAPPING: unknown aegis_instrument_id")
        try:
            last_price = float(record["last_price"])
            bid_price = float(record["bid_price"])
            ask_price = float(record["ask_price"])
            volume = int(float(record["volume"]))
        except (KeyError, TypeError, ValueError) as exc:
            reasons.append(f"SCHEMA: {exc}")
            last_price = bid_price = ask_price = 0.0
            volume = -1
        if min(last_price, bid_price, ask_price) <= 0:
            reasons.append("BUSINESS_RULE: quote prices must be positive")
        if bid_price > ask_price:
            reasons.append("BUSINESS_RULE: bid_price must be <= ask_price")
        if volume < 0:
            reasons.append("BUSINESS_RULE: volume must be >= 0")
        for required_ts in ("event_time", "available_time", "ingested_time"):
            if not record.get(required_ts):
                reasons.append(f"TEMPORAL: missing {required_ts}")

        if reasons:
            rejected.append({"record": record, "reasons": reasons})
        else:
            accepted.append(record)

    results = [
        DataQualityResult(
            dataset_version_id=dataset_version_id,
            check_name="live_quote_required_rules",
            check_category=QualityCategory.BUSINESS_RULE,
            severity=Severity.CRITICAL if rejected else Severity.INFO,
            passed=not rejected,
            message="Live quote records passed required read-only checks."
            if not rejected
            else "One or more live quote records failed validation.",
            affected_record_count=len(rejected),
        )
    ]
    return accepted, rejected, results


def freshness_snapshot(
    *,
    records: list[dict[str, Any]],
    dataset_name: str,
    max_age_seconds: int,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    checked_at = checked_at or datetime.now(timezone.utc)
    latest_available: datetime | None = None
    for record in records:
        raw = record.get("available_time")
        if not raw:
            continue
        candidate = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if candidate.tzinfo is None:
            candidate = candidate.replace(tzinfo=timezone.utc)
        latest_available = (
            candidate if latest_available is None else max(latest_available, candidate)
        )

    age_seconds = (
        None
        if latest_available is None
        else max(0.0, (checked_at - latest_available.astimezone(timezone.utc)).total_seconds())
    )
    status = (
        "UNKNOWN"
        if age_seconds is None
        else ("FRESH" if age_seconds <= max_age_seconds else "STALE")
    )
    return {
        "dataset_name": dataset_name,
        "status": status,
        "latest_available_time": latest_available.isoformat() if latest_available else None,
        "checked_at": checked_at.isoformat(),
        "age_seconds": age_seconds,
        "max_age_seconds": max_age_seconds,
    }


def derive_validation_status(
    results: list[DataQualityResult], critical_dataset: bool
) -> ValidationStatus:
    if any((not result.passed and result.severity == Severity.CRITICAL) for result in results):
        return ValidationStatus.RED
    if any((not result.passed and result.severity == Severity.ERROR) for result in results):
        return ValidationStatus.RED if critical_dataset else ValidationStatus.AMBER
    if any((not result.passed and result.severity == Severity.WARNING) for result in results):
        return ValidationStatus.GREEN_CAUTION
    return ValidationStatus.GREEN


def quality_score(results: list[DataQualityResult]) -> float:
    if not results:
        return 100.0
    penalties = {
        Severity.INFO: 0.0,
        Severity.WARNING: 5.0,
        Severity.ERROR: 25.0,
        Severity.CRITICAL: 100.0,
    }
    score = 100.0
    for result in results:
        if not result.passed:
            score -= penalties[result.severity]
    return max(score, 0.0)
