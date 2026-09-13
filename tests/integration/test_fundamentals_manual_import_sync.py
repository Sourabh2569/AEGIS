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
    monkeypatch.setattr(app_main, "fundamentals_manual_import_base_path", tmp_path)
    yield TestClient(app)
    app_main.repo.latest_fundamentals.clear()
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
    (tmp_path / "RELIANCE.xml").write_bytes(
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
    assert (tmp_path / "TCS.xml").read_bytes() == xml_bytes

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
    (tmp_path / "WIPRO.xml").write_bytes(
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


def test_upload_endpoint_rejects_a_malformed_symbol(client: TestClient) -> None:
    response = client.post(
        "/api/v1/fundamentals-manual-import/upload",
        headers={"X-Aegis-Role": "DATA_STEWARD"},
        data={"symbol": "not a symbol!"},
        files={"file": ("f.xml", b"<x/>", "text/xml")},
    )
    assert response.status_code == 422
