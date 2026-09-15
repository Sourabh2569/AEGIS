from __future__ import annotations

from decimal import Decimal

from aegis.strategies.baselines import Candidate, HealthGatedMomentumStrategyV1

STRATEGY = HealthGatedMomentumStrategyV1()


def _base_kwargs() -> dict:
    """A candidate that passes every Layer 1 check -- individual tests
    mutate one field to isolate one rule."""
    return dict(
        instrument_id="AEGIS-IN-TEST",
        sector="Information Technology",
        cluster="Information Technology",
        close=Decimal(120),
        momentum_60=Decimal("0.05"),
        price_to_sma_200=Decimal("0.20"),
        sma_50=Decimal(115),
        sma_200=Decimal(100),
        atr_14=Decimal(2),
        average_daily_value_traded_20=Decimal(500_000),
    )


def _candidate(**overrides) -> Candidate:
    kwargs = _base_kwargs()
    kwargs.update(overrides)
    return Candidate(**kwargs)


def test_a_technically_and_fundamentally_clean_candidate_is_healthy() -> None:
    assert len(STRATEGY.rank_candidates([_candidate()])) == 1


def test_weak_trend_fails_layer_1() -> None:
    assert STRATEGY.rank_candidates([_candidate(sma_50=Decimal(90))]) == []


def test_negative_momentum_fails_layer_1() -> None:
    assert STRATEGY.rank_candidates([_candidate(momentum_60=Decimal("-0.01"))]) == []


def test_illiquid_instrument_fails_layer_1() -> None:
    assert STRATEGY.rank_candidates([_candidate(average_daily_value_traded_20=Decimal(50_000))]) == []


def test_severe_decline_from_own_real_high_fails_layer_1() -> None:
    candidate = _candidate(close=Decimal(100), high_252=Decimal(130))
    assert STRATEGY.rank_candidates([candidate]) == []


def test_missing_high_252_does_not_fail_layer_1() -> None:
    assert len(STRATEGY.rank_candidates([_candidate(high_252=None)])) == 1


def test_real_net_loss_fails_layer_1_when_fundamentals_available() -> None:
    candidate = _candidate(fundamentals_available=True, profit_for_period=Decimal(-1000))
    assert STRATEGY.rank_candidates([candidate]) == []


def test_excessive_leverage_fails_layer_1_for_non_financial_sector() -> None:
    candidate = _candidate(
        sector="Consumer Durables", fundamentals_available=True, debt_equity_ratio=Decimal("3.5")
    )
    assert STRATEGY.rank_candidates([candidate]) == []


def test_excessive_leverage_does_not_fail_a_financial_sector_candidate() -> None:
    candidate = _candidate(
        sector="Financial Services", fundamentals_available=True, debt_equity_ratio=Decimal("8.0")
    )
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_pe_above_the_absolute_ceiling_fails_layer_1() -> None:
    # close=120, ttm_eps=1.0 -> P/E = 120, well above the 75x ceiling.
    candidate = _candidate(fundamentals_available=True, ttm_eps=Decimal("1.0"))
    assert STRATEGY.rank_candidates([candidate]) == []


def test_pe_within_the_absolute_ceiling_does_not_fail() -> None:
    # close=120, ttm_eps=5.0 -> P/E = 24, comfortably under the ceiling.
    candidate = _candidate(fundamentals_available=True, ttm_eps=Decimal("5.0"))
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_severe_qoq_profit_decline_fails_layer_1() -> None:
    candidate = _candidate(
        fundamentals_available=True,
        profit_for_period=Decimal(400),
        profit_for_period_prior_quarter=Decimal(1000),  # 60% decline
    )
    assert STRATEGY.rank_candidates([candidate]) == []


def test_moderate_qoq_profit_decline_does_not_fail() -> None:
    candidate = _candidate(
        fundamentals_available=True,
        profit_for_period=Decimal(800),
        profit_for_period_prior_quarter=Decimal(1000),  # 20% decline
    )
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_missing_fundamentals_never_fails_layer_1_on_technical_merit() -> None:
    candidate = _candidate(fundamentals_available=False)
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_missing_prior_quarter_profit_does_not_fail_the_trend_check() -> None:
    # Only one real quarter visible -- no trend to judge yet, graceful.
    candidate = _candidate(
        fundamentals_available=True,
        profit_for_period=Decimal(100),
        profit_for_period_prior_quarter=None,
    )
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_layer_2_ranking_matches_v3s_validated_score() -> None:
    at_high = _candidate(instrument_id="AT_HIGH", close=Decimal(120), high_252=Decimal(120))
    # 120/135 = 0.888 -- still within the 15%-off-high health band (0.85
    # floor), so this candidate passes Layer 1 and the difference is purely
    # a Layer 2 ranking question, not a health-gate exclusion.
    modestly_off_high = _candidate(
        instrument_id="MODESTLY_OFF_HIGH", close=Decimal(120), high_252=Decimal(135)
    )
    ranked = STRATEGY.rank_candidates([modestly_off_high, at_high])
    assert [c.instrument_id for c in ranked] == ["AT_HIGH", "MODESTLY_OFF_HIGH"]


def test_an_unhealthy_candidate_never_reaches_layer_2_regardless_of_momentum() -> None:
    # Huge momentum, but a real net loss -- must still be excluded entirely,
    # proving Layer 1 is a real gate and not just a scoring input.
    candidate = _candidate(
        momentum_60=Decimal("0.50"), fundamentals_available=True, profit_for_period=Decimal(-1)
    )
    assert STRATEGY.rank_candidates([candidate]) == []


def test_propose_target_weights_matches_v0_shape() -> None:
    candidates = [_candidate(instrument_id=f"I{i}") for i in range(3)]
    ranked = STRATEGY.rank_candidates(candidates)
    weights = STRATEGY.propose_target_weights(ranked, maximum_position_count=8)
    assert len(weights) == 3
    for weight in weights.values():
        assert weight == Decimal("0.80") / Decimal(3)


def test_propose_target_weights_is_empty_when_nothing_is_healthy() -> None:
    assert STRATEGY.propose_target_weights([], maximum_position_count=8) == {}


def test_invalidation_price_matches_v0s_atr_stop() -> None:
    candidate = _candidate(close=Decimal(120), atr_14=Decimal(3))
    assert STRATEGY.invalidation_price(candidate) == Decimal(114)


def test_get_strategy_metadata_is_honest_about_being_research_only() -> None:
    metadata = STRATEGY.get_strategy_metadata()
    assert metadata["strategy_name"] == "HealthGatedMomentumStrategyV1"
    assert metadata["classification"] == "RESEARCH_ONLY"
    assert metadata["not_recommendation"] is True
