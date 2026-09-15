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
    # Everything below is optional and additive for QualityMomentumStrategyV1
    # -- TrendFollowingBaselineStrategyV0 and the benchmark strategies never
    # read these fields, so their behavior is untouched by this extension.
    momentum_20: Decimal | None = None
    momentum_120: Decimal | None = None
    sma_100: Decimal | None = None
    realized_volatility_60: Decimal | None = None
    high_252: Decimal | None = None
    average_daily_value_traded_60: Decimal | None = None
    # Fundamentals are merged in only when a real filing has actually been
    # ingested for this instrument (see _build_candidate) -- never fabricated
    # or defaulted to a "neutral" value. fundamentals_available is the
    # explicit signal a strategy must check before trusting the fields below.
    fundamentals_available: bool = False
    profit_for_period: Decimal | None = None
    debt_equity_ratio: Decimal | None = None
    ttm_eps: Decimal | None = None
    # The next-most-recent real quarter's profit, when a second real
    # point-in-time-visible quarter exists -- lets a strategy judge a real
    # trend (is profit improving or deteriorating), not just a single
    # snapshot. None whenever fewer than two real quarters are visible yet.
    profit_for_period_prior_quarter: Decimal | None = None


class StrategyContract:
    strategy_name = "StrategyContract"
    strategy_version = "V0"

    def validate_inputs(self, candidates: list[Candidate]) -> None:
        if not candidates:
            raise ValueError("Strategy requires at least one candidate.")

    def rank_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        raise NotImplementedError

    def propose_target_weights(
        self, ranked: list[Candidate], maximum_position_count: int
    ) -> dict[str, Decimal]:
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

    def propose_target_weights(
        self, ranked: list[Candidate], maximum_position_count: int
    ) -> dict[str, Decimal]:
        return {ranked[0].instrument_id: Decimal("0.80")}


class EqualWeightUniverseBenchmarkStrategyV0(StrategyContract):
    """A "diversified neutral market-participation baseline" (its documented
    role in packages/research_activation/aegis/research_activation/evidence_review.py)
    -- the point is to represent "what if I just owned the whole real
    eligible universe equally, with no selection skill at all," as a
    reference point for strategies that DO make selection bets.

    propose_target_weights deliberately does NOT cap at
    maximum_position_count the way every real, risk-managed strategy in this
    file does. That cap is a real concentration-risk control appropriate for
    a strategy actually deploying capital under AEGIS's risk profile; this
    benchmark's whole purpose is to be the un-concentrated baseline those
    strategies are judged against. Capping it would silently turn "equal
    weight the universe" into "equal weight whichever handful of
    instruments happen to sort first by internal id" -- a real bug this
    fix corrects: with rank_candidates sorting by a stable, never-changing
    instrument_id and no other criterion, a capped version always selected
    the exact same fixed subset every single rebalance for the strategy's
    entire lifetime, never actually representing the universe at all.
    """

    strategy_name = "EqualWeightUniverseBenchmarkStrategyV0"

    def rank_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        self.validate_inputs(candidates)
        return sorted(candidates, key=lambda item: item.instrument_id)

    def propose_target_weights(
        self, ranked: list[Candidate], maximum_position_count: int
    ) -> dict[str, Decimal]:
        if not ranked:
            return {}
        weight = Decimal("0.80") / Decimal(len(ranked))
        return {candidate.instrument_id: weight for candidate in ranked}


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
            and candidate.average_daily_value_traded_20 > Decimal(100000)
        ]
        return sorted(
            eligible,
            key=lambda item: (
                -(item.momentum_60 or Decimal(0)),
                -(item.price_to_sma_200 or Decimal(0)),
                item.instrument_id,
            ),
        )

    def propose_target_weights(
        self, ranked: list[Candidate], maximum_position_count: int
    ) -> dict[str, Decimal]:
        selected = ranked[:maximum_position_count]
        if not selected:
            return {}
        weight = Decimal("0.80") / Decimal(len(selected))
        return {candidate.instrument_id: weight for candidate in selected}

    def invalidation_price(self, candidate: Candidate) -> Decimal:
        if candidate.atr_14 is None:
            raise ValueError("TrendFollowingBaselineStrategyV0 requires ATR_14.")
        return candidate.close - (Decimal(2) * candidate.atr_14)


