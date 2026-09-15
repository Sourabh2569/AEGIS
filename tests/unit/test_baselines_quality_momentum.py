from __future__ import annotations

from decimal import Decimal

from aegis.strategies.baselines import Candidate, QualityMomentumStrategyV1

STRATEGY = QualityMomentumStrategyV1()


def _base_kwargs() -> dict:
    """A candidate that passes every technical filter -- individual tests
    mutate exactly one field away from this baseline to isolate one rule at
    a time."""
    return dict(
        instrument_id="AEGIS-IN-TEST",
        sector="Information Technology",
        cluster="Information Technology",
        close=Decimal(120),
        momentum_60=Decimal("0.05"),
        price_to_sma_200=Decimal("0.10"),
        sma_50=Decimal(115),
        sma_200=Decimal(100),
        atr_14=Decimal(2),
        average_daily_value_traded_20=Decimal(500_000),
        momentum_20=Decimal("0.02"),
        momentum_120=Decimal("0.08"),
        sma_100=Decimal(108),
        realized_volatility_60=Decimal("0.01"),
        high_252=Decimal(125),
        average_daily_value_traded_60=Decimal(500_000),
    )


def _candidate(**overrides) -> Candidate:
    kwargs = _base_kwargs()
    kwargs.update(overrides)
    return Candidate(**kwargs)


def test_a_fully_passing_candidate_is_eligible() -> None:
    ranked = STRATEGY.rank_candidates([_candidate()])
    assert len(ranked) == 1


def test_disagreement_across_momentum_horizons_excludes_the_candidate() -> None:
    candidate = _candidate(momentum_120=Decimal("-0.01"))
    assert STRATEGY.rank_candidates([candidate]) == []


def test_weak_trend_without_sma_100_confirmation_excludes_the_candidate() -> None:
    # close > sma_50 holds, but sma_50 is NOT above sma_100 here -- V0's
    # two-SMA check would pass this; V1's three-SMA check must not.
    candidate = _candidate(sma_50=Decimal(105), sma_100=Decimal(110))
    assert STRATEGY.rank_candidates([candidate]) == []


def test_dried_up_liquidity_trend_excludes_the_candidate() -> None:
    # Above the absolute 100,000 floor, but well below 70% of its own
    # 60-day average -- liquidity has meaningfully dried up recently.
    candidate = _candidate(
        average_daily_value_traded_20=Decimal(200_000),
        average_daily_value_traded_60=Decimal(500_000),
    )
    assert STRATEGY.rank_candidates([candidate]) == []


def test_falling_knife_excludes_the_candidate() -> None:
    # close is more than 15% below the real trailing 252-day high.
    candidate = _candidate(close=Decimal(100), high_252=Decimal(130))
    assert STRATEGY.rank_candidates([candidate]) == []


def test_overextended_above_sma_50_excludes_the_candidate() -> None:
    # close is more than 25% above its own 50-day average.
    candidate = _candidate(close=Decimal(150), sma_50=Decimal(110), high_252=Decimal(150))
    assert STRATEGY.rank_candidates([candidate]) == []


def test_a_real_reported_net_loss_excludes_the_candidate_when_fundamentals_are_available() -> None:
    candidate = _candidate(fundamentals_available=True, profit_for_period=Decimal(-1000))
    assert STRATEGY.rank_candidates([candidate]) == []


def test_excessive_leverage_excludes_a_non_financial_candidate() -> None:
    candidate = _candidate(
        sector="Consumer Durables",
        fundamentals_available=True,
        debt_equity_ratio=Decimal("3.5"),
    )
    assert STRATEGY.rank_candidates([candidate]) == []


def test_excessive_leverage_does_not_exclude_a_financial_sector_candidate() -> None:
    # A bank's D/E ratio is structurally different -- this check must be
    # skipped entirely for Financial Services, not just have a higher bar.
    candidate = _candidate(
        sector="Financial Services",
        fundamentals_available=True,
        debt_equity_ratio=Decimal("8.0"),
    )
    ranked = STRATEGY.rank_candidates([candidate])
    assert len(ranked) == 1


