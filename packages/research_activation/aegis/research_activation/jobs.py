from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from aegis.research_activation.service import HistoricalResearchActivationService


class ActualResearchJobType(str, Enum):
    READINESS = "ActualDataResearchReadinessJob"
    FEATURE_COMPUTATION = "ActualFeatureComputationJob"
    BASELINE_EXPERIMENT_PREPARATION = "BaselineExperimentPreparationJob"
    BACKTEST_SIMULATION = "ActualBacktestSimulationJob"
    STRESS_TEST = "ActualResearchStressTestJob"
    ATTRIBUTION = "ActualResearchAttributionJob"
    EVIDENCE_PACKAGE = "ActualResearchEvidencePackageJob"
    COVERAGE_MONITORING = "ResearchCoverageMonitoringJob"
    DASHBOARD_SNAPSHOT = "ActualResearchDashboardSnapshotJob"


@dataclass(frozen=True)
class ActualResearchJob:
    job_type: ActualResearchJobType
    correlation_id: str
    experiment_id: str | None = None
    dataset_version_id: str | None = None
    feature_run_id: str | None = None
    job_id: str = field(default_factory=lambda: f"actual-research-job-{uuid4()}")
    status: str = "QUEUED"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    result: dict[str, Any] = field(default_factory=dict)


class ActualResearchJobRunner:
    def __init__(self, service: HistoricalResearchActivationService) -> None:
        self.service = service
        self.jobs: dict[str, ActualResearchJob] = {}
        self.idempotency_keys: dict[str, str] = {}

    def enqueue(self, job: ActualResearchJob) -> ActualResearchJob:
        key = self._key(job)
        existing_id = self.idempotency_keys.get(key)
        if existing_id:
            return self.jobs[existing_id]
        self.jobs[job.job_id] = job
        self.idempotency_keys[key] = job.job_id
        return job

    def run_once(self) -> ActualResearchJob | None:
        queued = next((job for job in self.jobs.values() if job.status == "QUEUED"), None)
        if queued is None:
            return None
        readiness = self.service.status()
        completed = ActualResearchJob(
            job_type=queued.job_type,
            correlation_id=queued.correlation_id,
            experiment_id=queued.experiment_id,
            dataset_version_id=queued.dataset_version_id,
            feature_run_id=queued.feature_run_id,
            job_id=queued.job_id,
            status="BLOCKED" if readiness["overall_status"] == "BLOCKED" else "COMPLETED",
            created_at=queued.created_at,
            completed_at=datetime.now(UTC).isoformat(),
            result={
                "readiness": readiness,
                "paper_trading_activated": False,
                "live_execution_activated": False,
            },
        )
        self.jobs[queued.job_id] = completed
        return completed

    def list_jobs(self) -> list[dict[str, Any]]:
        return [asdict(job) for job in self.jobs.values()]

    def _key(self, job: ActualResearchJob) -> str:
        return ":".join(
            [
                job.job_type.value,
                job.correlation_id,
                job.experiment_id or "",
                job.dataset_version_id or "",
                job.feature_run_id or "",
            ]
        )