# A bank/NBFC's debt-equity ratio isn't comparable to a non-financial
# company's -- leverage is structurally part of a financial institution's
# business model, not a risk red flag the same way it is for an industrial
# or consumer company. QualityMomentumStrategyV1's leverage disqualifier is
# skipped entirely for this sector rather than applying a threshold that
# would misclassify every bank as "excessively leveraged." Matches the real
# sector label used throughout CURATED_INSTRUMENT_METADATA.
FINANCIAL_SECTOR_LABEL = "Financial Services"

# Conservative, explicit thresholds -- tunable, but real numbers, not
# placeholders. See docs/strategy design notes for the reasoning behind each.
MAXIMUM_NON_FINANCIAL_DEBT_EQUITY_RATIO = Decimal("2.0")
MINIMUM_LIQUIDITY_TREND_RATIO = Decimal("0.7")
MAXIMUM_DRAWDOWN_FROM_52_WEEK_HIGH = Decimal("0.15")
MAXIMUM_EXTENSION_ABOVE_SMA_50 = Decimal("0.25")
VALUE_TIEBREAK_WEIGHT = Decimal("0.1")


class QualityMomentumStrategyV1(StrategyContract):
    """A stricter, multi-factor evolution of TrendFollowingBaselineStrategyV0:
    momentum confirmed across three horizons (not one arbitrary lookback),
    ranked by volatility-adjusted score rather than raw momentum, with a
    tighter trend filter, a falling-knife guard, an overextension guard, a
    liquidity-trend check, and -- only when a real filing has actually been
    ingested for that instrument -- hard disqualifiers for a reported net
    loss or excessive non-financial leverage, plus a modest earnings-yield
    tiebreak. Every fundamentals-based check is skipped, never faked, when
    fundamentals_available is False; as of this strategy's introduction, real
    fundamentals coverage across the tradeable universe is thin (a handful of
    symbols), so most candidates are judged on the technical criteria alone,
    exactly as TrendFollowingBaselineStrategyV0 already does -- the
    fundamentals layer is real and correct, and grows in effect only as more
    real filings are ingested, never approximated to compensate for missing
    data.

    Capital allocation (propose_target_weights) and the stop-loss reference
    (invalidation_price) are deliberately identical to
    TrendFollowingBaselineStrategyV0's -- this strategy isolates its change
    to selection criteria alone, so a real backtest comparison against V0
    measures the effect of the added filters, not a confounded change in
    position sizing or risk policy.
    """

    strategy_name = "QualityMomentumStrategyV1"
    strategy_version = "V1"

    def rank_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        eligible = [
            candidate for candidate in candidates if self._is_eligible(candidate)
        ]
        scored = [(self._final_score(candidate), candidate) for candidate in eligible]
        scored.sort(key=lambda pair: (-pair[0], pair[1].instrument_id))
        return [candidate for _, candidate in scored]

    def _is_eligible(self, candidate: Candidate) -> bool:
        required_technical = (
            candidate.sma_50,
            candidate.sma_100,
            candidate.sma_200,
            candidate.momentum_20,
            candidate.momentum_60,
            candidate.momentum_120,
            candidate.atr_14,
            candidate.realized_volatility_60,
            candidate.high_252,
            candidate.average_daily_value_traded_20,
            candidate.average_daily_value_traded_60,
        )
        if any(value is None for value in required_technical):
            return False
        assert candidate.sma_50 is not None
        assert candidate.sma_100 is not None
        assert candidate.sma_200 is not None
        assert candidate.momentum_20 is not None
        assert candidate.momentum_60 is not None
        assert candidate.momentum_120 is not None
        assert candidate.high_252 is not None
        assert candidate.average_daily_value_traded_60 is not None

        if not (candidate.momentum_20 > 0 and candidate.momentum_60 > 0 and candidate.momentum_120 > 0):
            return False
        if not (candidate.close > candidate.sma_50 > candidate.sma_100 > candidate.sma_200):
            return False
        if candidate.average_daily_value_traded_20 <= Decimal(100000):
            return False
        if candidate.average_daily_value_traded_20 < (
            MINIMUM_LIQUIDITY_TREND_RATIO * candidate.average_daily_value_traded_60
        ):
            return False
        if candidate.close < ((Decimal(1) - MAXIMUM_DRAWDOWN_FROM_52_WEEK_HIGH) * candidate.high_252):
            return False
        if candidate.close > ((Decimal(1) + MAXIMUM_EXTENSION_ABOVE_SMA_50) * candidate.sma_50):
            return False

        if candidate.fundamentals_available:
            if candidate.profit_for_period is not None and candidate.profit_for_period < 0:
                return False
            if (
                candidate.sector != FINANCIAL_SECTOR_LABEL
                and candidate.debt_equity_ratio is not None
                and candidate.debt_equity_ratio > MAXIMUM_NON_FINANCIAL_DEBT_EQUITY_RATIO
            ):
                return False

        return True

    def _final_score(self, candidate: Candidate) -> Decimal:
        assert candidate.momentum_20 is not None
        assert candidate.momentum_60 is not None
        assert candidate.momentum_120 is not None
        assert candidate.realized_volatility_60 is not None
        blended_momentum = (
            (Decimal("0.25") * candidate.momentum_20)
            + (Decimal("0.5") * candidate.momentum_60)
            + (Decimal("0.25") * candidate.momentum_120)
        )
        volatility_floor = Decimal("0.0001")
        risk_adjusted_score = blended_momentum / max(candidate.realized_volatility_60, volatility_floor)
        if (
            candidate.fundamentals_available
            and candidate.ttm_eps is not None
            and candidate.ttm_eps > 0
            and candidate.close > 0
        ):
            earnings_yield = candidate.ttm_eps / candidate.close
            return risk_adjusted_score * (Decimal(1) + (VALUE_TIEBREAK_WEIGHT * earnings_yield))
        return risk_adjusted_score

    def propose_target_weights(
        self, ranked: list[Candidate], maximum_position_count: int
    ) -> dict[str, Decimal]:
        selected = ranked[:maximum_position_count]
        if not selected:
            return {}
        weight = Decimal("0.80") / Decimal(len(selected))
        return {candidate.instrument_id: weight for candidate in selected}

    def invalidation_price(self, candidate: Candidate) -> Decimal:
        if candidate.atr_14 is None:
            raise ValueError("QualityMomentumStrategyV1 requires ATR_14.")
        return candidate.close - (Decimal(2) * candidate.atr_14)


