from __future__ import annotations

from pathlib import Path

from aegis.backtesting.momentum_report_store import SqliteMomentumReportStore


def test_load_all_is_empty_for_a_fresh_store(tmp_path: Path) -> None:
    store = SqliteMomentumReportStore(tmp_path / "reports.sqlite")
    assert store.load_all() == []


def test_appended_reports_round_trip_through_the_same_store(tmp_path: Path) -> None:
    store = SqliteMomentumReportStore(tmp_path / "reports.sqlite")
    report = {"strategy_name": "TrendFollowingBaselineStrategyV0", "total_return": "0.33"}
    store.append(report, created_at="2026-09-06T00:00:00+00:00")

    assert store.load_all() == [report]


def test_reports_survive_a_real_process_restart(tmp_path: Path) -> None:
    """The actual point of this store: a new SqliteMomentumReportStore
    instance -- standing in for the API process restarting -- pointed at
    the same file must see everything a prior instance wrote."""
    db_path = tmp_path / "reports.sqlite"
    first_process = SqliteMomentumReportStore(db_path)
    first_process.append(
        {"strategy_name": "TrendFollowingBaselineStrategyV0"},
        created_at="2026-09-06T00:00:00+00:00",
    )
    first_process.append(
        {"strategy_name": "EqualWeightUniverseBenchmarkStrategyV0"},
        created_at="2026-09-06T00:00:01+00:00",
    )

    second_process = SqliteMomentumReportStore(db_path)
    reports = second_process.load_all()

    assert [report["strategy_name"] for report in reports] == [
        "TrendFollowingBaselineStrategyV0",
        "EqualWeightUniverseBenchmarkStrategyV0",
    ]


def test_load_all_preserves_insertion_order_across_many_reports(tmp_path: Path) -> None:
    store = SqliteMomentumReportStore(tmp_path / "reports.sqlite")
    for index in range(5):
        store.append(
            {"scenario": f"run-{index}"}, created_at=f"2026-09-0{index + 1}T00:00:00+00:00"
        )

    assert [report["scenario"] for report in store.load_all()] == [f"run-{i}" for i in range(5)]
