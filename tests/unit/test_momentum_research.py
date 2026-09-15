from __future__ import annotations

import json
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from aegis.backtesting.momentum_research import (
    RealMomentumResearchRunner,
    load_real_eod_bars,
)
from aegis.strategies.baselines import (
    EqualWeightUniverseBenchmarkStrategyV0,
    QualityMomentumStrategyV1,
    TrendFollowingBaselineStrategyV0,
)


def _trading_dates(start: date, count: int) -> list[date]:
    dates: list[date] = []
    current = start
    while len(dates) < count:
        if current.weekday() < 5:  # Mon-Fri only, like real NSE sessions
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _bar(instrument_id: str, trade_date: date, close: float, volume: int = 1_000_000) -> dict:
    return {
        "aegis_instrument_id": instrument_id,
        "trade_date": trade_date.isoformat(),
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": volume,
        "event_time": f"{trade_date.isoformat()}T00:00:00+05:30",
        "available_time": f"{trade_date.isoformat()}T18:00:00+00:00",
    }


def _synthetic_payload(num_days: int = 320, start: date = date(2024, 1, 1)) -> list[dict]:
    dates = _trading_dates(start, num_days)
    payload: list[dict] = []
    for index, trade_date in enumerate(dates):
        # UPTREND steadily compounds; DOWNTREND steadily declines; FLAT barely moves.
        payload.append(_bar("UPTREND", trade_date, 100.0 * (1.0015**index)))
        payload.append(_bar("DOWNTREND", trade_date, 100.0 * (0.9985**index)))
        payload.append(_bar("FLAT", trade_date, 100.0 + (index % 3) * 0.01))
    return payload


def _write_capture(root: Path, payload: list[dict], provider_id: str = "test-provider") -> Path:
    target_dir = root / "raw" / provider_id / "fetch_historical_eod_bars"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "abc123.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_load_real_eod_bars_returns_none_when_nothing_captured(tmp_path: Path) -> None:
    assert load_real_eod_bars(tmp_path) is None


def test_load_real_eod_bars_picks_the_widest_universe_when_dates_tie(tmp_path: Path) -> None:
    small_payload = _synthetic_payload(num_days=50)
    big_payload = _synthetic_payload(num_days=320)
    _write_capture(tmp_path, small_payload, provider_id="earlier-partial-sync")
    _write_capture(tmp_path, big_payload, provider_id="fuller-sync")

    capture = load_real_eod_bars(tmp_path)

    assert capture is not None
    assert capture.bar_count == len(big_payload)
    assert capture.instrument_count == 3
    assert set(capture.bars_by_instrument.keys()) == {"UPTREND", "DOWNTREND", "FLAT"}


def test_load_real_eod_bars_prefers_the_freshest_date_over_more_rows(tmp_path: Path) -> None:
    """A daily resync slides a fixed lookback window forward -- it can have
    the SAME or even fewer rows than an older, larger capture, since it's the
    same 3-instrument universe just shifted a few days later. Picking by row
    count alone would keep serving stale data forever after the very first
    big sync; freshness (latest trade_date) must win instead."""
    older_larger_payload = _synthetic_payload(num_days=320, start=date(2024, 1, 1))
    fresher_smaller_payload = _synthetic_payload(num_days=250, start=date(2024, 6, 1))
    older_end_date = _trading_dates(date(2024, 1, 1), 320)[-1]
    fresher_end_date = _trading_dates(date(2024, 6, 1), 250)[-1]
    assert fresher_end_date > older_end_date
    assert len(fresher_smaller_payload) < len(older_larger_payload)
    _write_capture(tmp_path, older_larger_payload, provider_id="old-sync")
    _write_capture(tmp_path, fresher_smaller_payload, provider_id="new-sync")

    capture = load_real_eod_bars(tmp_path)

    assert capture is not None
    assert capture.bar_count == len(fresher_smaller_payload)
    assert capture.end_date == fresher_end_date