TREND_STRENGTH_WEIGHT = Decimal("0.5")


class QualityMomentumStrategyV2(StrategyContract):
    """QualityMomentumStrategyV1's real backtest result was worse than
    TrendFollowingBaselineStrategyV0's on both return and drawdown -- the
    diagnosis was architectural, not a bad threshold: V1 chains seven hard
    AND'd conditions (three-SMA trend, three-horizon momentum agreement,
    liquidity trend, falling-knife, overextension, plus fundamentals), so a
    real winner only has to fail ONE of seven simultaneous checks on a given
    rebalance day to be excluded -- most likely cutting off exactly the
    strongest trends, since a stock deep in a real uptrend is often *more*
    than 25% above its 50-day average, not less.

    V2's eligibility gate is deliberately identical to
    TrendFollowingBaselineStrategyV0's proven one (same trend filter, same
    momentum_60 > 0 requirement, same liquidity floor) plus the fundamentals
    disqualifiers already validated in V1 (a real net loss, or excessive
    non-financial leverage, when a filing has actually been ingested) --
    nothing new is added as a hard requirement. Every other signal V1 used
    as a filter (multi-horizon momentum, distance from the real 252-day
    high, trend strength above SMA_200) becomes a *scored*, multiplicative
    factor instead: a candidate that's slightly extended or has one weak
    momentum horizon loses some rank, never its eligibility outright. This
    isolates a clean, honest question a real backtest can actually answer:
    does a richer RANKING of the same proven-eligible universe improve
    risk-adjusted returns, independent of whether the eligibility gate
    itself is right.
    """

    strategy_name = "QualityMomentumStrategyV2"
    strategy_version = "V2"

    def rank_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        eligible = [candidate for candidate in candidates if self._is_eligible(candidate)]
        scored = [(self._final_score(candidate), candidate) for candidate in eligible]
        scored.sort(key=lambda pair: (-pair[0], pair[1].instrument_id))
        return [candidate for _, candidate in scored]

    def _is_eligible(self, candidate: Candidate) -> bool:
        if (
            candidate.sma_50 is None
            or candidate.sma_200 is None
            or candidate.momentum_60 is None
            or candidate.atr_14 is None
            or candidate.average_daily_value_traded_20 is None
        ):
            return False
        if not (candidate.close > candidate.sma_50 > candidate.sma_200):
            return False
        if candidate.momentum_60 <= 0:
            return False
        if candidate.average_daily_value_traded_20 <= Decimal(100000):
            return False

        if candidate.fundamentals_available:
            if candidate.profit_for_period is not None and candidate.profit_for_period < 0:
                return False
            if (
                candidate.sector != FINANCIAL_SECTOR_LABEL
                and candidate.debt_equity_ratio is not None
                and candidate.debt_equity_ratio > MAXIMUM_NON_FINANCIAL_DEBT_EQUITY_RATIO
            ):
                return False

        return True

    def _blended_momentum(self, candidate: Candidate) -> Decimal:
        """A weighted average over whichever of the three momentum horizons
        are actually real -- momentum_60 is guaranteed present by
        eligibility, so this always has at least one term. Unlike V1's hard
        AND across all three, a candidate with a real 60-day uptrend but a
        temporarily soft 20-day reading is scored down, not excluded."""
        weighted = (
            (Decimal("0.25"), candidate.momentum_20),
            (Decimal("0.5"), candidate.momentum_60),
            (Decimal("0.25"), candidate.momentum_120),
        )
        present = [(weight, value) for weight, value in weighted if value is not None]
        total_weight = sum(weight for weight, _ in present)
        return sum((weight * value for weight, value in present), start=Decimal(0)) / total_weight

    def _final_score(self, candidate: Candidate) -> Decimal:
        blended_momentum = self._blended_momentum(candidate)
        if candidate.realized_volatility_60 is not None:
            volatility_floor = Decimal("0.0001")
            score = blended_momentum / max(candidate.realized_volatility_60, volatility_floor)
        else:
            score = blended_momentum

        # Trend strength is a real signal, not a hard band -- a stock further
        # above its SMA_200 gets a proportionally larger (unbounded) boost
        # rather than being capped or excluded above some arbitrary line.
        if candidate.price_to_sma_200 is not None:
            score = score * (Decimal(1) + (TREND_STRENGTH_WEIGHT * candidate.price_to_sma_200))

        # Proximity to the real trailing 252-day high, as a smooth 0-1
        # multiplier (close is always <= high_252 by construction) -- a
        # candidate right at a new high scores highest; one still recovering
        # from a real drawdown is discounted, not excluded outright. Skipped
        # entirely (neutral) until 252+ real days of history exist.
        if candidate.high_252 is not None and candidate.high_252 > 0:
            score = score * (candidate.close / candidate.high_252)

        if (
            candidate.fundamentals_available
            and candidate.ttm_eps is not None
            and candidate.ttm_eps > 0
            and candidate.close > 0
        ):
            earnings_yield = candidate.ttm_eps / candidate.close
            score = score * (Decimal(1) + (VALUE_TIEBREAK_WEIGHT * earnings_yield))

        return score

    def propose_target_weights(
        self, ranked: list[Candidate], maximum_position_count: int
    ) -> dict[str, Decimal]:
        selected = ranked[:maximum_position_count]
        if not selected:
            return {}
        weight = Decimal("0.80") / Decimal(len(selected))
        return {candidate.instrument_id: weight for candidate in selected}

    def invalidation_price(self, candidate: Candidate) -> Decimal:
        if candidate.atr_14 is None:
            raise ValueError("QualityMomentumStrategyV2 requires ATR_14.")
        return candidate.close - (Decimal(2) * candidate.atr_14)


