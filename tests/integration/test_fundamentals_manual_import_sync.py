from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import aegis_api.main as app_main
from aegis_api.main import app
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "xbrl"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    # app_main.repo is a module-level singleton shared across the whole
    # pytest session (it also holds a real, permanent seed_dataset_version
    # other tests depend on -- a blanket .clear() would break those). Only
    # the *new* keys this test's own sync run adds are removed afterward, by
    # diffing against a snapshot taken before the test runs.
    before = {
        "dataset_versions": set(app_main.repo.dataset_versions),
        "dataset_origins": set(app_main.repo.dataset_origins),
        "raw_objects": set(app_main.repo.raw_objects),
        "ingestion_runs": set(app_main.repo.ingestion_runs),
    }
    app_main.repo.latest_fundamentals.clear()
    app_main.repo.fundamentals_history.clear()
    app_main.repo.latest_fundamentals_consolidated.clear()
    app_main.repo.fundamentals_history_consolidated.clear()
    monkeypatch.setattr(app_main, "fundamentals_manual_import_base_path", tmp_path / "standalone")
    monkeypatch.setattr(
        app_main,
        "fundamentals_manual_import_consolidated_base_path",
        tmp_path / "consolidated",
    )
    (tmp_path / "standalone").mkdir()
    (tmp_path / "consolidated").mkdir()
    yield TestClient(app)
    app_main.repo.latest_fundamentals.clear()
    app_main.repo.fundamentals_history.clear()
    app_main.repo.latest_fundamentals_consolidated.clear()
    app_main.repo.fundamentals_history_consolidated.clear()
    for attr, before_keys in before.items():
        mapping = getattr(app_main.repo, attr)
        for key in set(mapping) - before_keys:
            del mapping[key]


