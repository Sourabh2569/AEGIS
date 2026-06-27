from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any
from uuid import uuid5, NAMESPACE_URL

from aegis.research_activation.service import HistoricalResearchActivationService


BASELINE_STRATEGY_VERSIONS = [
    "BuyAndHoldBenchmarkStrategyV0",
    "EqualWeightUniverseBenchmarkStrategyV0",
    "TrendFollowingBaselineStrategyV0",
]

MANDATORY_GATE_AREAS = [
    "Data integrity and lineage",
    "Fixture isolation",
    "Point-in-time integrity",
    "Experiment governance",
    "Cost, slippage, and settlement realism",
    "Risk controls and portfolio construction",
    "Corporate-action treatment",
    "Backtest reproducibility",
    "Stress and sensitivity analysis",
    "Operational readiness for paper observation",
    "Evidence package completeness",
]

NON_BLOCKING_GATE_AREAS = [
    "Performance and attribution transparency",
]

REVIEW_LABELS = [
    "ACTUAL_HISTORICAL_RESEARCH_ONLY",
    "NOT_VALIDATED",
    "NOT_PAPER_TRADING_ELIGIBLE",
    "NOT_LIVE_TRADING_ELIGIBLE",
    "NO_REAL_CAPITAL_DEPLOYED",
]


@dataclass(frozen=True)
class EvidenceGateArea:
    name: str
    status: str
    blocking_issue: bool
    evidence_reference: str


@dataclass(frozen=True)
class BaselineEvidenceReview:
    review_id: str
    review_date: str
    strategy_name: str
    strategy_version: str
    experiment_id: str | None
    backtest_run_id: str | None
    evidence_package_id: str | None
    data_origin: str | None
    provider_name: str | None
    dataset_version_id: str | None
    universe_version_id: str
    benchmark_definition_id: str
    feature_run_id: str | None
    final_classification: str
    primary_decision_rationale: str
    critical_issues_found: list[str]
    required_remediation_actions: list[str]
    gate_summary: list[EvidenceGateArea]
    comparison_role: str
    labels: list[str]
    paper_trading_activated: bool = False
    live_execution_activated: bool = False


class ResearchEvidenceReviewGate:
    def __init__(self, activation_service: HistoricalResearchActivationService) -> None:
        self.activation_service = activation_service

    def review_baseline_strategy(self, strategy_version: str) -> dict[str, Any]:
        if strategy_version not in BASELINE_STRATEGY_VERSIONS:
            raise ValueError("BASELINE_STRATEGY_ONLY")

        readiness = self.activation_service.status()
        blocking_reasons = list(readiness["reason_codes"])
        missing_evidence = [
            "NO_ACTUAL_HISTORICAL_BACKTEST_RUN",
            "NO_FROZEN_EXPERIMENT_MANIFEST",
            "NO_ACTUAL_EVIDENCE_PACKAGE",
            "NO_FEATURE_RUN_ID",
            "NO_REPRODUCIBILITY_RESULT",
            "NO_STRESS_RESULTS",
        ]
        critical_issues = blocking_reasons + missing_evidence
        gate_summary = self._gate_summary(readiness, missing_evidence)
        review = BaselineEvidenceReview(
            review_id=self._review_id(strategy_version),
            review_date=date.today().isoformat(),
            strategy_name=strategy_version.removesuffix("StrategyV0").replace("V0", ""),
            strategy_version=strategy_version,
            experiment_id=None,
            backtest_run_id=None,
            evidence_package_id=None,
            data_origin=None,
            provider_name=None,
            dataset_version_id=readiness["dataset_version_id"],
            universe_version_id=readiness["universe_version_id"],
            benchmark_definition_id=readiness["benchmark_version_id"],
            feature_run_id=None,
            final_classification="RESEARCH_ONLY_NEEDS_FIXES",
            primary_decision_rationale=(
                "Formal paper-readiness review cannot progress because no completed actual "
                "historical research run, frozen manifest, feature run, or immutable evidence "
                "package exists for this baseline."
            ),
            critical_issues_found=critical_issues,
            required_remediation_actions=[
                "Configure an approved read-only provider or approved file import.",
                "Ingest actual historical EOD data into immutable raw storage.",
                "Pass actual research eligibility and fixture-isolation gates.",
                "Create a point-in-time actual feature run.",
                "Create and freeze an actual-data baseline experiment manifest.",
                "Run the baseline through shared cost, slippage, settlement, risk, and ledger engines.",
                "Generate an immutable evidence package and rerun this review gate.",
            ],
            gate_summary=gate_summary,
            comparison_role=self._comparison_role(strategy_version),
            labels=REVIEW_LABELS,
        )
        return self._jsonable(review)

    def review_all_baselines(self) -> dict[str, Any]:
        reviews = [
            self.review_baseline_strategy(strategy) for strategy in BASELINE_STRATEGY_VERSIONS
        ]
        return {
            "comparison": "Trend-Following Strategy vs Equal-Weight Universe vs Buy-and-Hold Benchmark",
            "ranking_allowed": False,
            "paper_trading_activated": False,
            "live_execution_activated": False,
            "final_state": "ALL_BASELINES_RESEARCH_ONLY_NEEDS_FIXES",
            "reviews": reviews,
        }

    def _gate_summary(
        self, readiness: dict[str, Any], missing_evidence: list[str]
    ) -> list[EvidenceGateArea]:
        evidence_ref = "GET /api/v1/research/actual-data/readiness"
        mandatory = [
            EvidenceGateArea(
                name=area,
                status="FAIL",
                blocking_issue=True,
                evidence_reference=evidence_ref,
            )
            for area in MANDATORY_GATE_AREAS
        ]
        non_blocking = [
            EvidenceGateArea(
                name=area,
                status="FAIL",
                blocking_issue=False,
                evidence_reference="No completed actual evidence package exists.",
            )
            for area in NON_BLOCKING_GATE_AREAS
        ]
        if readiness["overall_status"] != "BLOCKED" and not missing_evidence:
            return [
                EvidenceGateArea(
                    name=area.name,
                    status="PASS",
                    blocking_issue=False,
                    evidence_reference=area.evidence_reference,
                )
                for area in mandatory + non_blocking
            ]
        return mandatory + non_blocking

    def _review_id(self, strategy_version: str) -> str:
        return f"evidence-review-{uuid5(NAMESPACE_URL, strategy_version)}"

    def _comparison_role(self, strategy_version: str) -> str:
        roles = {
            "BuyAndHoldBenchmarkStrategyV0": "Engine mechanics and accounting integrity baseline",
            "EqualWeightUniverseBenchmarkStrategyV0": "Diversified neutral market-participation baseline",
            "TrendFollowingBaselineStrategyV0": "Point-in-time feature, ranking, and risk-control baseline",
        }
        return roles[strategy_version]

    def _jsonable(self, review: BaselineEvidenceReview) -> dict[str, Any]:
        payload = asdict(review)
        payload["gate_summary"] = [asdict(area) for area in review.gate_summary]
        return payload