class QualityMomentumStrategyV3(StrategyContract):
    """V2 bundled three ranking changes on top of TrendFollowingBaselineStrategyV0's
    proven gate (volatility-adjustment, trend-strength weighting, proximity
    to the real trailing 252-day high) and underperformed V0 overall. A
    real, isolated diagnostic -- each of the three tested alone, on the same
    real 10-year Nifty 50 history -- found that volatility-adjustment and
    trend-strength weighting BOTH independently hurt (17.7% and 19.7% total
    return respectively, vs. V0's own 32.8%), while proximity-to-high used
    ALONE beat V0 outright (36.5% return, a better return/drawdown ratio:
    3.16 vs 2.93). V2's mediocre combined result was the one real
    improvement being dragged down by two real drags, not three neutral
    changes cancelling out.

    V3 is exactly what that diagnostic validated: TrendFollowingBaselineStrategyV0's
    unchanged eligibility gate and unchanged ranking, with a single addition
    -- ranking multiplied by close/high_252 (how close the candidate is to
    its own real trailing-year high; 1.0 at a genuine new high, less the
    further below it). No volatility-adjustment, no trend-strength
    weighting -- both were tested and dropped on real evidence, not
    theory. The fundamentals disqualifiers (a real net loss, or excessive
    non-financial leverage, when a filing has actually been ingested) are
    kept from V1/V2 for genuine real-world safety value; they were
    confirmed inert against this specific historical backtest (current real
    fundamentals coverage is too thin to have fired here), so keeping them
    doesn't confound the validated result above.
    """

    strategy_name = "QualityMomentumStrategyV3"
    strategy_version = "V3"

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
            and candidate.average_daily_value_traded_20 > Decimal(100000)
            and self._passes_fundamentals(candidate)
        ]
        return sorted(
            eligible,
            key=lambda item: (
                -self._score(item),
                -(item.price_to_sma_200 or Decimal(0)),
                item.instrument_id,
            ),
        )

    def _passes_fundamentals(self, candidate: Candidate) -> bool:
        if not candidate.fundamentals_available:
            return True
        if candidate.profit_for_period is not None and candidate.profit_for_period < 0:
            return False
        if (
            candidate.sector != FINANCIAL_SECTOR_LABEL
            and candidate.debt_equity_ratio is not None
            and candidate.debt_equity_ratio > MAXIMUM_NON_FINANCIAL_DEBT_EQUITY_RATIO
        ):
            return False
        return True

    def _score(self, candidate: Candidate) -> Decimal:
        assert candidate.momentum_60 is not None
        high_proximity = Decimal(1)
        if candidate.high_252 is not None and candidate.high_252 > 0:
            high_proximity = candidate.close / candidate.high_252
        return candidate.momentum_60 * high_proximity

    def propose_target_weights(
        self, ranked: list[Candidate], maximum_position_count: int
    ) -> dict[str, Decimal]:
        selected = ranked[:maximum_position_count]
        if not selected:
            return {}
        weight = Decimal("0.80") / Decimal(len(selected))
        return {candidate.instrument_id: weight for candidate in selected}

    def invalidation_price(self, candidate: Candidate) -> Decimal:
        if candidate.atr_14 is None:
            raise ValueError("QualityMomentumStrategyV3 requires ATR_14.")
        return candidate.close - (Decimal(2) * candidate.atr_14)


