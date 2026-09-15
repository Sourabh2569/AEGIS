from __future__ import annotations

from decimal import Decimal

from aegis.strategies.baselines import Candidate, EqualWeightUniverseBenchmarkStrategyV0

STRATEGY = EqualWeightUniverseBenchmarkStrategyV0()


def _candidate(instrument_id: str) -> Candidate:
    return Candidate(
        instrument_id=instrument_id,
        sector="Sector",
        cluster="Sector",
        close=Decimal(100),
        momentum_60=None,
        price_to_sma_200=None,
        sma_50=None,
        sma_200=None,
        atr_14=None,
        average_daily_value_traded_20=None,
    )


def test_rank_candidates_includes_every_candidate_with_no_filter() -> None:
    candidates = [_candidate(f"I{i}") for i in range(20)]
    ranked = STRATEGY.rank_candidates(candidates)
    assert len(ranked) == 20


def test_propose_target_weights_is_not_capped_by_maximum_position_count() -> None:
    """The actual bug this fixes: a fixed cap combined with a stable
    instrument_id sort meant the real 'universe' benchmark always held the
    exact same handful of instruments forever, never representing the
    universe at all. This must never regress."""
    candidates = [_candidate(f"I{i}") for i in range(20)]
    ranked = STRATEGY.rank_candidates(candidates)
    weights = STRATEGY.propose_target_weights(ranked, maximum_position_count=8)
    assert len(weights) == 20


def test_every_eligible_instrument_gets_an_equal_share_of_80_percent() -> None:
    candidates = [_candidate(f"I{i}") for i in range(5)]
    ranked = STRATEGY.rank_candidates(candidates)
    weights = STRATEGY.propose_target_weights(ranked, maximum_position_count=8)
    assert len(weights) == 5
    for weight in weights.values():
        assert weight == Decimal("0.80") / Decimal(5)
    assert sum(weights.values()) == Decimal("0.80")


def test_a_larger_real_universe_still_gets_equal_weight_uncapped() -> None:
    """Regression check at real universe scale (50 curated instruments) --
    the fix must hold regardless of how many real candidates exist."""
    candidates = [_candidate(f"I{i}") for i in range(50)]
    ranked = STRATEGY.rank_candidates(candidates)
    weights = STRATEGY.propose_target_weights(ranked, maximum_position_count=8)
    assert len(weights) == 50
    for weight in weights.values():
        assert weight == Decimal("0.80") / Decimal(50)


def test_propose_target_weights_is_empty_when_nothing_is_eligible() -> None:
    assert STRATEGY.propose_target_weights([], maximum_position_count=8) == {}
