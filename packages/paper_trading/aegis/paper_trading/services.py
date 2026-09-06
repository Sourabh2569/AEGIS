from __future__ import annotations

import csv
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from aegis.audit.service import AuditLog
from aegis.paper_trading.domain import (
    PAPER_LABELS,
    DriftState,
    IncidentType,
    LifecycleStatus,
    PaperApproval,
    PaperApprovalDecision,
    PaperCorporateActionReview,
    PaperDriftAssessment,
    PaperEvidencePackage,
    PaperFill,
    PaperIntentStatus,
    PaperLedgerEntry,
    PaperNavSnapshot,
    PaperOrder,
    PaperOrderStatus,
    PaperPortfolio,
    PaperPortfolioConfiguration,
    PaperPortfolioStatus,
    PaperReconciliationRecord,
    PaperStrategyConfigStatus,
    PaperStrategyConfiguration,
    PaperTradeIntent,
    PaperTradingIncident,
    PaperTradingSession,
    default_approval_expiry,
)
from aegis.portfolio.sprint2 import (
    CostModel,
    CostSchedule,
    FixedBpsSlippageModelV0,
    ResearchPortfolio,
)
from aegis.risk.engine import (
    KillSwitch,
    KillSwitchType,
    PositionSizingEngine,
    RiskAssessment,
    RiskDecision,
    RiskProfileVersion,
)
from aegis.shared.ids import new_id
from aegis.shared.money import money, quantity
from aegis.shared.time import require_aware_utc, utc_now


def persist_if_supported(repository: Any) -> None:
    persist = getattr(repository, "persist", None)
    if callable(persist):
        persist()


class PaperTradingRepository:
    def __init__(self) -> None:
        self.portfolios: dict[str, PaperPortfolio] = {}
        self.portfolio_configs: dict[str, PaperPortfolioConfiguration] = {}
        self.strategy_configs: dict[str, PaperStrategyConfiguration] = {}
        self.sessions: dict[str, PaperTradingSession] = {}
        self.intents: dict[str, PaperTradeIntent] = {}
        self.approvals: dict[str, PaperApproval] = {}
        self.orders: dict[str, PaperOrder] = {}
        self.fills: dict[str, PaperFill] = {}
        self.ledger: dict[str, list[PaperLedgerEntry]] = {}
        self.nav: dict[str, list[PaperNavSnapshot]] = {}
        self.reconciliations: dict[str, list[PaperReconciliationRecord]] = {}
        self.incidents: dict[str, PaperTradingIncident] = {}
        self.drift: dict[str, PaperDriftAssessment] = {}
        self.evidence: dict[str, PaperEvidencePackage] = {}
        self.corporate_action_reviews: dict[str, PaperCorporateActionReview] = {}
        self.executed_idempotency_keys: set[str] = set()
        self.session_idempotency_keys: set[str] = set()
        self.paper_portfolios: dict[str, ResearchPortfolio] = {}
        self.kill_switches: dict[str, KillSwitch] = {}

    def add_portfolio(self, portfolio: PaperPortfolio, config: PaperPortfolioConfiguration) -> None:
        self.portfolios[portfolio.paper_portfolio_id] = portfolio
        self.portfolio_configs[portfolio.paper_portfolio_id] = config
        self.paper_portfolios[portfolio.paper_portfolio_id] = ResearchPortfolio(
            portfolio_id=portfolio.paper_portfolio_id,
            cash=portfolio.starting_capital,
        )

    def save_portfolio(self, portfolio: PaperPortfolio) -> None:
        self.portfolios[portfolio.paper_portfolio_id] = portfolio

    def save_strategy_config(self, config: PaperStrategyConfiguration) -> None:
        self.strategy_configs[config.paper_strategy_config_id] = config

    def active_strategy_configs(self, paper_portfolio_id: str) -> list[PaperStrategyConfiguration]:
        return [
            config
            for config in self.strategy_configs.values()
            if config.paper_portfolio_id == paper_portfolio_id
            and config.status == PaperStrategyConfigStatus.ACTIVE
        ]


class PaperAdmissionService:
    required_flags = (
        "approved_research_family",
        "approved_hypothesis",
        "immutable_strategy_version",
        "frozen_experiment_manifest",
        "backtest_evidence_package",
        "required_feature_versions",
        "dataset_lineage_complete",
        "point_in_time_checks_passed",
        "corporate_action_coverage_acceptable",
        "cost_model_configured",
        "slippage_model_configured",
        "settlement_model_configured",
        "risk_profile_configured",
        "portfolio_constraints_configured",
        "invalidation_logic_exists",
        "market_regime_compatibility_documented",
        "failure_regimes_documented",
        "kill_switch_behavior_tested",
        "audit_logging_healthy",
        "paper_monitoring_plan_exists",
        "incident_runbook_exists",
        "pause_criteria_exists",
        "retirement_criteria_exists",
        "founder_approval_recorded",
    )

    def review(self, evidence: dict[str, bool]) -> list[str]:
        return [
            f"MISSING_{flag.upper()}"
            for flag in self.required_flags
            if not evidence.get(flag, False)
        ]