MAXIMUM_ABSOLUTE_PE_RATIO = Decimal("75")
MAXIMUM_QOQ_PROFIT_DECLINE = Decimal("0.5")


class HealthGatedMomentumStrategyV1(StrategyContract):
    """A genuinely different architecture from every strategy above: those
    are all pure relative rankers -- "which of these candidates is best" --
    so a single candidate's fundamentals can only ever matter as a
    disqualifier or a tiebreak against peers, never as a real judgment
    about that one stock's own condition. This strategy is deliberately
    two layers, in this order:

    Layer 1 (_is_healthy): an ABSOLUTE, self-referential health check --
    "is this stock, by itself, in good shape right now" -- using no peer
    comparison at all. Technical health reuses TrendFollowingBaselineStrategyV0's
    own validated core (close > SMA_50 > SMA_200, positive 60-day momentum,
    a real liquidity floor) plus a not-in-severe-decline-from-its-own-real-
    high check. Fundamentals health reuses the real net-loss/excess-leverage
    disqualifiers already validated in V1/V2/V3, plus two genuinely new
    absolute checks only possible now that real multi-quarter data exists:
    a real quarter-over-quarter profit trend (not just a single snapshot --
    is the business getting worse, not just "was it profitable last
    quarter"), and a sanity ceiling on P/E computed from real TTM EPS.
    Every fundamentals check is graceful, never a hard requirement -- a
    stock with no real filing yet (still the large majority of the
    universe) is judged on technical health alone, exactly like V0 always
    was; nothing is excluded for missing data, only ever for a real,
    known red flag.

    Layer 2 (_score), only ever applied to stocks that already passed
    Layer 1: the comparison across survivors. This reuses
    QualityMomentumStrategyV3's exact, real-evidence-validated ranking --
    momentum weighted by proximity to the real trailing 252-day high --
    rather than inventing a new, untested ranking scheme on top of an
    already-new health gate. One genuinely new idea evaluated at a time.

    The not-in-severe-decline check and the two new fundamentals checks
    are well-motivated by the "absolute health" framing this strategy
    exists to test, but -- unlike the momentum-ranking factors in V1/V2/V3
    -- have NOT yet been isolated and backtested individually. Treat this
    whole strategy the same way V1/V2/V3 were treated: real evidence from
    a real backtest decides whether it's worth keeping, not this docstring.
    """

    strategy_name = "HealthGatedMomentumStrategyV1"
    strategy_version = "V1"

    def rank_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        healthy = [candidate for candidate in candidates if self._is_healthy(candidate)]
        scored = [(self._score(candidate), candidate) for candidate in healthy]
        scored.sort(key=lambda pair: (-pair[0], pair[1].instrument_id))
        return [candidate for _, candidate in scored]

    def _is_healthy(self, candidate: Candidate) -> bool:
        # Layer 1a -- absolute technical health.
        if (
            candidate.sma_50 is None
            or candidate.sma_200 is None
            or candidate.momentum_60 is None
            or candidate.average_daily_value_traded_20 is None
        ):
            return False
        if not (candidate.close > candidate.sma_50 > candidate.sma_200):
            return False
        if candidate.momentum_60 <= 0:
            return False
        if candidate.average_daily_value_traded_20 <= Decimal(100000):
            return False
        # Not in a severe decline from its own real trailing high -- graceful
        # (skipped) until 252+ real days of history exist for this instrument.
        if (
            candidate.high_252 is not None
            and candidate.high_252 > 0
            and candidate.close < (Decimal("0.85") * candidate.high_252)
        ):
            return False

        # Layer 1b -- absolute fundamentals health, only when a real filing
        # actually exists; never a requirement, only ever a real red flag.
        if candidate.fundamentals_available:
            if candidate.profit_for_period is not None and candidate.profit_for_period < 0:
                return False
            if (
                candidate.sector != FINANCIAL_SECTOR_LABEL
                and candidate.debt_equity_ratio is not None
                and candidate.debt_equity_ratio > MAXIMUM_NON_FINANCIAL_DEBT_EQUITY_RATIO
            ):
                return False
            if (
                candidate.ttm_eps is not None
                and candidate.ttm_eps > 0
                and candidate.close > 0
                and (candidate.close / candidate.ttm_eps) > MAXIMUM_ABSOLUTE_PE_RATIO
            ):
                return False
            if (
                candidate.profit_for_period is not None
                and candidate.profit_for_period_prior_quarter is not None
                and candidate.profit_for_period_prior_quarter > 0
            ):
                decline = (
                    candidate.profit_for_period_prior_quarter - candidate.profit_for_period
                ) / candidate.profit_for_period_prior_quarter
                if decline > MAXIMUM_QOQ_PROFIT_DECLINE:
                    return False

        return True

    def _score(self, candidate: Candidate) -> Decimal:
        """Layer 2 -- QualityMomentumStrategyV3's exact validated comparison,
        reused unchanged rather than inventing a new ranking scheme."""
        assert candidate.momentum_60 is not None
        high_proximity = Decimal(1)
        if candidate.high_252 is not None and candidate.high_252 > 0:
            high_proximity = candidate.close / candidate.high_252
        return candidate.momentum_60 * high_proximity

    def propose_target_weights(
        self, ranked: list[Candidate], maximum_position_count: int
    ) -> dict[str, Decimal]:
        selected = ranked[:maximum_position_count]
        if not selected:
            return {}
        weight = Decimal("0.80") / Decimal(len(selected))
        return {candidate.instrument_id: weight for candidate in selected}

    def invalidation_price(self, candidate: Candidate) -> Decimal:
        if candidate.atr_14 is None:
            raise ValueError("HealthGatedMomentumStrategyV1 requires ATR_14.")
        return candidate.close - (Decimal(2) * candidate.atr_14)


