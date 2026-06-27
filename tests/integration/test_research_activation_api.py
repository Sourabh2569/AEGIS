from __future__ import annotations

from fastapi.testclient import TestClient

from aegis_api.main import app


def test_research_activation_status_is_fail_closed_for_seed_fixture() -> None:
    client = TestClient(app)

    status = client.get("/api/v1/research-activation/status").json()
    eligible = client.get("/api/v1/research-activation/eligible-datasets").json()

    assert status["status"] == "PROVIDER_SETUP_REQUIRED"
    assert status["eligible_dataset_count"] == 0
    assert status["paper_trading_ready"] is False
    assert status["live_trading_ready"] is False
    assert eligible["eligible_datasets"] == []
    assert any(
        blocker["code"] == "FIXTURE_DATA_NOT_ALLOWED"
        for diagnostic in eligible["dataset_diagnostics"]
        for blocker in diagnostic["blockers"]
    )


def test_research_activation_attempt_records_blocked_manifest() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/research-activation/activate-historical",
        headers={"X-Aegis-Role": "RESEARCHER"},
        json={},
    )
    manifests = client.get("/api/v1/research-activation/manifests").json()

    assert response.status_code == 409
    assert response.json()["detail"]["status"] == "BLOCKED"
    assert manifests
    assert manifests[-1]["paper_trading_ready"] is False
    assert manifests[-1]["live_trading_ready"] is False


def test_baseline_evidence_review_api_runs_all_three_strategies() -> None:
    client = TestClient(app)

    payload = client.get("/api/v1/research/actual-data/evidence-reviews/baselines").json()

    assert payload["ranking_allowed"] is False
    assert payload["paper_trading_activated"] is False
    assert payload["live_execution_activated"] is False
    assert payload["final_state"] == "ALL_BASELINES_RESEARCH_ONLY_NEEDS_FIXES"
    assert [review["strategy_version"] for review in payload["reviews"]] == [
        "BuyAndHoldBenchmarkStrategyV0",
        "EqualWeightUniverseBenchmarkStrategyV0",
        "TrendFollowingBaselineStrategyV0",
    ]
    assert all(
        review["final_classification"] == "RESEARCH_ONLY_NEEDS_FIXES"
        for review in payload["reviews"]
    )