class PaperDataReadinessService:
    required_flags = (
        "market_calendar_valid",
        "market_session_eligible",
        "provider_license_approved",
        "provider_health_acceptable",
        "data_fresh",
        "dataset_green_or_caution",
        "instrument_mappings_verified",
        "universe_membership_available",
        "feature_inputs_available",
        "feature_values_computable",
        "corporate_action_status_acceptable",
        "strategy_configuration_frozen_active",
        "risk_engine_healthy",
        "audit_logging_healthy",
        "kill_switches_inactive",
        "portfolio_reconciliation_healthy",
    )

    def check(self, flags: dict[str, bool]) -> tuple[str, list[str]]:
        failures = [
            f"READINESS_{flag.upper()}_FAILED"
            for flag in self.required_flags
            if not flags.get(flag, False)
        ]
        return ("GREEN" if not failures else "BLOCKED", failures)


class PaperApprovalService:
    def __init__(self, repository: PaperTradingRepository, audit_log: AuditLog) -> None:
        self.repository = repository
        self.audit_log = audit_log

    def approve(
        self, intent_id: str, approver_id: str, now: datetime | None = None
    ) -> PaperApproval:
        now = require_aware_utc(now or utc_now())
        intent = self.repository.intents[intent_id]
        portfolio = self.repository.portfolios[intent.paper_portfolio_id]
        if portfolio.status in {
            PaperPortfolioStatus.CAPITAL_PRESERVATION,
            PaperPortfolioStatus.FROZEN,
            PaperPortfolioStatus.PAUSED,
        }:
            raise ValueError(f"APPROVAL_BLOCKED_BY_PORTFOLIO_STATE:{portfolio.status}")
        approval = PaperApproval(
            paper_trade_intent_id=intent.paper_trade_intent_id,
            approver_id=approver_id,
            decision=PaperApprovalDecision.APPROVED,
            decision_time=now,
            risk_assessment_id=intent.risk_assessment_id,
            paper_strategy_config_id=intent.paper_strategy_config_id,
            reason="Approved for paper-only simulated execution.",
            expiry_time=max(
                default_approval_expiry(now), intent.eligible_execution_time + timedelta(hours=1)
            ),
        )
        self.repository.approvals[approval.paper_trade_intent_id] = approval
        self.repository.intents[intent_id] = replace(
            intent,
            approval_status=PaperApprovalDecision.APPROVED,
            intent_status=PaperIntentStatus.APPROVED,
            updated_at=utc_now(),
        )
        persist_if_supported(self.repository)
        self.audit_log.record(
            event_type="PAPER_INTENT_APPROVED",
            entity_type="PaperTradeIntent",
            entity_id=intent_id,
            actor_type="USER",
            actor_id=approver_id,
            action="APPROVE_PAPER_INTENT",
            before_state=None,
            after_state={"classification": list(PAPER_LABELS)},
            correlation_id=intent.correlation_id,
        )
        return approval

    def reject(self, intent_id: str, approver_id: str, reason: str) -> PaperApproval:
        if not reason:
            raise ValueError("REJECTION_REASON_REQUIRED")
        intent = self.repository.intents[intent_id]
        approval = PaperApproval(
            paper_trade_intent_id=intent.paper_trade_intent_id,
            approver_id=approver_id,
            decision=PaperApprovalDecision.REJECTED,
            decision_time=utc_now(),
            risk_assessment_id=intent.risk_assessment_id,
            paper_strategy_config_id=intent.paper_strategy_config_id,
            reason=reason,
            expiry_time=utc_now(),
        )
        self.repository.approvals[approval.paper_trade_intent_id] = approval
        self.repository.intents[intent_id] = replace(
            intent,
            approval_status=PaperApprovalDecision.REJECTED,
            intent_status=PaperIntentStatus.REJECTED,
            reason_codes_json=[*intent.reason_codes_json, "MANUALLY_REJECTED"],
            updated_at=utc_now(),
        )
        persist_if_supported(self.repository)
        return approval

    def expire_due(self, now: datetime | None = None) -> list[PaperApproval]:
        now = require_aware_utc(now or utc_now())
        expired: list[PaperApproval] = []
        for intent_id, approval in list(self.repository.approvals.items()):
            if approval.decision == PaperApprovalDecision.APPROVED and approval.expiry_time < now:
                updated = replace(approval, decision=PaperApprovalDecision.EXPIRED)
                self.repository.approvals[intent_id] = updated
                intent = self.repository.intents[intent_id]
                self.repository.intents[intent_id] = replace(
                    intent,
                    approval_status=PaperApprovalDecision.EXPIRED,
                    intent_status=PaperIntentStatus.EXPIRED,
                    reason_codes_json=[*intent.reason_codes_json, "APPROVAL_EXPIRED"],
                    updated_at=utc_now(),
                )
                expired.append(updated)
        persist_if_supported(self.repository)
        return expired