class DiversifiedRiskOverlayStrategyV1(StrategyContract):
    """Every strategy above -- V0 through HealthGatedMomentumStrategyV1 --
    shares one structural trait: it requires a confirmed uptrend (close >
    SMA_50 > SMA_200, positive momentum) just to participate at all, and
    concentrates into a handful of positions (top 8) when it does. A real,
    isolated comparison this session found that trait itself was the
    problem: EqualWeightUniverseBenchmarkStrategyV0 -- which has no trend
    requirement and holds the entire real eligible universe, always --
    beat every one of those selective, sometimes-in-cash strategies, and
    was the only one to clearly beat a plain fixed deposit over the same
    real 10-year window. Being selective about *when* to be invested cost
    more in missed compounding than it saved in avoided drawdowns.

    This strategy tests the natural next question: can real risk signals
    still add value *without* reintroducing that trend-gate/concentration
    trait? It stays deliberately close to EqualWeight's own winning shape --
    broad, always-invested, equal-weighted -- and uses technicals and
    fundamentals only to EXCLUDE instruments in real, absolute trouble,
    never to require an uptrend to participate and never to concentrate
    into a small "best of" subset. A stock doesn't have to be rising to
    stay in; it only has to not be in genuine trouble.

    Excluded only for a real red flag, each independently, always graceful
    when data doesn't exist yet (never punished for missing data):
    - a real net loss or excessive non-financial leverage, when a real
      filing has been ingested (the same disqualifiers validated in
      V1/V2/V3/HealthGatedMomentumStrategyV1);
    - a severe real decline from its own trailing 252-day high (more than
      15% off), the one technical signal from HealthGatedMomentumStrategyV1
      that showed real, explicable value in this session's testing.

    No momentum requirement, no trend requirement, no position-count cap,
    no per-position stop -- deliberately, matching EqualWeight's own
    already-validated shape as closely as possible so this real backtest
    answers one question cleanly: does excluding genuine red flags improve
    on plain equal-weighting, or does even that much selectivity cost more
    than it protects.
    """

    strategy_name = "DiversifiedRiskOverlayStrategyV1"
    strategy_version = "V1"

    def rank_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        self.validate_inputs(candidates)
        survivors = [candidate for candidate in candidates if self._has_no_red_flag(candidate)]
        return sorted(survivors, key=lambda item: item.instrument_id)

    def _has_no_red_flag(self, candidate: Candidate) -> bool:
        if (
            candidate.high_252 is not None
            and candidate.high_252 > 0
            and candidate.close < (Decimal("0.85") * candidate.high_252)
        ):
            return False
        if candidate.fundamentals_available:
            if candidate.profit_for_period is not None and candidate.profit_for_period < 0:
                return False
            if (
                candidate.sector != FINANCIAL_SECTOR_LABEL
                and candidate.debt_equity_ratio is not None
                and candidate.debt_equity_ratio > MAXIMUM_NON_FINANCIAL_DEBT_EQUITY_RATIO
            ):
                return False
        return True

    def propose_target_weights(
        self, ranked: list[Candidate], maximum_position_count: int
    ) -> dict[str, Decimal]:
        # Deliberately ignores maximum_position_count -- same real reasoning
        # as EqualWeightUniverseBenchmarkStrategyV0: a cap here would
        # silently reintroduce the concentration this strategy exists to
        # avoid, capping "the whole healthy universe" down to an arbitrary
        # subset by nothing more than which id happens to sort first.
        if not ranked:
            return {}
        weight = Decimal("0.80") / Decimal(len(ranked))
        return {candidate.instrument_id: weight for candidate in ranked}


