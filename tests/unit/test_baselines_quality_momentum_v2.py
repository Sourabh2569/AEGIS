from __future__ import annotations

from decimal import Decimal

from aegis.strategies.baselines import Candidate, QualityMomentumStrategyV2

STRATEGY = QualityMomentumStrategyV2()


def _base_kwargs() -> dict:
    """Matches TrendFollowingBaselineStrategyV0's own eligibility exactly --
    V2's hard gate is deliberately identical to V0's, so this baseline
    passes both. Individual tests mutate one field to isolate one rule."""
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


def test_a_v0_style_passing_candidate_is_eligible() -> None:
    assert len(STRATEGY.rank_candidates([_candidate()])) == 1


def test_weak_trend_excludes_the_candidate() -> None:
    candidate = _candidate(sma_50=Decimal(90))  # close > sma_50 fails
    assert STRATEGY.rank_candidates([candidate]) == []


def test_negative_momentum_excludes_the_candidate() -> None:
    candidate = _candidate(momentum_60=Decimal("-0.01"))
    assert STRATEGY.rank_candidates([candidate]) == []


def test_illiquid_instrument_excludes_the_candidate() -> None:
    candidate = _candidate(average_daily_value_traded_20=Decimal(50_000))
    assert STRATEGY.rank_candidates([candidate]) == []


def test_a_real_reported_net_loss_excludes_the_candidate_when_fundamentals_are_available() -> None:
    candidate = _candidate(fundamentals_available=True, profit_for_period=Decimal(-1000))
    assert STRATEGY.rank_candidates([candidate]) == []


def test_excessive_leverage_excludes_a_non_financial_candidate() -> None:
    candidate = _candidate(
        sector="Consumer Durables", fundamentals_available=True, debt_equity_ratio=Decimal("3.5")
    )
    assert STRATEGY.rank_candidates([candidate]) == []


def test_excessive_leverage_does_not_exclude_a_financial_sector_candidate() -> None:
    candidate = _candidate(
        sector="Financial Services", fundamentals_available=True, debt_equity_ratio=Decimal("8.0")
    )
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_missing_fundamentals_never_excludes_a_candidate_on_technical_merit() -> None:
    candidate = _candidate(fundamentals_available=False)
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_unlike_v1_an_overextended_candidate_is_not_excluded_only_scored() -> None:
    """The whole point of V2: a candidate more than 25% above its SMA_50 --
    which V1's hard overextension filter would have thrown out entirely --
    must still be eligible here. It's scored, not gated."""
    candidate = _candidate(close=Decimal(160), sma_50=Decimal(110), high_252=Decimal(160))
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_unlike_v1_a_single_weak_momentum_horizon_does_not_exclude_the_candidate() -> None:
    """A real 60-day uptrend with a temporarily soft 20-day reading must
    stay eligible -- V1's hard three-horizon-agreement filter would have
    excluded this outright; V2 only scores it down."""
    candidate = _candidate(momentum_20=Decimal("-0.02"), momentum_120=Decimal("0.10"))
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_missing_optional_technical_fields_do_not_exclude_the_candidate() -> None:
    """V2's eligibility needs only what TrendFollowingBaselineStrategyV0
    needs (200 real days) -- momentum_20/120, sma_100, realized_volatility_60,
    high_252 are all still None at that point and must not block eligibility,
    only skip their scoring contribution."""
    candidate = _candidate(
        momentum_20=None,
        momentum_120=None,
        sma_100=None,
        realized_volatility_60=None,
        high_252=None,
        average_daily_value_traded_60=None,
    )
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_ranking_rewards_a_stronger_established_trend() -> None:
    strong_trend = _candidate(instrument_id="STRONG_TREND", price_to_sma_200=Decimal("0.40"))
    weak_trend = _candidate(instrument_id="WEAK_TREND", price_to_sma_200=Decimal("0.05"))
    ranked = STRATEGY.rank_candidates([weak_trend, strong_trend])
    assert [c.instrument_id for c in ranked] == ["STRONG_TREND", "WEAK_TREND"]


def test_ranking_rewards_proximity_to_the_real_252_day_high() -> None:
    at_new_high = _candidate(instrument_id="AT_HIGH", close=Decimal(120), high_252=Decimal(120))
    off_the_high = _candidate(instrument_id="OFF_HIGH", close=Decimal(120), high_252=Decimal(160))
    ranked = STRATEGY.rank_candidates([off_the_high, at_new_high])
    assert [c.instrument_id for c in ranked] == ["AT_HIGH", "OFF_HIGH"]


def test_high_proximity_factor_is_neutral_when_high_252_is_unavailable() -> None:
    a = _candidate(instrument_id="A", high_252=None)
    b = _candidate(instrument_id="B", high_252=None)
    ranked = STRATEGY.rank_candidates([a, b])
    assert [c.instrument_id for c in ranked] == ["A", "B"]  # falls back to instrument_id order


def test_earnings_yield_tiebreak_favors_the_cheaper_of_two_otherwise_similar_candidates() -> None:
    expensive = _candidate(instrument_id="EXPENSIVE", fundamentals_available=True, ttm_eps=Decimal("1.0"))
    cheap = _candidate(instrument_id="CHEAP", fundamentals_available=True, ttm_eps=Decimal("40.0"))
    ranked = STRATEGY.rank_candidates([expensive, cheap])
    assert [c.instrument_id for c in ranked] == ["CHEAP", "EXPENSIVE"]


def test_blended_momentum_uses_only_the_real_horizons_present() -> None:
    # Only momentum_60 present (matches V0's real-world common case at day
    # 200-251, before the 252-day fields exist) -- blended momentum must
    # equal momentum_60 itself, not be diluted by treating missing horizons
    # as zero.
    strategy = QualityMomentumStrategyV2()
    candidate = _candidate(momentum_20=None, momentum_120=None, momentum_60=Decimal("0.08"))
    assert strategy._blended_momentum(candidate) == Decimal("0.08")


def test_propose_target_weights_matches_v0_shape() -> None:
    candidates = [_candidate(instrument_id=f"I{i}") for i in range(3)]
    ranked = STRATEGY.rank_candidates(candidates)
    weights = STRATEGY.propose_target_weights(ranked, maximum_position_count=8)
    assert len(weights) == 3
    for weight in weights.values():
        assert weight == Decimal("0.80") / Decimal(3)


def test_invalidation_price_matches_v0s_atr_stop() -> None:
    candidate = _candidate(close=Decimal(120), atr_14=Decimal(3))
    assert STRATEGY.invalidation_price(candidate) == Decimal(114)


def test_get_strategy_metadata_is_honest_about_being_research_only() -> None:
    metadata = STRATEGY.get_strategy_metadata()
    assert metadata["strategy_name"] == "QualityMomentumStrategyV2"
    assert metadata["classification"] == "RESEARCH_ONLY"
    assert metadata["not_recommendation"] is True
