from __future__ import annotations

from pathlib import Path

from aegis.data_ingestion.fundamentals_store import SqliteFundamentalsStore


def test_load_history_is_empty_for_a_fresh_store(tmp_path: Path) -> None:
    store = SqliteFundamentalsStore(tmp_path / "fundamentals.sqlite")
    assert store.load_history("STANDALONE") == {}


def test_upserted_quarter_round_trips_through_the_same_store(tmp_path: Path) -> None:
    store = SqliteFundamentalsStore(tmp_path / "fundamentals.sqlite")
    record = {"symbol": "RELIANCE", "period_from": "2024-10-01", "period_to": "2024-12-31"}
    store.upsert("RELIANCE", "STANDALONE", "2024-12-31", record)

    assert store.load_history("STANDALONE") == {"RELIANCE": {"2024-12-31": record}}


def test_quarters_survive_a_real_process_restart(tmp_path: Path) -> None:
    """The actual point of this store: a new SqliteFundamentalsStore
    instance -- standing in for the API process restarting -- pointed at
    the same file must see everything a prior instance wrote."""
    db_path = tmp_path / "fundamentals.sqlite"
    first_process = SqliteFundamentalsStore(db_path)
    first_process.upsert(
        "RELIANCE", "STANDALONE", "2024-12-31", {"symbol": "RELIANCE", "basic_eps": "6.44"}
    )
    first_process.upsert(
        "TCS", "STANDALONE", "2024-12-31", {"symbol": "TCS", "basic_eps": "32.71"}
    )

    second_process = SqliteFundamentalsStore(db_path)
    history = second_process.load_history("STANDALONE")

    assert history["RELIANCE"]["2024-12-31"]["basic_eps"] == "6.44"
    assert history["TCS"]["2024-12-31"]["basic_eps"] == "32.71"


def test_re_upserting_the_same_quarter_replaces_it_not_duplicates_it(tmp_path: Path) -> None:
    store = SqliteFundamentalsStore(tmp_path / "fundamentals.sqlite")
    store.upsert("RELIANCE", "STANDALONE", "2024-12-31", {"basic_eps": "6.44"})
    store.upsert("RELIANCE", "STANDALONE", "2024-12-31", {"basic_eps": "6.50"})

    history = store.load_history("STANDALONE")
    assert history == {"RELIANCE": {"2024-12-31": {"basic_eps": "6.50"}}}


def test_delete_removes_only_the_named_quarter(tmp_path: Path) -> None:
    store = SqliteFundamentalsStore(tmp_path / "fundamentals.sqlite")
    store.upsert("RELIANCE", "STANDALONE", "2024-09-30", {"basic_eps": "5.00"})
    store.upsert("RELIANCE", "STANDALONE", "2024-12-31", {"basic_eps": "6.44"})

    store.delete("RELIANCE", "STANDALONE", "2024-12-31")

    history = store.load_history("STANDALONE")
    assert history == {"RELIANCE": {"2024-09-30": {"basic_eps": "5.00"}}}


def test_delete_of_a_never_stored_quarter_is_a_harmless_no_op(tmp_path: Path) -> None:
    store = SqliteFundamentalsStore(tmp_path / "fundamentals.sqlite")
    store.delete("RELIANCE", "STANDALONE", "2024-12-31")  # must not raise
    assert store.load_history("STANDALONE") == {}


def test_standalone_and_consolidated_never_mix_even_for_the_same_symbol_and_period(
    tmp_path: Path,
) -> None:
    store = SqliteFundamentalsStore(tmp_path / "fundamentals.sqlite")
    store.upsert(
        "RELIANCE", "STANDALONE", "2024-12-31", {"nature": "STANDALONE", "basic_eps": "6.44"}
    )
    store.upsert(
        "RELIANCE", "CONSOLIDATED", "2024-12-31", {"nature": "CONSOLIDATED", "basic_eps": "13.10"}
    )

    assert store.load_history("STANDALONE")["RELIANCE"]["2024-12-31"]["basic_eps"] == "6.44"
    assert store.load_history("CONSOLIDATED")["RELIANCE"]["2024-12-31"]["basic_eps"] == "13.10"