class PaperIncidentService:
    def __init__(self, repository: PaperTradingRepository, audit_log: AuditLog) -> None:
        self.repository = repository
        self.audit_log = audit_log

    def create(
        self,
        *,
        paper_portfolio_id: str,
        incident_type: IncidentType,
        severity: str,
        description: str,
        reason_codes: list[str],
        freeze: bool,
        correlation_id: str,
    ) -> PaperTradingIncident:
        incident = PaperTradingIncident(
            paper_portfolio_id=paper_portfolio_id,
            incident_type=incident_type,
            severity=severity,
            description=description,
            status="OPEN",
            reason_codes=reason_codes,
        )
        self.repository.incidents[incident.id] = incident
        if freeze:
            portfolio = self.repository.portfolios[paper_portfolio_id].freeze(description)
            self.repository.save_portfolio(portfolio)
        persist_if_supported(self.repository)
        self.audit_log.record(
            event_type="PAPER_INCIDENT_CREATED",
            entity_type="PaperTradingIncident",
            entity_id=incident.id,
            actor_type="SYSTEM_SERVICE",
            actor_id="paper-incident-service",
            action="CREATE_INCIDENT",
            before_state=None,
            after_state=asdict(incident),
            correlation_id=correlation_id,
        )
        return incident


class PaperReconciliationService:
    def __init__(
        self, repository: PaperTradingRepository, incident_service: PaperIncidentService
    ) -> None:
        self.repository = repository
        self.incident_service = incident_service

    def reconcile(
        self,
        paper_portfolio_id: str,
        expected_nav: Decimal,
        observed_nav: Decimal,
        correlation_id: str,
    ) -> PaperReconciliationRecord:
        expected_nav = money(expected_nav)
        status = "GREEN" if expected_nav == money(observed_nav) else "RED"
        reasons = [] if status == "GREEN" else ["RECONCILIATION_FAILURE"]
        record = PaperReconciliationRecord(
            paper_portfolio_id=paper_portfolio_id,
            reconciliation_time=utc_now(),
            expected_nav=expected_nav,
            observed_nav=money(observed_nav),
            status=status,
            reason_codes=reasons,
        )
        self.repository.reconciliations.setdefault(paper_portfolio_id, []).append(record)
        if status == "RED":
            self.incident_service.create(
                paper_portfolio_id=paper_portfolio_id,
                incident_type=IncidentType.RECONCILIATION_INCIDENT,
                severity="CRITICAL",
                description="Paper portfolio reconciliation mismatch.",
                reason_codes=reasons,
                freeze=True,
                correlation_id=correlation_id,
            )
        persist_if_supported(self.repository)
        return record


class PaperMonitoringService:
    def assess_drift(
        self,
        *,
        paper_strategy_config_id: str,
        expected_signal_count: int,
        observed_signal_count: int,
    ) -> PaperDriftAssessment:
        ratio = (
            Decimal(0)
            if expected_signal_count == 0
            else Decimal(observed_signal_count) / Decimal(expected_signal_count)
        )
        if ratio <= Decimal("0.25") or ratio >= Decimal(3):
            state = DriftState.CRITICAL_DIVERGENCE
            action = "PAUSE_STRATEGY_AND_REVALIDATE"
        elif ratio <= Decimal("0.50") or ratio >= Decimal(2):
            state = DriftState.MATERIAL_DIVERGENCE
            action = "INITIATE_REVIEW"
        elif ratio <= Decimal("0.75") or ratio >= Decimal("1.50"):
            state = DriftState.WATCH
            action = "INCREASE_MONITORING"
        else:
            state = DriftState.WITHIN_EXPECTATION
            action = "CONTINUE_MONITORING"
        return PaperDriftAssessment(
            paper_strategy_config_id=paper_strategy_config_id,
            assessment_time=utc_now(),
            drift_category="SIGNAL_FREQUENCY",
            severity=state,
            expected_range_reference=f"expected={expected_signal_count}",
            observed_value=Decimal(observed_signal_count),
            market_regime="NORMAL",
            recommended_action=action,
            reason_codes=[state],
        )


class PaperTradingCalendarService:
    def __init__(self, sessions: list[date], exchange: str = "NSE") -> None:
        self.sessions = sorted(set(sessions))
        self.exchange = exchange

    @classmethod
    def from_csv(cls, path: Path, exchange: str = "NSE") -> PaperTradingCalendarService:
        with path.open(newline="", encoding="utf-8") as file:
            rows = list(csv.DictReader(file))
        sessions = [
            date.fromisoformat(row["session_date"])
            for row in rows
            if row.get("exchange", exchange) == exchange and row["is_open"].lower() == "true"
        ]
        return cls(sessions=sessions, exchange=exchange)

    def next_open_session_after(self, value: datetime) -> date:
        decision_date = require_aware_utc(value).date()
        for session in self.sessions:
            if session > decision_date:
                return session
        raise ValueError(f"NO_GOVERNED_OPEN_SESSION_AFTER:{decision_date}")

    def open_time(self, session: date) -> datetime:
        if session not in self.sessions:
            raise ValueError(f"SESSION_NOT_OPEN:{session}")
        return datetime.combine(session, time(3, 45), tzinfo=UTC)