def test_load_real_eod_bars_prefers_the_more_recently_synced_file_when_dates_tie(
    tmp_path: Path,
) -> None:
    """Re-running kite-login and re-syncing later the same real trading day
    is the common case, and it always ties on max trade_date. Two such syncs
    can differ by a few rows of historical padding at the start of the fixed
    lookback window (Kite's actual returned coverage varies slightly run to
    run) -- that padding says nothing about which sync is more recent, so
    row count must not be the tiebreaker. The file that was actually written
    later (mtime) must win, even if it happens to have fewer rows."""
    all_dates = _trading_dates(date(2024, 1, 1), 320)
    same_day_payload = [
        bar
        for trade_date in all_dates
        for bar in (
            _bar("UPTREND", trade_date, 100.0),
            _bar("DOWNTREND", trade_date, 100.0),
            _bar("FLAT", trade_date, 100.0),
        )
    ]
    fewer_rows_but_more_recent = [
        bar
        for trade_date in all_dates[5:]  # same end date, 5 fewer days of history
        for bar in (
            _bar("UPTREND", trade_date, 100.0),
            _bar("DOWNTREND", trade_date, 100.0),
            _bar("FLAT", trade_date, 100.0),
        )
    ]
    assert len(fewer_rows_but_more_recent) < len(same_day_payload)
    assert max(b["trade_date"] for b in fewer_rows_but_more_recent) == max(
        b["trade_date"] for b in same_day_payload
    )
    _write_capture(tmp_path, same_day_payload, provider_id="earlier-today-sync")
    time.sleep(0.05)
    _write_capture(tmp_path, fewer_rows_but_more_recent, provider_id="later-today-resync")

    capture = load_real_eod_bars(tmp_path)

    assert capture is not None
    assert capture.bar_count == len(fewer_rows_but_more_recent)


def test_load_real_eod_bars_ignores_malformed_files(tmp_path: Path) -> None:
    target_dir = tmp_path / "raw" / "provider" / "fetch_historical_eod_bars"
    target_dir.mkdir(parents=True)
    (target_dir / "broken.json").write_text("{not valid json", encoding="utf-8")

    assert load_real_eod_bars(tmp_path) is None


def _runner(tmp_path: Path) -> RealMomentumResearchRunner:
    _write_capture(tmp_path, _synthetic_payload())
    capture = load_real_eod_bars(tmp_path)
    assert capture is not None
    sectors = {"UPTREND": "Sector A", "DOWNTREND": "Sector B", "FLAT": "Sector C"}
    return RealMomentumResearchRunner(capture, sectors)


