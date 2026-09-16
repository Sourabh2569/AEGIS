from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from aegis.live_trading.domain import (
    LiveCapitalTier,
    LiveExecutionPreflight,
    LiveOrderIntent,
    LivePortfolio,
    LivePortfolioStatus,
)
from aegis.paper_trading.services import PaperTradingCalendarService
from aegis.risk.engine import KillSwitch, RiskProfileVersion

if TYPE_CHECKING:
    # Deferred to a type-checking-only import: services.py (the
    # orchestrator/gateway layer) needs to import THIS module, so this
    # module must not import back from services.py at runtime -- the type
    # hint below is still fully checked by mypy/pyright, just never
    # actually executed.
    from aegis.live_trading.services import LiveTradingRepository


class ExecutionPreflightGate:
    """The final real guard before a broker call, run strictly AFTER
    PositionSizingEngine.assess() (unchanged, shared risk-sizing code) at
    execution time -- it re-validates a different set of concerns than
    sizing does: has anything changed between approval and now (kill
    switches, market hours, broker health), not "how much should this
    position be." Generalizes the exact "final guard" pattern paper trading
    already uses in execute_approved_orders() (which re-checks kill
    switches even though approve() already ran once), because a real
    broker call is irreversible in a way a simulated paper fill never was.

    Every check runs independently; an exception during any single check
    counts as that check failing and never propagates past it -- fail
    closed on uncertainty, matching Document 007's own closing line ("when
    uncertainty exists, do not submit the order")."""

    def __init__(
        self,
        *,
        repository: LiveTradingRepository,
        calendar: PaperTradingCalendarService,
        order_adapter: Any,
        risk_profile: RiskProfileVersion | None = None,
    ) -> None:
        self.repository = repository
        self.calendar = calendar
        self.order_adapter = order_adapter
        self.risk_profile = risk_profile or RiskProfileVersion()

    def check(
        self,
        *,
        intent: LiveOrderIntent,
        portfolio: LivePortfolio,
        execution_time: datetime,
        entry_price: Decimal,
        existing_deployed_notional: Decimal,
        kill_switches: list[KillSwitch],
    ) -> LiveExecutionPreflight:
        results: dict[str, bool] = {}
        failures: list[str] = []

        def run(name: str, fn: Any) -> None:
            try:
                ok = bool(fn())
            except Exception:  # noqa: BLE001 -- fail closed: any exception while
                # evaluating a check is itself a failure of that check, never
                # allowed to propagate and skip the remaining checks.
                ok = False
            results[name] = ok
            if not ok:
                failures.append(name)

        proposed_quantity = intent.approved_quantity_nullable or intent.proposed_quantity
        proposed_notional = proposed_quantity * entry_price

        def check_kill_switches() -> bool:
            # Same scope-matching shape paper trading already uses
            # (scope_id in {GLOBAL, portfolio, instrument}), extended with
            # the order adapter's own name -- the one genuinely new scope
            # dimension a broker-aware system introduces that pure
            # portfolio/instrument-scoped paper trading never needed
            # (BROKER_ADAPTER_KILL_SWITCH's natural scope). Deliberately
            # does not branch on switch_type for matching -- paper trading
            # doesn't either; a switch's type is a label, its scope_id is
            # what actually gates.
            relevant_scopes = {
                "GLOBAL",
                portfolio.live_portfolio_id,
                intent.instrument_id,
                self.order_adapter.name,
            }
            return not any(
                switch.is_active and switch.scope_id in relevant_scopes for switch in kill_switches
            )

        def check_portfolio_status() -> bool:
            return portfolio.status not in {
                LivePortfolioStatus.CAPITAL_PRESERVATION,
                LivePortfolioStatus.FROZEN,
                LivePortfolioStatus.PAUSED,
            }

        def check_market_open() -> bool:
            return execution_time.date() in self.calendar.sessions

        def check_approval_valid() -> bool:
            approval = self.repository.approvals.get(intent.live_order_intent_id)
            return approval is not None and approval.is_valid_at(execution_time)

        def check_capital_cap() -> bool:
            if portfolio.capital_tier != LiveCapitalTier.PILOT:
                return True
            return (existing_deployed_notional + proposed_notional) <= portfolio.pilot_capital_cap

        def check_broker_healthy() -> bool:
            return bool(self.order_adapter.get_health_status().healthy)

        def check_idempotency() -> bool:
            return intent.idempotency_key not in self.repository.executed_idempotency_keys

        def check_minimum_notional() -> bool:
            # A real, not theoretical, check for a broadly diversified
            # rebalancing strategy: DiversifiedRiskOverlayStrategyV2 spreads
            # capital across the whole eligible universe, so individual
            # allocations can be small enough to fall under the risk
            # engine's own minimum_trade_notional floor. An order that
            # would round below it is blocked here with an honest reason
            # code, never silently rounded up to fabricate a fill.
            return proposed_notional >= self.risk_profile.minimum_trade_notional

        run("kill_switches", check_kill_switches)
        run("portfolio_status", check_portfolio_status)
        run("market_open", check_market_open)
        run("approval_valid", check_approval_valid)
        run("capital_cap", check_capital_cap)
        run("broker_healthy", check_broker_healthy)
        run("idempotency", check_idempotency)
        run("minimum_notional", check_minimum_notional)

        preflight = LiveExecutionPreflight(
            live_order_intent_id=intent.live_order_intent_id,
            live_portfolio_id=portfolio.live_portfolio_id,
            checked_at=execution_time,
            passed=not failures,
            check_results=results,
            failure_reasons=failures,
        )
        self.repository.save_preflight(preflight)
        return preflight