class PaperCorporateActionReviewService:
    def __init__(self, repository: PaperTradingRepository, incidents: PaperIncidentService) -> None:
        self.repository = repository
        self.incidents = incidents

    def review(
        self,
        *,
        paper_portfolio_id: str,
        instrument_id: str,
        action_type: str,
        effective_date: date,
        verification_status: str,
        supported: bool,
        reviewer_id: str,
        correlation_id: str,
    ) -> PaperCorporateActionReview:
        if supported and verification_status == "VERIFIED":
            review = PaperCorporateActionReview(
                paper_portfolio_id=paper_portfolio_id,
                instrument_id=instrument_id,
                action_type=action_type,
                effective_date=effective_date,
                verification_status=verification_status,
                support_status="SUPPORTED",
                decision="ACCEPTED_FOR_PAPER_LEDGER",
                reviewer_id_nullable=reviewer_id,
                reason_codes=["SUPPORTED_VERIFIED_CORPORATE_ACTION"],
            )
            self.repository.corporate_action_reviews[review.id] = review
            persist_if_supported(self.repository)
            return review

        incident = self.incidents.create(
            paper_portfolio_id=paper_portfolio_id,
            incident_type=IncidentType.CORPORATE_ACTION_INCIDENT,
            severity="CRITICAL",
            description=f"Unsupported or unverified corporate action for {instrument_id}.",
            reason_codes=["UNSUPPORTED_OR_UNVERIFIED_CORPORATE_ACTION"],
            freeze=True,
            correlation_id=correlation_id,
        )
        review = PaperCorporateActionReview(
            paper_portfolio_id=paper_portfolio_id,
            instrument_id=instrument_id,
            action_type=action_type,
            effective_date=effective_date,
            verification_status=verification_status,
            support_status="SUPPORTED" if supported else "UNSUPPORTED",
            decision="REJECTED_AND_PORTFOLIO_FROZEN",
            reviewer_id_nullable=reviewer_id,
            incident_id_nullable=incident.id,
            reason_codes=["UNSUPPORTED_OR_UNVERIFIED_CORPORATE_ACTION"],
        )
        self.repository.corporate_action_reviews[review.id] = review
        persist_if_supported(self.repository)
        return review


