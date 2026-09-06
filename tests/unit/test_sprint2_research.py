from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from aegis.backtesting.sprint2 import Sprint2ResearchScenarioRunner
from aegis.feature_engine.engine import daily_return, ema, rsi, sma
from aegis.research_registry.sprint2 import (
    Experiment,
    ExperimentManifest,
    HoldoutUsageRecord,
    ResearchRegistry,
    Strategy,
)
from aegis.risk.engine import (
    KillSwitch,
    KillSwitchType,
    PortfolioRiskState,
    PositionSizingEngine,
    RiskProfileVersion,
    drawdown_state,
)

ROOT = Path(__file__).resolve().parents[2]


def manifest(frozen: bool = True) -> ExperimentManifest:
    value = ExperimentManifest(
        experiment_id="exp-1",
        strategy_version_id="sv-1",
        dataset_version_id="dv-1",
        instrument_master_version="im-v1",
        corporate_action_version="ca-v1",
        universe_version="u-v1",
        feature_versions_json={"SMA_50": "V0"},
        benchmark_definition="fixture",
        cost_schedule_version="FIXTURE_COST_SCHEDULE_V0",
        slippage_model_version="FIXED_BPS_SLIPPAGE_V0",
        settlement_model_version="T_PLUS_1_CONSERVATIVE_V0",
        risk_profile_version="AEGIS_CONSERVATIVE_V0",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        training_start_date=date(2026, 1, 1),
        training_end_date=date(2026, 3, 31),
        validation_start_date=date(2026, 4, 1),
        validation_end_date=date(2026, 6, 30),
        holdout_start_date=date(2026, 7, 1),
        holdout_end_date=date(2026, 12, 31),
        rebalance_frequency="WEEKLY",
        decision_time_policy="POST_CLOSE",
        execution_time_policy="NEXT_ELIGIBLE_SESSION_OPEN",
        primary_metric="TOTAL_RETURN",
        secondary_metrics_json=["MAX_DRAWDOWN"],
        rejection_criteria_json={"max_drawdown": "-0.20"},
        random_seed=42,
        software_commit_hash="local",
    )
    return value.freeze() if frozen else value


def test_frozen_manifest_is_immutable_and_required() -> None:
    registry = ResearchRegistry()
    frozen = manifest()
    registry.add_experiment(
        Experiment(strategy_version_id="sv-1", name="exp", created_by="RESEARCHER"), frozen
    )
    with pytest.raises(ValueError):
        frozen.update_rebalance_frequency("DAILY")
    with pytest.raises(ValueError):
        registry.add_experiment(
            Experiment(strategy_version_id="sv-1", name="bad", created_by="RESEARCHER"),
            manifest(False),
        )


def test_holdout_consumption_blocks_reuse() -> None:
    registry = ResearchRegistry()
    record = HoldoutUsageRecord(
        experiment_id="exp-1",
        holdout_start_date=date(2026, 7, 1),
        holdout_end_date=date(2026, 12, 31),
        purpose="single inspection",
        created_by="RESEARCHER",
    )
    registry.record_holdout_usage(record)
    with pytest.raises(ValueError):
        registry.record_holdout_usage(record)


def test_research_only_status_enforced() -> None:
    strategy = Strategy(
        research_family_id="rf-1",
        hypothesis_id="hyp-1",
        name="baseline",
        description="baseline",
        strategy_type="BASELINE",
    )
    assert strategy.status == "RESEARCH_ONLY"


def test_feature_math_known_values() -> None:
    values = [Decimal(1), Decimal(2), Decimal(3), Decimal(4)]
    assert daily_return(Decimal(100), Decimal(110)) == Decimal("0.1000")
    assert sma(values, 4) == Decimal("2.5000")
    assert ema(values, 2) is not None
    assert rsi([Decimal(1), Decimal(2), Decimal(3), Decimal(4), Decimal(5)], 4) == Decimal(
        "100.0000"
    )


def test_risk_state_and_kill_switch_block() -> None:
    assert drawdown_state(Decimal("-0.11")) == PortfolioRiskState.FROZEN
    assessment = PositionSizingEngine().assess(
        portfolio_id="p",
        strategy_id="s",
        instrument_id="i",
        portfolio_nav=Decimal(100000),
        available_cash=Decimal(100000),
        existing_position_value=Decimal(0),
        sector_value=Decimal(0),
        cluster_value=Decimal(0),
        gross_equity_value=Decimal(0),
        entry_price=Decimal(100),
        invalidation_price=Decimal(90),
        proposed_quantity=Decimal(100),
        sector="Financials",
        cluster="FINANCIALS",
        data_quality_status="GREEN",
        instrument_eligibility_status="ELIGIBLE",
        profile=RiskProfileVersion(),
        current_drawdown=Decimal(0),
        kill_switches=[KillSwitch(KillSwitchType.GLOBAL_TRADING_KILL_SWITCH, "GLOBAL", True)],
    )
    assert assessment.approved_quantity == Decimal("0.000000")
    assert any("KILL_SWITCH_ACTIVE" in reason for reason in assessment.reason_codes)


def test_sprint2_scenario_a_runs_research_only() -> None:
    report = Sprint2ResearchScenarioRunner(
        ROOT / "sample_data/sprint_2"
    ).run_equal_weight_scenario()
    assert "RESEARCH_ONLY" in report.classification
    assert report.position_count > 0
    assert report.cash_weight >= Decimal("0.2000")


def test_t_plus_1_settlement_blocks_unsettled_cash_reuse() -> None:
    reason = Sprint2ResearchScenarioRunner(
        ROOT / "sample_data/sprint_2"
    ).settlement_restriction_demo()
    assert reason == "INSUFFICIENT_SETTLED_CASH"
