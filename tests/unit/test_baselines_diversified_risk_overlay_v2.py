from __future__ import annotations

from decimal import Decimal

from aegis.strategies.baselines import Candidate, DiversifiedRiskOverlayStrategyV2

STRATEGY = DiversifiedRiskOverlayStrategyV2()


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


def test_a_candidate_with_no_technical_data_at_all_is_included() -> None:
    assert len(STRATEGY.rank_candidates([_candidate()])) == 1


def test_being_far_below_its_own_high_no_longer_excludes_a_candidate() -> None:
    """The actual fix over V1: a stock deep off its real 252-day high --
    which V1 hard-excluded, destroying most of the return -- must stay in."""
    candidate = _candidate(close=Decimal(70), high_252=Decimal(130))  # ~46% off high
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_real_net_loss_still_excludes_when_fundamentals_available() -> None:
    candidate = _candidate(fundamentals_available=True, profit_for_period=Decimal(-1))
    assert STRATEGY.rank_candidates([candidate]) == []


def test_excessive_leverage_still_excludes_non_financial_sector() -> None:
    candidate = _candidate(
        sector="Consumer Durables", fundamentals_available=True, debt_equity_ratio=Decimal("3.0")
    )
    assert STRATEGY.rank_candidates([candidate]) == []


def test_excessive_leverage_does_not_exclude_financial_sector() -> None:
    candidate = _candidate(
        sector="Financial Services", fundamentals_available=True, debt_equity_ratio=Decimal("9.0")
    )
    assert len(STRATEGY.rank_candidates([candidate])) == 1


def test_missing_fundamentals_never_excludes() -> None:
    assert len(STRATEGY.rank_candidates([_candidate(fundamentals_available=False)])) == 1


def test_a_stock_at_its_real_high_gets_a_larger_weight_than_one_far_below_it() -> None:
    at_high = _candidate(instrument_id="AT_HIGH", close=Decimal(120), high_252=Decimal(120))
    off_high = _candidate(instrument_id="OFF_HIGH", close=Decimal(60), high_252=Decimal(120))
    ranked = STRATEGY.rank_candidates([off_high, at_high])
    weights = STRATEGY.propose_target_weights(ranked, maximum_position_count=8)
    assert weights["AT_HIGH"] > weights["OFF_HIGH"]


def test_a_stock_far_off_its_high_still_gets_a_real_nonzero_weight() -> None:
    """The actual point of switching from exclusion to weighting: this
    stock must never be zeroed out, only sized down."""
    at_high = _candidate(instrument_id="AT_HIGH", close=Decimal(120), high_252=Decimal(120))
    deep_off_high = _candidate(instrument_id="DEEP_OFF_HIGH", close=Decimal(30), high_252=Decimal(120))
    ranked = STRATEGY.rank_candidates([at_high, deep_off_high])
    weights = STRATEGY.propose_target_weights(ranked, maximum_position_count=8)
    assert weights["DEEP_OFF_HIGH"] > 0


def test_weights_still_sum_to_80_percent_of_nav() -> None:
    candidates = [
        _candidate(instrument_id="A", close=Decimal(100), high_252=Decimal(100)),
        _candidate(instrument_id="B", close=Decimal(50), high_252=Decimal(100)),
        _candidate(instrument_id="C", close=Decimal(80), high_252=Decimal(200)),
    ]
    ranked = STRATEGY.rank_candidates(candidates)
    weights = STRATEGY.propose_target_weights(ranked, maximum_position_count=8)
    assert sum(weights.values()) == Decimal("0.80")


def test_missing_high_252_gets_neutral_weight_equal_to_an_at_high_candidate() -> None:
    no_data = _candidate(instrument_id="NO_DATA", high_252=None)
    at_high = _candidate(instrument_id="AT_HIGH", close=Decimal(120), high_252=Decimal(120))
    ranked = STRATEGY.rank_candidates([no_data, at_high])
    weights = STRATEGY.propose_target_weights(ranked, maximum_position_count=8)
    assert weights["NO_DATA"] == weights["AT_HIGH"]


def test_weights_are_uncapped_regardless_of_maximum_position_count() -> None:
    candidates = [_candidate(instrument_id=f"I{i}") for i in range(20)]
    ranked = STRATEGY.rank_candidates(candidates)
    weights = STRATEGY.propose_target_weights(ranked, maximum_position_count=8)
    assert len(weights) == 20


def test_propose_target_weights_is_empty_when_nothing_survives() -> None:
    assert STRATEGY.propose_target_weights([], maximum_position_count=8) == {}


def test_strategy_has_no_invalidation_price_method() -> None:
    assert not hasattr(STRATEGY, "invalidation_price")


def test_get_strategy_metadata_is_honest_about_being_research_only() -> None:
    metadata = STRATEGY.get_strategy_metadata()
    assert metadata["strategy_name"] == "DiversifiedRiskOverlayStrategyV2"
    assert metadata["classification"] == "RESEARCH_ONLY"
    assert metadata["not_recommendation"] is True