class PaperTradingOrchestrator:
    def __init__(
        self,
        repository: PaperTradingRepository,
        audit_log: AuditLog,
        calendar: PaperTradingCalendarService | None = None,
    ) -> None:
        self.repository = repository
        self.audit_log = audit_log
        self.admission = PaperAdmissionService()
        self.readiness = PaperDataReadinessService()
        self.approvals = PaperApprovalService(repository, audit_log)
        self.incidents = PaperIncidentService(repository, audit_log)
        self.corporate_actions = PaperCorporateActionReviewService(repository, self.incidents)
        self.reconciliation = PaperReconciliationService(repository, self.incidents)
        self.monitoring = PaperMonitoringService()
        self.calendar = calendar or PaperTradingCalendarService(
            sessions=[date(2026, 6, 26), date(2026, 6, 29), date(2026, 6, 30)]
        )
        self.risk_engine = PositionSizingEngine()
        self.profile = RiskProfileVersion()
        self.cost_model = CostModel()
        self.cost_schedule = CostSchedule(
            version="PAPER_FIXTURE_COST_SCHEDULE_V0",
            brokerage_bps_buy=Decimal(5),
            brokerage_bps_sell=Decimal(5),
            other_bps_buy=Decimal(2),
            other_bps_sell=Decimal(2),
            verification_status="APPROVED_FIXTURE",
        )
        self.slippage = FixedBpsSlippageModelV0(Decimal(5), Decimal(5))

    def create_portfolio(
        self, *, name: str, description: str, starting_capital: Decimal, created_by: str
    ) -> PaperPortfolio:
        portfolio = PaperPortfolio(
            name=name,
            description=description,
            starting_capital=starting_capital,
            risk_profile_version_id=self.profile.profile_version,
            portfolio_configuration_version="PAPER_PORTFOLIO_CONFIG_V0",
            created_by=created_by,
            status=PaperPortfolioStatus.SETUP_PENDING,
        )
        config = PaperPortfolioConfiguration(
            paper_portfolio_id=portfolio.paper_portfolio_id,
            version="PAPER_PORTFOLIO_CONFIG_V0",
            risk_profile_version_id=self.profile.profile_version,
            minimum_cash_weight=self.profile.minimum_cash_weight_normal,
            maximum_gross_equity_exposure=self.profile.maximum_gross_equity_exposure_normal,
            maximum_position_count=self.profile.maximum_position_count,
            settlement_model_version="T_PLUS_1_CONSERVATIVE_V0",
            cost_schedule_version=self.cost_schedule.version,
            slippage_model_version=self.slippage.version,
            execution_model_version="NEXT_ELIGIBLE_SESSION_OPEN_WITH_CONFIGURED_FRICTION_V0",
            market_calendar_policy="GOVERNED_FORWARD_CALENDAR",
            valuation_policy="EOD_MARK_TO_MARKET",
            corporate_action_policy="SUPPORTED_ONLY_FAIL_CLOSED",
            created_by=created_by,
        ).freeze()
        self.repository.add_portfolio(portfolio, config)
        persist_if_supported(self.repository)
        return portfolio

    def create_strategy_config(self, paper_portfolio_id: str) -> PaperStrategyConfiguration:
        config = PaperStrategyConfiguration(
            paper_portfolio_id=paper_portfolio_id,
            strategy_id="EqualWeightUniverseBenchmarkStrategyV0",
            strategy_version_id="EqualWeightUniverseBenchmarkStrategyV0:V0",
            research_family_id="AEGIS_TEST_RESEARCH_FAMILY",
            risk_profile_version_id=self.profile.profile_version,
            dataset_version_policy="GREEN_OR_GREEN_CAUTION_ONLY",
            feature_version_policy="FROZEN_FEATURE_VERSIONS",
            universe_definition_version="AEGIS_TEST_UNIVERSE_V0",
            cost_schedule_version=self.cost_schedule.version,
            slippage_model_version=self.slippage.version,
            settlement_model_version="T_PLUS_1_CONSERVATIVE_V0",
            corporate_action_version="SUPPORTED_ONLY_V0",
            execution_model_version="NEXT_ELIGIBLE_SESSION_OPEN_WITH_CONFIGURED_FRICTION_V0",
            rebalancing_frequency="DAILY",
            decision_time_policy="POST_CLOSE_FORWARD_ONLY",
            execution_time_policy="NEXT_ELIGIBLE_SESSION_OPEN",
            market_regime_policy="NORMAL_FIXTURE",
            position_sizing_policy="AEGIS_CONSERVATIVE_V0",
            paper_start_date=date(2026, 6, 26),
            status=PaperStrategyConfigStatus.ADMISSION_PENDING,
        )
        self.repository.save_strategy_config(config)
        persist_if_supported(self.repository)
        return config

    def admit_and_activate_strategy(
        self, paper_strategy_config_id: str, evidence: dict[str, bool], approved_by: str
    ) -> PaperStrategyConfiguration:
        failures = self.admission.review(evidence)
        config = self.repository.strategy_configs[paper_strategy_config_id]
        if failures:
            failed = replace(config, status=PaperStrategyConfigStatus.FAILED)
            self.repository.save_strategy_config(failed)
            raise ValueError(",".join(failures))
        active = config.freeze().activate(approved_by)
        self.repository.save_strategy_config(active)
        portfolio = self.repository.portfolios[active.paper_portfolio_id]
        self.repository.save_portfolio(
            replace(portfolio, status=PaperPortfolioStatus.READY).activate()
        )
        persist_if_supported(self.repository)
        return active

    def run_decision_cycle(
        self,
        *,
        paper_portfolio_id: str,
        session_date: date,
        readiness_flags: dict[str, bool],
        reference_prices: dict[str, Decimal],
        correlation_id: str | None = None,
    ) -> PaperTradingSession:
        correlation_id = correlation_id or new_id("corr")
        idempotency_key = f"{paper_portfolio_id}:{session_date}:decision"
        if idempotency_key in self.repository.session_idempotency_keys:
            return next(
                session
                for session in self.repository.sessions.values()
                if session.paper_portfolio_id == paper_portfolio_id
                and session.session_date == session_date
            )
        self.repository.session_idempotency_keys.add(idempotency_key)
        status, failures = self.readiness.check(readiness_flags)
        portfolio = self.repository.portfolios[paper_portfolio_id]
        if status != "GREEN":
            session = PaperTradingSession(
                paper_portfolio_id=paper_portfolio_id,
                session_date=session_date,
                market_session_status="OPEN",
                data_readiness_status=status,
                portfolio_risk_state=portfolio.status,
                decision_cycle_status=LifecycleStatus.BLOCKED,
                execution_cycle_status=LifecycleStatus.PENDING,
                reconciliation_status="NOT_RUN",
                correlation_id=correlation_id,
                failure_reason_nullable=",".join(failures),
            )
            self.repository.sessions[session.paper_trading_session_id] = session
            self.incidents.create(
                paper_portfolio_id=paper_portfolio_id,
                incident_type=IncidentType.DATA_INCIDENT,
                severity="CRITICAL"
                if any("DATASET" in failure for failure in failures)
                else "WARNING",
                description="Paper data readiness failed.",
                reason_codes=failures,
                freeze=any("DATASET_GREEN_OR_CAUTION" in failure for failure in failures),
                correlation_id=correlation_id,
            )
            persist_if_supported(self.repository)
            return session
        session = PaperTradingSession(
            paper_portfolio_id=paper_portfolio_id,
            session_date=session_date,
            market_session_status="OPEN",
            data_readiness_status="GREEN",
            portfolio_risk_state=portfolio.status,
            decision_cycle_status=LifecycleStatus.RUNNING,
            execution_cycle_status=LifecycleStatus.PENDING,
            reconciliation_status="NOT_RUN",
            correlation_id=correlation_id,
        )
        self.repository.sessions[session.paper_trading_session_id] = session
        if portfolio.status in {
            PaperPortfolioStatus.CAPITAL_PRESERVATION,
            PaperPortfolioStatus.FROZEN,
            PaperPortfolioStatus.PAUSED,
        }:
            self.repository.sessions[session.paper_trading_session_id] = replace(
                session,
                decision_cycle_status=LifecycleStatus.BLOCKED,
                failure_reason_nullable=f"PORTFOLIO_STATE_BLOCKS_ORDER:{portfolio.status}",
            )
            persist_if_supported(self.repository)
            return self.repository.sessions[session.paper_trading_session_id]
        for config in self.repository.active_strategy_configs(paper_portfolio_id):
            instrument_id, price = next(iter(reference_prices.items()))
            risk = self.risk_engine.assess(
                portfolio_id=paper_portfolio_id,
                strategy_id=config.strategy_id,
                instrument_id=instrument_id,
                portfolio_nav=self.repository.paper_portfolios[paper_portfolio_id].cash,
                available_cash=self.repository.paper_portfolios[paper_portfolio_id].cash,
                existing_position_value=Decimal(0),
                sector_value=Decimal(0),
                cluster_value=Decimal(0),
                gross_equity_value=Decimal(0),
                entry_price=price,
                invalidation_price=money(price * Decimal("0.90")),
                proposed_quantity=Decimal(100),
                sector="Financials",
                cluster="FINANCIALS",
                data_quality_status="GREEN",
                instrument_eligibility_status="ELIGIBLE",
                profile=self.profile,
                current_drawdown=Decimal(0),
                kill_switches=list(self.repository.kill_switches.values()),
            )
            if (
                risk.decision in {RiskDecision.APPROVED, RiskDecision.APPROVED_WITH_REDUCED_SIZE}
                and risk.approved_quantity > 0
            ):
                decision_time = datetime.combine(session_date, time(10, 45), tzinfo=UTC)
                next_session = self.calendar.next_open_session_after(decision_time)
                intent = PaperTradeIntent(
                    paper_portfolio_id=paper_portfolio_id,
                    paper_strategy_config_id=config.paper_strategy_config_id,
                    strategy_version_id=config.strategy_version_id,
                    instrument_id=instrument_id,
                    side="BUY",
                    proposed_quantity=Decimal(100),
                    approved_quantity_nullable=risk.approved_quantity,
                    decision_time=decision_time,
                    available_data_cutoff=datetime.combine(session_date, time(10, 30), tzinfo=UTC),
                    eligible_execution_time=self.calendar.open_time(next_session),
                    risk_assessment_id=risk.risk_assessment_id,
                    configuration_version=config.paper_strategy_config_id,
                    idempotency_key=f"{paper_portfolio_id}:{session_date}:{instrument_id}:BUY",
                    correlation_id=correlation_id,
                    reason_codes_json=risk.reason_codes,
                )
                self.repository.intents[intent.paper_trade_intent_id] = intent
        completed = replace(
            session,
            decision_cycle_status=LifecycleStatus.COMPLETED,
            completed_at_nullable=utc_now(),
        )
        self.repository.sessions[session.paper_trading_session_id] = completed
        persist_if_supported(self.repository)
        return completed

    def execute_approved_orders(
        self,
        *,
        paper_portfolio_id: str,
        execution_time: datetime,
        reference_prices: dict[str, Decimal],
        correlation_id: str | None = None,
    ) -> list[PaperOrder]:
        correlation_id = correlation_id or new_id("corr")
        orders: list[PaperOrder] = []
        portfolio = self.repository.portfolios[paper_portfolio_id]
        if portfolio.status in {
            PaperPortfolioStatus.CAPITAL_PRESERVATION,
            PaperPortfolioStatus.FROZEN,
            PaperPortfolioStatus.PAUSED,
        }:
            return []
        for intent in list(self.repository.intents.values()):
            if intent.paper_portfolio_id != paper_portfolio_id:
                continue
            if intent.intent_status == PaperIntentStatus.PENDING_APPROVAL:
                blocked = PaperOrder(
                    paper_trade_intent_id=intent.paper_trade_intent_id,
                    paper_portfolio_id=paper_portfolio_id,
                    instrument_id=intent.instrument_id,
                    status=PaperOrderStatus.BLOCKED,
                    scheduled_execution_time=intent.eligible_execution_time,
                    eligible_execution_time=intent.eligible_execution_time,
                    requested_quantity=intent.approved_quantity_nullable or Decimal(0),
                    remaining_quantity=intent.approved_quantity_nullable or Decimal(0),
                    execution_model_version="NEXT_ELIGIBLE_SESSION_OPEN_WITH_CONFIGURED_FRICTION_V0",
                    idempotency_key=f"{intent.idempotency_key}:approval-missing",
                    rejection_reason_nullable="APPROVAL_MISSING",
                )
                self.repository.orders[blocked.paper_order_id] = blocked
                orders.append(blocked)
                continue
            if intent.intent_status != PaperIntentStatus.APPROVED:
                continue
            approval = self.repository.approvals.get(intent.paper_trade_intent_id)
            if approval is None or not approval.is_valid_at(execution_time):
                blocked = PaperOrder(
                    paper_trade_intent_id=intent.paper_trade_intent_id,
                    paper_portfolio_id=paper_portfolio_id,
                    instrument_id=intent.instrument_id,
                    status=PaperOrderStatus.BLOCKED,
                    scheduled_execution_time=intent.eligible_execution_time,
                    eligible_execution_time=intent.eligible_execution_time,
                    requested_quantity=intent.approved_quantity_nullable or Decimal(0),
                    remaining_quantity=intent.approved_quantity_nullable or Decimal(0),
                    execution_model_version="NEXT_ELIGIBLE_SESSION_OPEN_WITH_CONFIGURED_FRICTION_V0",
                    idempotency_key=intent.idempotency_key,
                    rejection_reason_nullable="APPROVAL_MISSING_OR_EXPIRED",
                )
                self.repository.orders[blocked.paper_order_id] = blocked
                orders.append(blocked)
                continue
            if intent.idempotency_key in self.repository.executed_idempotency_keys:
                raise ValueError("DUPLICATE_ORDER_EXECUTION")
            self.repository.executed_idempotency_keys.add(intent.idempotency_key)
            reference_price = reference_prices.get(intent.instrument_id)
            if reference_price is None:
                status = PaperOrderStatus.REJECTED
                reason = "REFERENCE_PRICE_MISSING"
                filled_quantity = Decimal(0)
            else:
                status = PaperOrderStatus.FILLED
                reason = None
                filled_quantity = intent.approved_quantity_nullable or Decimal(0)
            order = PaperOrder(
                paper_trade_intent_id=intent.paper_trade_intent_id,
                paper_portfolio_id=paper_portfolio_id,
                instrument_id=intent.instrument_id,
                status=status,
                scheduled_execution_time=intent.eligible_execution_time,
                eligible_execution_time=intent.eligible_execution_time,
                submitted_at_nullable=execution_time,
                executed_at_nullable=execution_time if status == PaperOrderStatus.FILLED else None,
                requested_quantity=intent.approved_quantity_nullable or Decimal(0),
                filled_quantity=filled_quantity,
                remaining_quantity=Decimal(0)
                if status == PaperOrderStatus.FILLED
                else filled_quantity,
                execution_model_version="NEXT_ELIGIBLE_SESSION_OPEN_WITH_CONFIGURED_FRICTION_V0",
                idempotency_key=intent.idempotency_key,
                rejection_reason_nullable=reason,
            )
            self.repository.orders[order.paper_order_id] = order
            orders.append(order)
            if status == PaperOrderStatus.FILLED and reference_price is not None:
                fill_price = self.slippage.fill_price(reference_price, intent.side)
                slippage_amount = money(abs(fill_price - reference_price) * filled_quantity)
                gross = money(fill_price * filled_quantity)
                costs = self.cost_model.calculate(gross, intent.side, self.cost_schedule)
                self.repository.paper_portfolios[paper_portfolio_id].buy(
                    intent.instrument_id,
                    filled_quantity,
                    fill_price,
                    costs.total_cost,
                )
                fill = PaperFill(
                    paper_order_id=order.paper_order_id,
                    paper_portfolio_id=paper_portfolio_id,
                    instrument_id=intent.instrument_id,
                    fill_time=execution_time,
                    fill_quantity=filled_quantity,
                    reference_price=reference_price,
                    reference_price_time=execution_time,
                    simulated_fill_price=fill_price,
                    gross_notional=gross,
                    slippage_amount=slippage_amount,
                    slippage_bps=self.slippage.buy_slippage_bps,
                    cost_total=costs.total_cost,
                    net_cash_effect=money(-(gross + costs.total_cost)),
                    settlement_date=execution_time.date(),
                    fill_status="FILLED",
                )
                self.repository.fills[fill.paper_fill_id] = fill
                self.repository.ledger.setdefault(paper_portfolio_id, []).append(
                    PaperLedgerEntry(
                        paper_portfolio_id=paper_portfolio_id,
                        ledger_type="PAPER_CASH_LEDGER",
                        event_time=execution_time,
                        amount=fill.net_cash_effect,
                        balance_after=self.repository.paper_portfolios[paper_portfolio_id].cash,
                        source_reference=fill.paper_fill_id,
                        configuration_version=intent.configuration_version,
                        correlation_id=correlation_id,
                    )
                )
                self.repository.intents[intent.paper_trade_intent_id] = replace(
                    intent,
                    intent_status=PaperIntentStatus.COMPLETED,
                    updated_at=utc_now(),
                )
                self.audit_log.record(
                    event_type="PAPER_ORDER_FILLED",
                    entity_type="PaperOrder",
                    entity_id=order.paper_order_id,
                    actor_type="SYSTEM_SERVICE",
                    actor_id="paper-execution-service",
                    action="SIMULATE_FILL",
                    before_state=None,
                    after_state={
                        "classification": list(PAPER_LABELS),
                        "fill_id": fill.paper_fill_id,
                    },
                    correlation_id=correlation_id,
                )
        persist_if_supported(self.repository)
        return orders

    def value_and_reconcile(
        self, paper_portfolio_id: str, prices: dict[str, Decimal], inject_failure: bool = False
    ) -> PaperNavSnapshot:
        paper = self.repository.paper_portfolios[paper_portfolio_id]
        market_value = money(
            sum(
                (qty * prices.get(inst, Decimal(0)) for inst, qty in paper.positions.items()),
                Decimal(0),
            )
        )
        nav = money(paper.cash + paper.unsettled_receivables + market_value)
        observed = money(nav + (Decimal(1) if inject_failure else Decimal(0)))
        recon = self.reconciliation.reconcile(paper_portfolio_id, nav, observed, new_id("corr"))
        previous_hwm = max(
            [snap.high_water_mark for snap in self.repository.nav.get(paper_portfolio_id, [])],
            default=nav,
        )
        hwm = max(previous_hwm, nav)
        drawdown = Decimal(0) if hwm == 0 else money((nav - hwm) / hwm)
        snapshot = PaperNavSnapshot(
            paper_portfolio_id=paper_portfolio_id,
            valuation_time=utc_now(),
            available_cash=paper.cash,
            unsettled_receivables=paper.unsettled_receivables,
            market_value=market_value,
            nav=nav,
            high_water_mark=money(hwm),
            drawdown=drawdown,
            reconciliation_status=recon.status,
        )
        self.repository.nav.setdefault(paper_portfolio_id, []).append(snapshot)
        persist_if_supported(self.repository)
        return snapshot

    def activate_kill_switch(
        self, switch_type: KillSwitchType, scope_id: str, reason: str
    ) -> KillSwitch:
        switch = KillSwitch(
            switch_type=switch_type, scope_id=scope_id, is_active=True, reason=reason
        )
        self.repository.kill_switches[switch.id] = switch
        for intent_id, intent in list(self.repository.intents.items()):
            if intent.intent_status in {
                PaperIntentStatus.PENDING_APPROVAL,
                PaperIntentStatus.APPROVED,
            }:
                self.repository.intents[intent_id] = replace(
                    intent,
                    intent_status=PaperIntentStatus.BLOCKED,
                    reason_codes_json=[*intent.reason_codes_json, "KILL_SWITCH_ACTIVE"],
                )
        persist_if_supported(self.repository)
        return switch

    def evidence_package(self, paper_portfolio_id: str) -> PaperEvidencePackage:
        configs = self.repository.active_strategy_configs(paper_portfolio_id)
        strategy_config_id = (
            configs[0].paper_strategy_config_id if configs else "NO_ACTIVE_STRATEGY"
        )
        package = PaperEvidencePackage(
            paper_portfolio_id=paper_portfolio_id,
            paper_strategy_config_id=strategy_config_id,
            generated_at=utc_now(),
            payload_json={
                "portfolio": asdict(self.repository.portfolios[paper_portfolio_id]),
                "intents": [
                    asdict(intent)
                    for intent in self.repository.intents.values()
                    if intent.paper_portfolio_id == paper_portfolio_id
                ],
                "orders": [
                    asdict(order)
                    for order in self.repository.orders.values()
                    if order.paper_portfolio_id == paper_portfolio_id
                ],
                "fills": [
                    asdict(fill)
                    for fill in self.repository.fills.values()
                    if fill.paper_portfolio_id == paper_portfolio_id
                ],
                "incidents": [
                    asdict(incident)
                    for incident in self.repository.incidents.values()
                    if incident.paper_portfolio_id == paper_portfolio_id
                ],
            },
        )
        self.repository.evidence[package.id] = package
        persist_if_supported(self.repository)
        return package


def all_admission_evidence() -> dict[str, bool]:
    return {flag: True for flag in PaperAdmissionService.required_flags}


def all_readiness_green() -> dict[str, bool]:
    return {flag: True for flag in PaperDataReadinessService.required_flags}