def test_sync_with_no_files_present_is_honest_and_empty(client: TestClient) -> None:
    response = client.post(
        "/api/v1/fundamentals-manual-import/sync", headers={"X-Aegis-Role": "DATA_STEWARD"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["run"]["records_accepted"] == 0


def test_sync_requires_a_real_role(client: TestClient) -> None:
    response = client.post("/api/v1/fundamentals-manual-import/sync")
    assert response.status_code in (401, 403)


def test_sync_real_downloaded_file_flows_through_to_the_existing_endpoint(
    client: TestClient, tmp_path: Path
) -> None:
    (tmp_path / "standalone" / "RELIANCE.xml").write_bytes(
        (FIXTURES_DIR / "reliance_q3_fy2025_standalone.xml").read_bytes()
    )

    sync_response = client.post(
        "/api/v1/fundamentals-manual-import/sync", headers={"X-Aegis-Role": "DATA_STEWARD"}
    )
    assert sync_response.status_code == 200
    run = sync_response.json()["run"]
    assert run["records_accepted"] == 1
    assert run["records_rejected"] == 0

    # The same, already-existing endpoint (used by the NSE pilot too) picks
    # this up automatically -- no separate read path needed. The reported
    # origin must honestly say APPROVED_FILE_IMPORT here, not
    # ACTUAL_PROVIDER_DATA -- this is exactly the real bug this feature's
    # verification caught: the endpoint used to hardcode the origin instead
    # of reporting what actually happened.
    read_response = client.get("/api/v1/instruments/RELIANCE/fundamentals")
    assert read_response.status_code == 200
    body = read_response.json()
    assert body["available"] is True
    assert body["dataset_origin"] == "APPROVED_FILE_IMPORT"
    assert body["revenue_from_operations"] == "1282600000000.00"

    # Real provenance: the exact DatasetVersion this run created is tagged
    # honestly as a human-approved file import, not an automated provider
    # fetch.
    dataset_version_id = run["validation_summary"]["dataset_version_id"]
    assert app_main.repo.dataset_origins[dataset_version_id] == "APPROVED_FILE_IMPORT"


def test_history_endpoint_is_honest_for_a_symbol_with_nothing_uploaded(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/fundamentals-manual-import/history/CIPLA")
    assert response.status_code == 200
    body = response.json()
    assert body["quarters"] == []
    assert body["ttm_eps"] is None


def test_history_endpoint_lists_a_real_uploaded_quarter(client: TestClient) -> None:
    client.post(
        "/api/v1/fundamentals-manual-import/upload",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
        data={"symbol": "RELIANCE"},
        files={
            "file": (
                "f.xml",
                (FIXTURES_DIR / "reliance_q3_fy2025_standalone.xml").read_bytes(),
                "text/xml",
            )
        },
    )
    response = client.get("/api/v1/fundamentals-manual-import/history/RELIANCE")
    assert response.status_code == 200
    body = response.json()
    assert body["quarters"] == [
        {"period_from": "2024-10-01", "period_to": "2024-12-31", "filing_date": "2025-01-16"}
    ]
    assert body["ttm_eps"] is None  # only 1 of 4 real quarters uploaded so far


def test_history_endpoint_reports_real_ttm_once_four_quarters_are_on_file(
    client: TestClient,
) -> None:
    for period_from, period_to, basic_eps in [
        ("2024-01-01", "2024-03-31", "5.00"),
        ("2024-04-01", "2024-06-30", "6.00"),
        ("2024-07-01", "2024-09-30", "7.00"),
        ("2024-10-01", "2024-12-31", "8.00"),
    ]:
        app_main.repo.fundamentals_history.setdefault("RELIANCE", {})[period_to] = {
            "symbol": "RELIANCE",
            "period_from": period_from,
            "period_to": period_to,
            "basic_eps": basic_eps,
        }
    response = client.get("/api/v1/fundamentals-manual-import/history/RELIANCE")
    assert response.status_code == 200
    body = response.json()
    assert len(body["quarters"]) == 4
    assert body["quarters"][0]["period_to"] == "2024-12-31"  # most recent first
    assert body["ttm_eps"] == "26.00"


def test_upload_endpoint_saves_the_file_and_ingests_it_in_one_call(
    client: TestClient, tmp_path: Path
) -> None:
    xml_bytes = (FIXTURES_DIR / "tcs_q3_fy2025_standalone.xml").read_bytes()

    response = client.post(
        "/api/v1/fundamentals-manual-import/upload",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
        data={"symbol": "tcs"},
        files={"file": ("whatever-nse-named-it.xml", xml_bytes, "text/xml")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "TCS"
    assert body["accepted"] is True
    assert body["skip_reason"] is None
    assert (tmp_path / "standalone" / "TCS.xml").read_bytes() == xml_bytes

    read_response = client.get("/api/v1/instruments/TCS/fundamentals")
    assert read_response.status_code == 200
    body = read_response.json()
    assert body["available"] is True
    assert body["dataset_origin"] == "APPROVED_FILE_IMPORT"


def test_upload_endpoint_reports_an_honest_skip_reason_for_a_bad_file(
    client: TestClient, tmp_path: Path
) -> None:
    # A real valid file must already be present alongside the bad upload --
    # an all-skipped directory produces the exact same empty payload/hash as
    # test_sync_with_no_files_present_is_honest_and_empty above, and the
    # shared object store's write-once dedup (keyed on provider+endpoint+
    # content-hash, see LocalObjectStore.put_raw_once) rejects a second
    # write of that identical empty snapshot.
    (tmp_path / "standalone" / "WIPRO.xml").write_bytes(
        (FIXTURES_DIR / "wipro_q3_fy2025_standalone.xml").read_bytes()
    )

    response = client.post(
        "/api/v1/fundamentals-manual-import/upload",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
        data={"symbol": "GARBAGE"},
        files={"file": ("garbage.xml", b"not xml at all", "text/xml")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is False
    assert body["skip_reason"] is not None


def test_upload_endpoint_requires_a_real_role(client: TestClient) -> None:
    response = client.post(
        "/api/v1/fundamentals-manual-import/upload",
        data={"symbol": "TCS"},
        files={"file": ("f.xml", b"<x/>", "text/xml")},
    )
    assert response.status_code in (401, 403)


def test_uploading_the_identical_file_twice_does_not_crash(client: TestClient) -> None:
    """Real bug found via live use: LocalObjectStore's raw layer is
    write-once and content-addressed by payload hash (see
    test_missing_object_storage_fails_safely), so ingesting the exact same
    file twice used to raise an unhandled FileExistsError -- a raw 500 with
    no CORS headers, which browsers confusingly report as a CORS failure.
    ProviderIngestionService._put_layer_or_reuse now treats that collision
    as "nothing changed," not a crash."""
    xml_bytes = (FIXTURES_DIR / "reliance_q3_fy2025_standalone.xml").read_bytes()

    first = client.post(
        "/api/v1/fundamentals-manual-import/upload",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
        data={"symbol": "RELIANCE"},
        files={"file": ("f.xml", xml_bytes, "text/xml")},
    )
    assert first.status_code == 200
    assert first.json()["accepted"] is True

    second = client.post(
        "/api/v1/fundamentals-manual-import/upload",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
        data={"symbol": "RELIANCE"},
        files={"file": ("f.xml", xml_bytes, "text/xml")},
    )
    assert second.status_code == 200
    assert second.json()["accepted"] is True

    read_response = client.get("/api/v1/instruments/RELIANCE/fundamentals")
    assert read_response.status_code == 200
    assert read_response.json()["available"] is True


def test_upload_endpoint_rejects_a_malformed_symbol(client: TestClient) -> None:
    response = client.post(
        "/api/v1/fundamentals-manual-import/upload",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
        data={"symbol": "not a symbol!"},
        files={"file": ("f.xml", b"<x/>", "text/xml")},
    )
    assert response.status_code == 422


def test_delete_quarter_endpoint_requires_a_real_role(client: TestClient) -> None:
    response = client.delete("/api/v1/fundamentals-manual-import/history/RELIANCE/2024-12-31")
    assert response.status_code in (401, 403)


def test_delete_quarter_endpoint_is_honest_about_a_quarter_that_was_never_uploaded(
    client: TestClient,
) -> None:
    response = client.delete(
        "/api/v1/fundamentals-manual-import/history/RELIANCE/2024-12-31",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
    )
    assert response.status_code == 404


def test_delete_quarter_removes_a_mistaken_upload(client: TestClient) -> None:
    client.post(
        "/api/v1/fundamentals-manual-import/upload",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
        data={"symbol": "RELIANCE"},
        files={
            "file": (
                "f.xml",
                (FIXTURES_DIR / "reliance_q3_fy2025_standalone.xml").read_bytes(),
                "text/xml",
            )
        },
    )
    delete_response = client.delete(
        "/api/v1/fundamentals-manual-import/history/RELIANCE/2024-12-31",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
    )
    assert delete_response.status_code == 200
    body = delete_response.json()
    assert body["deleted_period_to"] == "2024-12-31"
    assert body["remaining_quarters"] == []

    # Both the history and the "latest" convenience pointer must honestly
    # reflect that nothing real is on file any more for this symbol -- not
    # a stale echo of the deleted upload.
    history_response = client.get("/api/v1/fundamentals-manual-import/history/RELIANCE")
    assert history_response.json()["quarters"] == []
    fundamentals_response = client.get("/api/v1/instruments/RELIANCE/fundamentals")
    assert fundamentals_response.json()["available"] is False


def test_delete_quarter_falls_back_to_the_next_most_recent_remaining_quarter(
    client: TestClient,
) -> None:
    """Deleting the mistakenly-uploaded *latest* quarter must not leave
    latest_fundamentals pointing at stale/deleted data -- it should fall
    back to whichever real quarter is now genuinely the most recent."""
    for period_from, period_to, basic_eps in [
        ("2024-07-01", "2024-09-30", "7.00"),
        ("2024-10-01", "2024-12-31", "8.00"),
    ]:
        app_main.repo.fundamentals_history.setdefault("RELIANCE", {})[period_to] = {
            "symbol": "RELIANCE",
            "period_from": period_from,
            "period_to": period_to,
            "basic_eps": basic_eps,
        }
        app_main.repo.latest_fundamentals["RELIANCE"] = app_main.repo.fundamentals_history[
            "RELIANCE"
        ][period_to]

    response = client.delete(
        "/api/v1/fundamentals-manual-import/history/RELIANCE/2024-12-31",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
    )
    assert response.status_code == 200
    assert response.json()["remaining_quarters"] == ["2024-09-30"]
    assert app_main.repo.latest_fundamentals["RELIANCE"]["period_to"] == "2024-09-30"


# A real RELIANCE filing that turned out to be genuinely Consolidated (found
# via live use -- it was originally rejected as "not Standalone", which is
# exactly correct behavior; it's real, valid data for the *Consolidated*
# path this section exercises).
CONSOLIDATED_FIXTURE = "reliance_q1_fy2027_consolidated_sebi_capmkt_taxonomy.xml"


def test_upload_with_nature_standalone_rejects_a_real_consolidated_file(
    client: TestClient,
) -> None:
    """Default nature is "standalone" -- a genuinely Consolidated file must
    still be rejected there, exactly as before Consolidated support
    existed at all."""
    response = client.post(
        "/api/v1/fundamentals-manual-import/upload",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
        data={"symbol": "RELIANCE"},
        files={
            "file": ("f.xml", (FIXTURES_DIR / CONSOLIDATED_FIXTURE).read_bytes(), "text/xml")
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is False
    assert "not Standalone" in body["skip_reason"]


def test_upload_with_nature_consolidated_accepts_the_same_real_file(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/fundamentals-manual-import/upload",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
        data={"symbol": "RELIANCE", "nature": "consolidated"},
        files={
            "file": ("f.xml", (FIXTURES_DIR / CONSOLIDATED_FIXTURE).read_bytes(), "text/xml")
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["nature"] == "Consolidated"

    # Real, entirely separate from Standalone -- the main fundamentals
    # endpoint's top-level fields must stay untouched (nothing real was
    # ever uploaded there in this test), while the nested "consolidated"
    # block reflects the real upload.
    fundamentals_response = client.get("/api/v1/instruments/RELIANCE/fundamentals")
    body = fundamentals_response.json()
    assert body["available"] is False
    assert body["consolidated"]["available"] is True
    assert body["consolidated"]["revenue_from_operations"] == "3118500000000"
    assert body["consolidated"]["basic_eps"] == "15.48"


def test_history_endpoint_keeps_standalone_and_consolidated_entirely_separate(
    client: TestClient,
) -> None:
    client.post(
        "/api/v1/fundamentals-manual-import/upload",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
        data={"symbol": "RELIANCE", "nature": "consolidated"},
        files={
            "file": ("f.xml", (FIXTURES_DIR / CONSOLIDATED_FIXTURE).read_bytes(), "text/xml")
        },
    )

    standalone_history = client.get(
        "/api/v1/fundamentals-manual-import/history/RELIANCE"
    ).json()
    assert standalone_history["quarters"] == []

    consolidated_history = client.get(
        "/api/v1/fundamentals-manual-import/history/RELIANCE?nature=consolidated"
    ).json()
    assert len(consolidated_history["quarters"]) == 1
    assert consolidated_history["quarters"][0]["period_to"] == "2026-06-30"


def test_delete_consolidated_quarter_does_not_touch_standalone(client: TestClient) -> None:
    client.post(
        "/api/v1/fundamentals-manual-import/upload",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
        data={"symbol": "RELIANCE"},
        files={
            "file": (
                "f.xml",
                (FIXTURES_DIR / "reliance_q3_fy2025_standalone.xml").read_bytes(),
                "text/xml",
            )
        },
    )
    client.post(
        "/api/v1/fundamentals-manual-import/upload",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
        data={"symbol": "RELIANCE", "nature": "consolidated"},
        files={
            "file": ("f.xml", (FIXTURES_DIR / CONSOLIDATED_FIXTURE).read_bytes(), "text/xml")
        },
    )

    delete_response = client.delete(
        "/api/v1/fundamentals-manual-import/history/RELIANCE/2026-06-30?nature=consolidated",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
    )
    assert delete_response.status_code == 200

    body = client.get("/api/v1/instruments/RELIANCE/fundamentals").json()
    assert body["available"] is True  # Standalone untouched
    assert body["period_to"] == "2024-12-31"
    assert body["consolidated"]["available"] is False  # Consolidated now empty
