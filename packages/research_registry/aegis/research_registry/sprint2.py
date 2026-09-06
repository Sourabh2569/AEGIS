from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import Enum
from typing import Any

from aegis.shared.ids import new_id
from aegis.shared.time import utc_now


class StrEnum(str, Enum):
    pass


RESEARCH_LABELS = (
    "RESEARCH_ONLY",
    "NOT_VALIDATED",
    "NOT_PAPER_TRADING_ELIGIBLE",
    "NOT_LIVE_TRADING_ELIGIBLE",
)


class ResearchFamilyStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"


class HypothesisStatus(StrEnum):
    DRAFT = "DRAFT"
    EXPLORATORY = "EXPLORATORY"
    UNDER_VALIDATION = "UNDER_VALIDATION"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class StrategyStatus(StrEnum):
    DRAFT = "DRAFT"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    PAUSED = "PAUSED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ResearchFamily:
    name: str
    description: str
    economic_thesis: str
    created_by: str
    status: ResearchFamilyStatus = ResearchFamilyStatus.ACTIVE
    id: str = field(default_factory=lambda: new_id("rf"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class Hypothesis:
    research_family_id: str
    title: str
    core_hypothesis: str
    economic_rationale: str
    persistence_rationale: str
    market_regime_assumptions: str
    failure_regimes: str
    required_data_description: str
    known_risks: str
    counter_hypothesis: str
    primary_success_metric: str
    rejection_criteria_json: dict[str, Any]
    created_by: str
    status: HypothesisStatus = HypothesisStatus.DRAFT
    id: str = field(default_factory=lambda: new_id("hyp"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def assert_ready_for_validation(self) -> None:
        required = {
            "economic_rationale": self.economic_rationale,
            "counter_hypothesis": self.counter_hypothesis,
            "failure_regimes": self.failure_regimes,
            "required_data_description": self.required_data_description,
            "rejection_criteria_json": self.rejection_criteria_json,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Hypothesis is not validation-ready: {missing}")


@dataclass(frozen=True)
class Strategy:
    research_family_id: str
    hypothesis_id: str
    name: str
    description: str
    strategy_type: str
    status: StrategyStatus = StrategyStatus.RESEARCH_ONLY
    strategy_id: str = field(default_factory=lambda: new_id("strategy"))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.status.value in {"VALIDATED", "PAPER_TRADING", "LIVE_CANDIDATE", "LIVE_ENABLED"}:
            raise ValueError("Sprint 2 strategies cannot use validated, paper, or live statuses.")


@dataclass(frozen=True)
class StrategyVersion:
    strategy_id: str
    version: str
    source_commit_hash: str
    configuration_json: dict[str, Any]
    feature_requirements_json: dict[str, Any]
    universe_definition_json: dict[str, Any]
    entry_logic_description: str
    exit_logic_description: str
    invalidation_logic_description: str
    ranking_logic_description: str
    position_sizing_policy_reference: str
    risk_profile_version_reference: str
    strategy_version_id: str = field(default_factory=lambda: new_id("strategy-version"))
    created_at: datetime = field(default_factory=utc_now)
    approved_at_nullable: datetime | None = None


@dataclass(frozen=True)
class Experiment:
    strategy_version_id: str
    name: str
    created_by: str
    experiment_id: str = field(default_factory=lambda: new_id("experiment"))
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class ExperimentManifest:
    experiment_id: str
    strategy_version_id: str
    dataset_version_id: str
    instrument_master_version: str
    corporate_action_version: str
    universe_version: str
    feature_versions_json: dict[str, str]
    benchmark_definition: str
    cost_schedule_version: str
    slippage_model_version: str
    settlement_model_version: str
    risk_profile_version: str
    start_date: date
    end_date: date
    training_start_date: date
    training_end_date: date
    validation_start_date: date
    validation_end_date: date
    holdout_start_date: date
    holdout_end_date: date
    rebalance_frequency: str
    decision_time_policy: str
    execution_time_policy: str
    primary_metric: str
    secondary_metrics_json: list[str]
    rejection_criteria_json: dict[str, Any]
    random_seed: int
    software_commit_hash: str
    is_frozen: bool = False
    frozen_at: datetime | None = None
    id: str = field(default_factory=lambda: new_id("manifest"))
    created_at: datetime = field(default_factory=utc_now)

    def freeze(self) -> ExperimentManifest:
        return replace(self, is_frozen=True, frozen_at=utc_now())

    def update_rebalance_frequency(self, value: str) -> ExperimentManifest:
        if self.is_frozen:
            raise ValueError("Frozen experiment manifests are immutable.")
        return replace(self, rebalance_frequency=value)


@dataclass(frozen=True)
class HoldoutUsageRecord:
    experiment_id: str
    holdout_start_date: date
    holdout_end_date: date
    purpose: str
    created_by: str
    id: str = field(default_factory=lambda: new_id("holdout"))
    created_at: datetime = field(default_factory=utc_now)


class ResearchRegistry:
    def __init__(self) -> None:
        self.families: dict[str, ResearchFamily] = {}
        self.hypotheses: dict[str, Hypothesis] = {}
        self.strategies: dict[str, Strategy] = {}
        self.strategy_versions: dict[str, StrategyVersion] = {}
        self.experiments: dict[str, Experiment] = {}
        self.manifests: dict[str, ExperimentManifest] = {}
        self.holdout_usage: list[HoldoutUsageRecord] = []

    def add_family(self, family: ResearchFamily) -> ResearchFamily:
        self.families[family.id] = family
        return family

    def add_hypothesis(self, hypothesis: Hypothesis) -> Hypothesis:
        self.hypotheses[hypothesis.id] = hypothesis
        return hypothesis

    def add_strategy(self, strategy: Strategy) -> Strategy:
        self.strategies[strategy.strategy_id] = strategy
        return strategy

    def add_strategy_version(self, version: StrategyVersion) -> StrategyVersion:
        self.strategy_versions[version.strategy_version_id] = version
        return version

    def add_experiment(self, experiment: Experiment, manifest: ExperimentManifest) -> Experiment:
        if not manifest.is_frozen:
            raise ValueError("Formal Sprint 2 experiments require a frozen manifest.")
        self.experiments[experiment.experiment_id] = experiment
        self.manifests[experiment.experiment_id] = manifest
        return experiment

    def record_holdout_usage(self, record: HoldoutUsageRecord) -> HoldoutUsageRecord:
        for existing in self.holdout_usage:
            if (
                existing.experiment_id == record.experiment_id
                and existing.holdout_start_date == record.holdout_start_date
                and existing.holdout_end_date == record.holdout_end_date
            ):
                raise ValueError("Holdout window has already been consumed for this experiment.")
        self.holdout_usage.append(record)
        return record
