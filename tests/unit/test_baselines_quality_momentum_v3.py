from __future__ import annotations

from decimal import Decimal

from aegis.strategies.baselines import Candidate, QualityMomentumStrategyV3

STRATEGY = QualityMomentumStrategyV3()


def _base_kwargs() -> dict:
    """Matches TrendFollowingBaselineStrategyV0's own eligibility exactly --
    V3's gate is deliberately identical to V0's."""
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
    assert STRATEGY.rank_candidates([_candidate(sma_50=Decimal(90))]) == []


def test_negative_momentum_excludes_the_candidate() -> None:
    assert STRATEGY.rank_candidates([_candidate(momentum_60=Decimal("-0.01"))]) == []


def test_illiquid_instrument_excludes_the_candidate() -> None:
    assert STRATEGY.rank_candidates([_candidate(average_daily_value_traded_20=Decimal(50_000))]) == []


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
    assert len(STRATEGY.rank_candidates([_candidate(fundamentals_available=False)])) == 1


def test_a_candidate_more_than_25_percent_above_sma_50_is_not_excluded() -> None:
    # V1's hard overextension filter would have thrown this out; V3 has no
    # such filter at all (that specific addition was never validated to help).
    candidate = _candidate(close=Decimal(160), sma_50=Decimal(110), high_252=Decimal(160))
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_missing_high_252_does_not_exclude_the_candidate() -> None:
    # Before 252 real days of history exist -- the common case at day
    # 200-251 -- the proximity factor is simply neutral (1.0), not blocking.
    assert len(STRATEGY.rank_candidates([_candidate(high_252=None)])) == 1


def test_ranking_prefers_a_candidate_at_its_real_trailing_high_over_one_further_below_it() -> None:
    at_high = _candidate(instrument_id="AT_HIGH", close=Decimal(120), high_252=Decimal(120))
    off_high = _candidate(instrument_id="OFF_HIGH", close=Decimal(120), high_252=Decimal(160))
    ranked = STRATEGY.rank_candidates([off_high, at_high])
    assert [c.instrument_id for c in ranked] == ["AT_HIGH", "OFF_HIGH"]


def test_ranking_still_prefers_higher_raw_momentum_when_proximity_is_equal() -> None:
    strong = _candidate(instrument_id="STRONG", momentum_60=Decimal("0.10"))
    weak = _candidate(instrument_id="WEAK", momentum_60=Decimal("0.02"))
    ranked = STRATEGY.rank_candidates([weak, strong])
    assert [c.instrument_id for c in ranked] == ["STRONG", "WEAK"]


def test_price_to_sma_200_breaks_ties_when_scores_are_equal() -> None:
    # Same momentum_60 and no high_252 for either (multiplier neutral for
    # both) -- score ties, so V0's own secondary sort key must decide.
    higher_trend = _candidate(instrument_id="HIGHER_TREND", price_to_sma_200=Decimal("0.30"))
    lower_trend = _candidate(instrument_id="LOWER_TREND", price_to_sma_200=Decimal("0.05"))
    ranked = STRATEGY.rank_candidates([lower_trend, higher_trend])
    assert [c.instrument_id for c in ranked] == ["HIGHER_TREND", "LOWER_TREND"]


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
    assert metadata["strategy_name"] == "QualityMomentumStrategyV3"
    assert metadata["classification"] == "RESEARCH_ONLY"
    assert metadata["not_recommendation"] is True
