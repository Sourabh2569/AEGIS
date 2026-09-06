from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from itertools import pairwise
from statistics import pstdev
from typing import Any

from aegis.shared.ids import new_id
from aegis.shared.money import decimal, money
from aegis.shared.time import require_aware_utc, utc_now


class StrEnum(str, Enum):
    pass


class AvailabilityPolicy(StrEnum):
    POST_CLOSE_NEXT_SESSION_ELIGIBLE = "POST_CLOSE_NEXT_SESSION_ELIGIBLE"
    POINT_IN_TIME_FILING_AVAILABLE = "POINT_IN_TIME_FILING_AVAILABLE"
    POINT_IN_TIME_EVENT_AVAILABLE = "POINT_IN_TIME_EVENT_AVAILABLE"


class FeatureStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"


@dataclass(frozen=True)
class FeatureDefinition:
    feature_key: str
    name: str
    description: str
    formula_description: str
    input_requirements_json: dict[str, Any]
    lookback_days: int
    output_type: str
    null_handling_policy: str
    outlier_handling_policy: str
    availability_policy: AvailabilityPolicy
    version: str = "V0"
    status: FeatureStatus = FeatureStatus.ACTIVE
    id: str = field(default_factory=lambda: new_id("feature"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class FeatureValue:
    instrument_id: str
    feature_definition_id: str
    feature_version: str
    feature_date: date
    feature_value: Decimal | None
    event_time: datetime
    available_time: datetime
    dataset_version_id: str
    corporate_action_version: str
    calculation_run_id: str
    validation_status: str
    id: str = field(default_factory=lambda: new_id("feature-value"))
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time", require_aware_utc(self.event_time))
        object.__setattr__(self, "available_time", require_aware_utc(self.available_time))
        if self.feature_value is not None:
            object.__setattr__(self, "feature_value", money(self.feature_value))


def daily_return(previous_close: Decimal, close: Decimal) -> Decimal | None:
    if previous_close <= 0:
        return None
    return money((close - previous_close) / previous_close)


def rolling_return(closes: list[Decimal]) -> Decimal | None:
    if len(closes) < 2 or closes[0] <= 0:
        return None
    return money((closes[-1] - closes[0]) / closes[0])


def sma(values: list[Decimal], lookback: int) -> Decimal | None:
    if len(values) < lookback:
        return None
    return money(sum(values[-lookback:]) / Decimal(lookback))


def ema(values: list[Decimal], lookback: int) -> Decimal | None:
    if len(values) < lookback:
        return None
    alpha = Decimal(2) / Decimal(lookback + 1)
    current = values[0]
    for value in values[1:]:
        current = (value * alpha) + (current * (Decimal(1) - alpha))
    return money(current)


def rsi(closes: list[Decimal], lookback: int = 14) -> Decimal | None:
    if len(closes) <= lookback:
        return None
    gains: list[Decimal] = []
    losses: list[Decimal] = []
    window = closes[-(lookback + 1) :]
    for previous, current in pairwise(window):
        change = current - previous
        gains.append(max(change, Decimal(0)))
        losses.append(abs(min(change, Decimal(0))))
    avg_gain = sum(gains) / Decimal(lookback)
    avg_loss = sum(losses) / Decimal(lookback)
    if avg_loss == 0:
        return money(100)
    rs = avg_gain / avg_loss
    return money(Decimal(100) - (Decimal(100) / (Decimal(1) + rs)))


def atr(
    highs: list[Decimal], lows: list[Decimal], closes: list[Decimal], lookback: int = 14
) -> Decimal | None:
    if len(highs) <= lookback or len(lows) <= lookback or len(closes) <= lookback:
        return None
    true_ranges: list[Decimal] = []
    for index in range(len(closes) - lookback, len(closes)):
        high = highs[index]
        low = lows[index]
        previous_close = closes[index - 1]
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return money(sum(true_ranges) / Decimal(lookback))


def rolling_volatility(returns: list[Decimal], lookback: int = 20) -> Decimal | None:
    if len(returns) < lookback:
        return None
    return money(Decimal(str(pstdev([float(value) for value in returns[-lookback:]]))))


def price_to_ma_distance(close: Decimal, moving_average: Decimal | None) -> Decimal | None:
    if moving_average is None or moving_average <= 0:
        return None
    return money((close - moving_average) / moving_average)


def compute_feature_set(
    *,
    instrument_id: str,
    bars: list[dict[str, Any]],
    dataset_version_id: str,
    corporate_action_version: str,
    calculation_run_id: str | None = None,
) -> list[FeatureValue]:
    calculation_run_id = calculation_run_id or new_id("feature-run")
    values: list[FeatureValue] = []
    closes: list[Decimal] = []
    highs: list[Decimal] = []
    lows: list[Decimal] = []
    volumes: list[Decimal] = []
    returns: list[Decimal] = []
    definitions = default_feature_definitions()
    by_key = {definition.feature_key: definition for definition in definitions}
    for bar in sorted(bars, key=lambda item: item["trade_date"]):
        close = decimal(bar["close"])
        high = decimal(bar["high"])
        low = decimal(bar["low"])
        volume = decimal(bar["volume"])
        closes.append(close)
        highs.append(high)
        lows.append(low)
        volumes.append(volume)
        if len(closes) > 1:
            computed_return = daily_return(closes[-2], close)
            if computed_return is not None:
                returns.append(computed_return)
        feature_date = bar["trade_date"]
        event_time = bar["event_time"]
        available_time = bar["available_time"]
        computed = {
            "DAILY_RETURN": returns[-1] if returns else None,
            "ROLLING_RETURN_20": rolling_return(closes[-20:]),
            "SMA_20": sma(closes, 20),
            "SMA_50": sma(closes, 50),
            "SMA_200": sma(closes, 200),
            "EMA_20": ema(closes, 20),
            "EMA_50": ema(closes, 50),
            "RSI_14": rsi(closes, 14),
            "ATR_14": atr(highs, lows, closes, 14),
            "ROLLING_VOLATILITY_20": rolling_volatility(returns, 20),
            "ROLLING_AVERAGE_DAILY_VOLUME_20": sma(volumes, 20),
            "ROLLING_AVERAGE_DAILY_VALUE_TRADED_20": sma(
                [c * v for c, v in zip(closes, volumes)], 20
            ),
            "MOMENTUM_20": rolling_return(closes[-21:]),
            "MOMENTUM_60": rolling_return(closes[-61:]),
            "PRICE_TO_SMA_50_DISTANCE": price_to_ma_distance(close, sma(closes, 50)),
            "PRICE_TO_SMA_200_DISTANCE": price_to_ma_distance(close, sma(closes, 200)),
        }
        for key, value in computed.items():
            definition = by_key[key]
            values.append(
                FeatureValue(
                    instrument_id=instrument_id,
                    feature_definition_id=definition.id,
                    feature_version=definition.version,
                    feature_date=feature_date,
                    feature_value=value,
                    event_time=event_time,
                    available_time=available_time,
                    dataset_version_id=dataset_version_id,
                    corporate_action_version=corporate_action_version,
                    calculation_run_id=calculation_run_id,
                    validation_status="GREEN" if value is not None else "INSUFFICIENT_HISTORY",
                )
            )
    return values


def default_feature_definitions() -> list[FeatureDefinition]:
    def definition(key: str, lookback: int, formula: str) -> FeatureDefinition:
        return FeatureDefinition(
            feature_key=key,
            name=key.replace("_", " ").title(),
            description=f"{key} deterministic Sprint 2 feature.",
            formula_description=formula,
            input_requirements_json={"requires": ["open", "high", "low", "close", "volume"]},
            lookback_days=lookback,
            output_type="DECIMAL",
            null_handling_policy="INSUFFICIENT_HISTORY",
            outlier_handling_policy="NO_SILENT_CORRECTION",
            availability_policy=AvailabilityPolicy.POST_CLOSE_NEXT_SESSION_ELIGIBLE,
        )

    return [
        definition("DAILY_RETURN", 1, "(close_t / close_t-1) - 1"),
        definition("ROLLING_RETURN_20", 20, "(close_t / close_t-20) - 1"),
        definition("SMA_20", 20, "mean(close, 20)"),
        definition("SMA_50", 50, "mean(close, 50)"),
        definition("SMA_200", 200, "mean(close, 200)"),
        definition("EMA_20", 20, "exponential moving average close, 20"),
        definition("EMA_50", 50, "exponential moving average close, 50"),
        definition("RSI_14", 14, "relative strength index, 14"),
        definition("ATR_14", 14, "average true range, 14"),
        definition(
            "ROLLING_VOLATILITY_20", 20, "population standard deviation of daily returns, 20"
        ),
        definition("ROLLING_AVERAGE_DAILY_VOLUME_20", 20, "mean(volume, 20)"),
        definition("ROLLING_AVERAGE_DAILY_VALUE_TRADED_20", 20, "mean(close * volume, 20)"),
        definition("MOMENTUM_20", 20, "20-day rolling return"),
        definition("MOMENTUM_60", 60, "60-day rolling return"),
        definition("PRICE_TO_SMA_50_DISTANCE", 50, "(close - SMA_50) / SMA_50"),
        definition("PRICE_TO_SMA_200_DISTANCE", 200, "(close - SMA_200) / SMA_200"),
    ]