def test_missing_fundamentals_never_excludes_a_candidate_on_technical_merit() -> None:
    # The common case today: no real filing ingested yet for this symbol.
    # A candidate must never be punished for data that simply doesn't exist.
    candidate = _candidate(fundamentals_available=False, profit_for_period=None, debt_equity_ratio=None)
    ranked = STRATEGY.rank_candidates([candidate])
    assert len(ranked) == 1


def test_incomplete_technical_data_excludes_the_candidate() -> None:
    candidate = _candidate(high_252=None)
    assert STRATEGY.rank_candidates([candidate]) == []


def test_ranking_favors_higher_volatility_adjusted_blended_momentum() -> None:
    strong = _candidate(instrument_id="STRONG", momentum_20=Decimal("0.10"), momentum_60=Decimal("0.10"), momentum_120=Decimal("0.10"), realized_volatility_60=Decimal("0.01"))
    weak = _candidate(instrument_id="WEAK", momentum_20=Decimal("0.01"), momentum_60=Decimal("0.01"), momentum_120=Decimal("0.01"), realized_volatility_60=Decimal("0.05"))
    ranked = STRATEGY.rank_candidates([weak, strong])
    assert [candidate.instrument_id for candidate in ranked] == ["STRONG", "WEAK"]


def test_earnings_yield_tiebreak_favors_the_cheaper_of_two_otherwise_similar_candidates() -> None:
    # Same close (120, the passing baseline) and identical momentum/volatility
    # inputs for both -- only ttm_eps differs, isolating the value tiebreak
    # from every eligibility filter and from the momentum score itself.
    expensive = _candidate(instrument_id="EXPENSIVE", fundamentals_available=True, ttm_eps=Decimal("1.0"))
    cheap = _candidate(instrument_id="CHEAP", fundamentals_available=True, ttm_eps=Decimal("40.0"))
    ranked = STRATEGY.rank_candidates([expensive, cheap])
    assert [candidate.instrument_id for candidate in ranked] == ["CHEAP", "EXPENSIVE"]


def test_value_tiebreak_is_inert_without_real_ttm_eps() -> None:
    a = _candidate(instrument_id="A", fundamentals_available=False)
    b = _candidate(instrument_id="B", fundamentals_available=False)
    ranked = STRATEGY.rank_candidates([a, b])
    # Identical inputs otherwise -- with no fundamentals at all, ranking
    # falls back purely to the deterministic instrument_id tie-break.
    assert [candidate.instrument_id for candidate in ranked] == ["A", "B"]


def test_propose_target_weights_matches_v0_shape() -> None:
    candidates = [_candidate(instrument_id=f"I{i}") for i in range(3)]
    ranked = STRATEGY.rank_candidates(candidates)
    weights = STRATEGY.propose_target_weights(ranked, maximum_position_count=8)
    assert len(weights) == 3
    for weight in weights.values():
        assert weight == Decimal("0.80") / Decimal(3)


def test_propose_target_weights_caps_at_maximum_position_count() -> None:
    candidates = [_candidate(instrument_id=f"I{i}") for i in range(5)]
    ranked = STRATEGY.rank_candidates(candidates)
    weights = STRATEGY.propose_target_weights(ranked, maximum_position_count=2)
    assert len(weights) == 2


def test_propose_target_weights_is_empty_when_nothing_is_eligible() -> None:
    assert STRATEGY.propose_target_weights([], maximum_position_count=8) == {}


def test_invalidation_price_matches_v0s_atr_stop() -> None:
    candidate = _candidate(close=Decimal(120), atr_14=Decimal(3))
    assert STRATEGY.invalidation_price(candidate) == Decimal(114)


def test_invalidation_price_requires_atr() -> None:
    candidate = _candidate(atr_14=None)
    try:
        STRATEGY.invalidation_price(candidate)
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_get_strategy_metadata_is_honest_about_being_research_only() -> None:
    metadata = STRATEGY.get_strategy_metadata()
    assert metadata["strategy_name"] == "QualityMomentumStrategyV1"
    assert metadata["classification"] == "RESEARCH_ONLY"
    assert metadata["not_recommendation"] is True
