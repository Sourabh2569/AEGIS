from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class Candidate:
    instrument_id: str
    sector: str
    cluster: str
    close: Decimal
    momentum_60: Decimal | None
    price_to_sma_200: Decimal | None
    sma_50: Decimal | None
    sma_200: Decimal | None
    atr_14: Decimal | None
    average_daily_value_traded_20: Decimal | None


class StrategyContract:
    strategy_name = "StrategyContract"
    strategy_version = "V0"

    def validate_inputs(self, candidates: list[Candidate]) -> None:
        if not candidates:
            raise ValueError("Strategy requires at least one candidate.")

    def rank_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        raise NotImplementedError

    def propose_target_weights(self, ranked: list[Candidate], maximum_position_count: int) -> dict[str, Decimal]:
        raise NotImplementedError

    def get_strategy_metadata(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "classification": "RESEARCH_ONLY",
            "not_recommendation": True,
        }


class BuyAndHoldBenchmarkStrategyV0(StrategyContract):
    strategy_name = "BuyAndHoldBenchmarkStrategyV0"

    def rank_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        self.validate_inputs(candidates)
        return sorted(candidates, key=lambda item: item.instrument_id)[:1]

    def propose_target_weights(self, ranked: list[Candidate], maximum_position_count: int) -> dict[str, Decimal]:
        return {ranked[0].instrument_id: Decimal("0.80")}


class EqualWeightUniverseBenchmarkStrategyV0(StrategyContract):
    strategy_name = "EqualWeightUniverseBenchmarkStrategyV0"

    def rank_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        self.validate_inputs(candidates)
        return sorted(candidates, key=lambda item: item.instrument_id)

    def propose_target_weights(self, ranked: list[Candidate], maximum_position_count: int) -> dict[str, Decimal]:
        selected = ranked[:maximum_position_count]
        if not selected:
            return {}
        weight = Decimal("0.80") / Decimal(len(selected))
        return {candidate.instrument_id: weight for candidate in selected}


class TrendFollowingBaselineStrategyV0(StrategyContract):
    strategy_name = "TrendFollowingBaselineStrategyV0"

    def rank_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        eligible = [
            candidate
            for candidate in candidates
            if candidate.sma_50 is not None
            and candidate.sma_200 is not None
            and candidate.momentum_60 is not None
            and candidate.price_to_sma_200 is not None
            and candidate.average_daily_value_traded_20 is not None
            and candidate.close > candidate.sma_50
            and candidate.sma_50 > candidate.sma_200
            and candidate.momentum_60 > 0
            and candidate.average_daily_value_traded_20 > Decimal("100000")
        ]
        return sorted(
            eligible,
            key=lambda item: (-(item.momentum_60 or Decimal("0")), -(item.price_to_sma_200 or Decimal("0")), item.instrument_id),
        )

    def propose_target_weights(self, ranked: list[Candidate], maximum_position_count: int) -> dict[str, Decimal]:
        selected = ranked[:maximum_position_count]
        if not selected:
            return {}
        weight = Decimal("0.80") / Decimal(len(selected))
        return {candidate.instrument_id: weight for candidate in selected}

    def invalidation_price(self, candidate: Candidate) -> Decimal:
        if candidate.atr_14 is None:
            raise ValueError("TrendFollowingBaselineStrategyV0 requires ATR_14.")
        return candidate.close - (Decimal("2") * candidate.atr_14)
