from __future__ import annotations

from decimal import Decimal

from aegis.strategies.baselines import Candidate, DiversifiedRiskOverlayStrategyV1

STRATEGY = DiversifiedRiskOverlayStrategyV1()


def _candidate(**overrides) -> Candidate:
    kwargs = dict(
        instrument_id="AEGIS-IN-TEST",
        sector="Information Technology",
        cluster="Information Technology",
        close=Decimal(120),
        momentum_60=None,
        price_to_sma_200=None,
        sma_50=None,
        sma_200=None,
        atr_14=None,
        average_daily_value_traded_20=None,
    )
    kwargs.update(overrides)
    return Candidate(**kwargs)


def test_a_candidate_with_no_trend_or_momentum_data_at_all_is_still_included() -> None:
    """The whole point: unlike every ranking strategy in this file, this one
    never requires an uptrend, momentum, or even SMA/ATR data to
    participate -- only real red flags exclude a candidate."""
    candidate = _candidate()
    ranked = STRATEGY.rank_candidates([candidate])
    assert len(ranked) == 1


def test_negative_momentum_does_not_exclude_a_candidate() -> None:
    # A momentum-based strategy would exclude this; this one must not.
    candidate = _candidate(momentum_60=Decimal("-0.10"), sma_50=Decimal(90), sma_200=Decimal(100))
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_a_downtrend_does_not_exclude_a_candidate() -> None:
    candidate = _candidate(close=Decimal(80), sma_50=Decimal(90), sma_200=Decimal(100))
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_severe_decline_from_own_real_high_is_a_real_red_flag() -> None:
    candidate = _candidate(close=Decimal(100), high_252=Decimal(130))  # >15% off high
    assert STRATEGY.rank_candidates([candidate]) == []


def test_a_mild_pullback_from_the_high_is_not_a_red_flag() -> None:
    candidate = _candidate(close=Decimal(120), high_252=Decimal(130))  # ~7.7% off high
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_missing_high_252_is_never_a_red_flag() -> None:
    assert len(STRATEGY.rank_candidates([_candidate(high_252=None)])) == 1


def test_real_net_loss_is_a_red_flag_when_fundamentals_available() -> None:
    candidate = _candidate(fundamentals_available=True, profit_for_period=Decimal(-1))
    assert STRATEGY.rank_candidates([candidate]) == []


def test_excessive_leverage_is_a_red_flag_for_non_financial_sector() -> None:
    candidate = _candidate(
        sector="Consumer Durables", fundamentals_available=True, debt_equity_ratio=Decimal("3.0")
    )
    assert STRATEGY.rank_candidates([candidate]) == []


def test_excessive_leverage_is_not_a_red_flag_for_financial_sector() -> None:
    candidate = _candidate(
        sector="Financial Services", fundamentals_available=True, debt_equity_ratio=Decimal("9.0")
    )
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_missing_fundamentals_is_never_a_red_flag() -> None:
    assert len(STRATEGY.rank_candidates([_candidate(fundamentals_available=False)])) == 1


def test_weights_are_equal_and_uncapped_regardless_of_maximum_position_count() -> None:
    candidates = [_candidate(instrument_id=f"I{i}") for i in range(20)]
    ranked = STRATEGY.rank_candidates(candidates)
    weights = STRATEGY.propose_target_weights(ranked, maximum_position_count=8)
    assert len(weights) == 20
    for weight in weights.values():
        assert weight == Decimal("0.80") / Decimal(20)
    assert sum(weights.values()) == Decimal("0.80")


def test_a_red_flagged_candidate_among_many_is_the_only_one_excluded() -> None:
    healthy = [_candidate(instrument_id=f"HEALTHY{i}") for i in range(5)]
    unhealthy = _candidate(
        instrument_id="UNHEALTHY", fundamentals_available=True, profit_for_period=Decimal(-1)
    )
    ranked = STRATEGY.rank_candidates([*healthy, unhealthy])
    assert len(ranked) == 5
    assert "UNHEALTHY" not in {c.instrument_id for c in ranked}


def test_propose_target_weights_is_empty_when_nothing_survives() -> None:
    assert STRATEGY.propose_target_weights([], maximum_position_count=8) == {}


def test_strategy_has_no_invalidation_price_method() -> None:
    # Deliberately matches EqualWeightUniverseBenchmarkStrategyV0/
    # BuyAndHoldBenchmarkStrategyV0's own no-stop shape.
    assert not hasattr(STRATEGY, "invalidation_price")


def test_get_strategy_metadata_is_honest_about_being_research_only() -> None:
    metadata = STRATEGY.get_strategy_metadata()
    assert metadata["strategy_name"] == "DiversifiedRiskOverlayStrategyV1"
    assert metadata["classification"] == "RESEARCH_ONLY"
    assert metadata["not_recommendation"] is True