class DiversifiedRiskOverlayStrategyV2(StrategyContract):
    """V1's own isolated diagnostic found that hard-excluding anything more
    than 15% below its own real 252-day high destroyed most of the return
    (52.53% vs EqualWeight's 216.29%, on the exact same real data) without
    a matching risk benefit -- because a stock off its high is frequently a
    genuine recovery in progress, not just a decliner, and a blunt yes/no
    cutoff can't tell those apart without a trend signal alongside it
    (which is exactly why the same rule worked well inside
    HealthGatedMomentumStrategyV1's trend-gated design, but actively hurt
    here, where there's no trend context at all).

    V2 tests the natural next idea instead of abandoning the signal
    entirely: keep every instrument in -- never hard-exclude for being off
    its high -- but WEIGHT it by real proximity to that high. A stock
    sitting right at a new high gets a full share; one further below it
    gets proportionally less, never zero, so a genuine recovery still
    participates instead of being locked out entirely. Real red flags (a
    real net loss, or excessive non-financial leverage, when a filing has
    actually been ingested) remain hard exclusions -- those are genuine,
    binary problems, not a judgment call about where a stock sits in its
    own price cycle, which proximity-to-high inherently is.
    """

    strategy_name = "DiversifiedRiskOverlayStrategyV2"
    strategy_version = "V2"

    def rank_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        self.validate_inputs(candidates)
        survivors = [candidate for candidate in candidates if self._passes_fundamentals(candidate)]
        return sorted(survivors, key=lambda item: item.instrument_id)

    def _passes_fundamentals(self, candidate: Candidate) -> bool:
        if not candidate.fundamentals_available:
            return True
        if candidate.profit_for_period is not None and candidate.profit_for_period < 0:
            return False
        if (
            candidate.sector != FINANCIAL_SECTOR_LABEL
            and candidate.debt_equity_ratio is not None
            and candidate.debt_equity_ratio > MAXIMUM_NON_FINANCIAL_DEBT_EQUITY_RATIO
        ):
            return False
        return True

    def _proximity_weight(self, candidate: Candidate) -> Decimal:
        """1.0 (neutral -- neither rewarded nor penalized) until 252+ real
        days of history exist; otherwise close/high_252, always in (0, 1]
        since high_252 is itself the real max of a window that includes
        close -- a genuine new high scores exactly 1.0, never higher."""
        if candidate.high_252 is not None and candidate.high_252 > 0 and candidate.close > 0:
            return candidate.close / candidate.high_252
        return Decimal(1)

    def propose_target_weights(
        self, ranked: list[Candidate], maximum_position_count: int
    ) -> dict[str, Decimal]:
        # Same deliberate no-cap reasoning as V1 -- every fundamentals-clean
        # instrument stays in, sized by proximity rather than excluded.
        if not ranked:
            return {}
        proximity_weights = {
            candidate.instrument_id: self._proximity_weight(candidate) for candidate in ranked
        }
        total_weight = sum(proximity_weights.values())
        if total_weight <= 0:
            # Not reachable in practice (close/high_252 is always in (0, 1]
            # for real prices) -- fail closed to equal weight rather than
            # divide by zero if it ever somehow were.
            equal_weight = Decimal("0.80") / Decimal(len(ranked))
            return {candidate.instrument_id: equal_weight for candidate in ranked}
        return {
            instrument_id: (Decimal("0.80") * weight / total_weight)
            for instrument_id, weight in proximity_weights.items()
        }