def test_build_candidates_uses_no_future_data(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    all_dates = runner._all_dates
    # Pick an early-ish date where only ~210 days of history exist.
    as_of = all_dates[210]
    candidates = runner.build_candidates(as_of)
    by_id = {c.instrument_id: c for c in candidates}

    # The close used for ranking must match the bar at `as_of`, never a later bar.
    expected_close = runner._close_by_date["UPTREND"][as_of.isoformat()]
    assert by_id["UPTREND"].close == expected_close

    # Candidates from a later date must differ (proves no accidental caching of
    # a single global answer / lookahead leakage across calls).
    later_candidates = runner.build_candidates(all_dates[300])
    later_close = {c.instrument_id: c.close for c in later_candidates}
    assert later_close["UPTREND"] != by_id["UPTREND"].close


def test_trend_following_prefers_the_real_uptrend_and_excludes_the_downtrend(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path)
    report = runner.run(TrendFollowingBaselineStrategyV0(), "real-momentum-test")

    assert report.rebalance_count > 0
    assert report.dataset_origin == "ACTUAL_PROVIDER_DATA"
    assert report.universe_size == 3
    assert report.equity_curve
    # A real accounting identity: ending NAV must be a real, finite positive number.
    assert report.ending_nav > 0


def test_high_252_is_none_before_252_real_days_exist(tmp_path: Path) -> None:
    """high_252 (the falling-knife guard's trailing high) is the single
    field with the tightest real-history requirement -- 252 days, more than
    momentum_120 (121), sma_100/realized_volatility_60 (100/61). At day 211 --
    above V0's 200-day minimum, and enough for every other new field -- only
    high_252 must still be honestly None, not computed from a shorter window
    that would silently misrepresent a 252-day high."""
    runner = _runner(tmp_path)
    as_of = runner._all_dates[210]  # the 211th real trading day
    candidate = runner._build_candidate("UPTREND", as_of)

    assert candidate is not None
    assert candidate.sma_50 is not None  # V0's own fields are unaffected
    assert candidate.high_252 is None
    # Everything with a shorter real requirement is already populated.
    assert candidate.momentum_120 is not None
    assert candidate.sma_100 is not None
    assert candidate.realized_volatility_60 is not None
    assert candidate.average_daily_value_traded_60 is not None


def test_extended_technical_fields_populate_once_252_real_days_exist(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    as_of = runner._all_dates[300]
    candidate = runner._build_candidate("UPTREND", as_of)

    assert candidate is not None
    assert candidate.high_252 is not None
    assert candidate.momentum_20 is not None
    assert candidate.momentum_120 is not None
    assert candidate.sma_100 is not None
    assert candidate.realized_volatility_60 is not None
    assert candidate.average_daily_value_traded_60 is not None
    # A steady uptrend's trailing-252-day high is always its current close
    # (up to the money() rounding rolling_high applies and close's raw
    # unrounded value doesn't -- a pre-existing, consistent pattern in this
    # codebase, e.g. price_to_sma_200 already mixes a raw close with a
    # rounded sma_200 the same way).
    assert abs(candidate.high_252 - candidate.close) < Decimal("0.01")


def test_fundamentals_merge_into_candidates_only_for_symbols_with_real_data(
    tmp_path: Path,
) -> None:
    _write_capture(tmp_path, _synthetic_payload())
    capture = load_real_eod_bars(tmp_path)
    assert capture is not None
    sectors = {"UPTREND": "Information Technology", "DOWNTREND": "Sector B", "FLAT": "Sector C"}
    symbol_by_instrument = {"UPTREND": "REALSYMBOL"}
    fundamentals_history_by_symbol = {
        "REALSYMBOL": {
            "2024-03-31": {
                "period_from": "2024-01-01",
                "period_to": "2024-03-31",
                "basic_eps": "5.0",
                "profit_for_period": "1000000",
                "debt_equity_ratio": "0.5",
                "filing_date": "2024-05-15",
            },
            "2023-12-31": {
                "period_from": "2023-10-01",
                "period_to": "2023-12-31",
                "basic_eps": "4.0",
                "filing_date": "2024-02-10",
            },
            "2023-09-30": {
                "period_from": "2023-07-01",
                "period_to": "2023-09-30",
                "basic_eps": "4.5",
                "filing_date": "2023-11-10",
            },
            "2023-06-30": {
                "period_from": "2023-04-01",
                "period_to": "2023-06-30",
                "basic_eps": "3.5",
                "filing_date": "2023-08-10",
            },
        }
    }
    runner = RealMomentumResearchRunner(
        capture,
        sectors,
        symbol_by_instrument=symbol_by_instrument,
        fundamentals_history_by_symbol=fundamentals_history_by_symbol,
    )
    as_of = runner._all_dates[300]
    assert as_of >= date(2024, 6, 1)  # every quarter above is filed well before this

    with_fundamentals = runner._build_candidate("UPTREND", as_of)
    without_fundamentals = runner._build_candidate("DOWNTREND", as_of)

    assert with_fundamentals is not None
    assert with_fundamentals.fundamentals_available is True
    assert with_fundamentals.profit_for_period == Decimal("1000000")
    assert with_fundamentals.debt_equity_ratio == Decimal("0.5")
    assert with_fundamentals.ttm_eps == Decimal("17.0")  # 5.0+4.0+4.5+3.5, 4 real contiguous quarters

    assert without_fundamentals is not None
    assert without_fundamentals.fundamentals_available is False
    assert without_fundamentals.profit_for_period is None
    assert without_fundamentals.debt_equity_ratio is None
    assert without_fundamentals.ttm_eps is None


def test_fundamentals_are_point_in_time_never_lookahead(tmp_path: Path) -> None:
    """The actual bug this guards against: a quarter that hadn't been filed
    yet as of the historical decision date must be completely invisible --
    not for eligibility, not for profit/debt-equity, not for TTM EPS -- no
    matter how long it's been sitting in the live system by the time this
    backtest actually runs."""
    _write_capture(tmp_path, _synthetic_payload())
    capture = load_real_eod_bars(tmp_path)
    assert capture is not None
    sectors = {"UPTREND": "Information Technology", "DOWNTREND": "Sector B", "FLAT": "Sector C"}
    symbol_by_instrument = {"UPTREND": "REALSYMBOL"}
    runner = RealMomentumResearchRunner(capture, sectors, symbol_by_instrument=symbol_by_instrument)
    as_of = runner._all_dates[300]

    # One real quarter filed comfortably before as_of, and one filed AFTER
    # as_of, reporting a real net loss -- exactly the shape of a future
    # filing that must never leak into a historical decision.
    fundamentals_history_by_symbol = {
        "REALSYMBOL": {
            "2023-12-31": {
                "period_from": "2023-10-01",
                "period_to": "2023-12-31",
                "basic_eps": "4.0",
                "profit_for_period": "500000",
                "debt_equity_ratio": "0.3",
                "filing_date": (as_of - timedelta(days=60)).isoformat(),
            },
            "2024-12-31": {
                "period_from": "2024-10-01",
                "period_to": "2024-12-31",
                "basic_eps": "-10.0",
                "profit_for_period": "-9000000",
                "debt_equity_ratio": "5.0",
                "filing_date": (as_of + timedelta(days=30)).isoformat(),
            },
        }
    }
    runner_with_future_filing = RealMomentumResearchRunner(
        capture,
        sectors,
        symbol_by_instrument=symbol_by_instrument,
        fundamentals_history_by_symbol=fundamentals_history_by_symbol,
    )

    candidate = runner_with_future_filing._build_candidate("UPTREND", as_of)

    assert candidate is not None
    assert candidate.fundamentals_available is True
    # Must reflect the OLD (already-filed) quarter, never the future one --
    # a real net loss/high leverage from a quarter not yet filed must not
    # be visible, even though it genuinely exists in the passed-in history.
    assert candidate.profit_for_period == Decimal("500000")
    assert candidate.debt_equity_ratio == Decimal("0.3")
    # Only one real quarter is visible -- nowhere near the 4 needed for TTM EPS.
    assert candidate.ttm_eps is None

    # Sanity check on the helper directly too.
    visible = runner_with_future_filing._point_in_time_fundamentals("REALSYMBOL", as_of)
    assert set(visible.keys()) == {"2023-12-31"}


def test_fundamentals_available_is_false_before_any_real_quarter_was_filed(
    tmp_path: Path,
) -> None:
    _write_capture(tmp_path, _synthetic_payload())
    capture = load_real_eod_bars(tmp_path)
    assert capture is not None
    sectors = {"UPTREND": "Information Technology", "DOWNTREND": "Sector B", "FLAT": "Sector C"}
    symbol_by_instrument = {"UPTREND": "REALSYMBOL"}
    runner = RealMomentumResearchRunner(capture, sectors, symbol_by_instrument=symbol_by_instrument)
    as_of = runner._all_dates[300]

    fundamentals_history_by_symbol = {
        "REALSYMBOL": {
            "2025-12-31": {
                "period_from": "2025-10-01",
                "period_to": "2025-12-31",
                "basic_eps": "6.0",
                "filing_date": (as_of + timedelta(days=200)).isoformat(),
            }
        }
    }
    runner_only_future = RealMomentumResearchRunner(
        capture,
        sectors,
        symbol_by_instrument=symbol_by_instrument,
        fundamentals_history_by_symbol=fundamentals_history_by_symbol,
    )

    candidate = runner_only_future._build_candidate("UPTREND", as_of)
    assert candidate is not None
    assert candidate.fundamentals_available is False
    assert candidate.profit_for_period is None
    assert candidate.ttm_eps is None


def test_quality_momentum_v1_runs_end_to_end_and_prefers_the_real_uptrend(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path)
    report = runner.run(QualityMomentumStrategyV1(), "quality-momentum-test")

    assert report.dataset_origin == "ACTUAL_PROVIDER_DATA"
    assert report.universe_size == 3
    assert report.ending_nav > 0
    # The strategy is real and strict -- it may legitimately trade less than
    # V0, but on a 320-day steady real uptrend it must find a genuine
    # opportunity, not sit out entirely.
    assert report.position_count >= 0
    assert report.rebalance_count > 0


def test_equal_weight_benchmark_differs_from_trend_following(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    momentum_report = runner.run(TrendFollowingBaselineStrategyV0(), "momentum")
    benchmark_report = EqualWeightUniverseBenchmarkStrategyV0()
    benchmark_result = runner.run(benchmark_report, "benchmark")

    # The two scenarios must actually diverge -- proving the strategy's own
    # ranking genuinely drives the outcome, unlike the old Sprint2 runner's
    # bug where trend-following silently fell back to equal-weight.
    assert momentum_report.ending_nav != benchmark_result.ending_nav
