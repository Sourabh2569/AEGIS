from __future__ import annotations

from pathlib import Path

from aegis.data_ingestion.fundamentals_store import FundamentalsRawArchive, SqliteFundamentalsStore


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


def test_raw_archive_has_and_load_are_honest_when_nothing_is_archived(tmp_path: Path) -> None:
    archive = FundamentalsRawArchive(tmp_path / "archive")
    assert archive.has(nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31") is False
    assert archive.load(nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31") is None


def test_raw_archive_saved_file_round_trips_exact_bytes(tmp_path: Path) -> None:
    archive = FundamentalsRawArchive(tmp_path / "archive")
    content = b"<xbrli:xbrl>real filing bytes</xbrli:xbrl>"
    archive.save_accepted(nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31", content=content)

    assert archive.has(nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31") is True
    assert archive.load(nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31") == content


def test_raw_archive_survives_a_real_process_restart(tmp_path: Path) -> None:
    """The actual point of this archive: a new FundamentalsRawArchive
    instance -- standing in for the API process restarting -- pointed at
    the same directory must see everything a prior instance wrote."""
    archive_root = tmp_path / "archive"
    content = b"<xbrli:xbrl>real filing bytes</xbrli:xbrl>"
    first_process = FundamentalsRawArchive(archive_root)
    first_process.save_accepted(
        nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31", content=content
    )

    second_process = FundamentalsRawArchive(archive_root)
    assert second_process.load(nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31") == content


def test_raw_archive_two_different_quarters_never_collide(tmp_path: Path) -> None:
    archive = FundamentalsRawArchive(tmp_path / "archive")
    archive.save_accepted(nature="STANDALONE", symbol="RELIANCE", period_to="2024-09-30", content=b"q2")
    archive.save_accepted(nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31", content=b"q3")

    assert archive.load(nature="STANDALONE", symbol="RELIANCE", period_to="2024-09-30") == b"q2"
    assert archive.load(nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31") == b"q3"


def test_raw_archive_re_upload_of_the_same_quarter_replaces_it_a_correction(tmp_path: Path) -> None:
    archive = FundamentalsRawArchive(tmp_path / "archive")
    archive.save_accepted(nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31", content=b"first")
    archive.save_accepted(
        nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31", content=b"corrected"
    )

    assert archive.load(nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31") == b"corrected"


def test_raw_archive_standalone_and_consolidated_never_collide(tmp_path: Path) -> None:
    archive = FundamentalsRawArchive(tmp_path / "archive")
    archive.save_accepted(
        nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31", content=b"standalone bytes"
    )
    archive.save_accepted(
        nature="CONSOLIDATED", symbol="RELIANCE", period_to="2024-12-31", content=b"consolidated bytes"
    )

    assert archive.load(nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31") == b"standalone bytes"
    assert (
        archive.load(nature="CONSOLIDATED", symbol="RELIANCE", period_to="2024-12-31")
        == b"consolidated bytes"
    )


def test_raw_archive_rejected_upload_is_still_kept_not_discarded(tmp_path: Path) -> None:
    archive = FundamentalsRawArchive(tmp_path / "archive")
    content = b"not a real filing at all"
    path = archive.save_rejected(
        nature="STANDALONE", symbol="GARBAGE", uploaded_at="20260914-101500", content=content
    )

    assert path.exists()
    assert path.read_bytes() == content


def test_raw_archive_delete_removes_only_the_named_quarter(tmp_path: Path) -> None:
    archive = FundamentalsRawArchive(tmp_path / "archive")
    archive.save_accepted(nature="STANDALONE", symbol="RELIANCE", period_to="2024-09-30", content=b"q2")
    archive.save_accepted(nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31", content=b"q3")

    archive.delete(nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31")

    assert archive.has(nature="STANDALONE", symbol="RELIANCE", period_to="2024-09-30") is True
    assert archive.has(nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31") is False


def test_raw_archive_delete_of_a_never_archived_quarter_is_a_harmless_no_op(tmp_path: Path) -> None:
    archive = FundamentalsRawArchive(tmp_path / "archive")
    archive.delete(nature="STANDALONE", symbol="RELIANCE", period_to="2024-12-31")  # must not raise
