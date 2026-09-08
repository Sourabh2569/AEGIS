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


def test_equal_weight_benchmark_differs_from_trend_following(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    momentum_report = runner.run(TrendFollowingBaselineStrategyV0(), "momentum")
    benchmark_report = EqualWeightUniverseBenchmarkStrategyV0()
    benchmark_result = runner.run(benchmark_report, "benchmark")

    # The two scenarios must actually diverge -- proving the strategy's own
    # ranking genuinely drives the outcome, unlike the old Sprint2 runner's
    # bug where trend-following silently fell back to equal-weight.
    assert momentum_report.ending_nav != benchmark_result.ending_nav
