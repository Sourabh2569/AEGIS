from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from aegis.live_trading.domain import (
    LiveIncident,
    LiveIncidentType,
    LiveReconciliationRecord,
)
from aegis.live_trading.services import LiveTradingRepository
from aegis.shared.ids import new_id
from aegis.shared.money import money
from aegis.shared.time import utc_now

# Anything within this fraction of expected_nav is treated as GREEN --
# real settlement timing/rounding differences of a few paise are not a
# real mismatch. A genuine discrepancy (a missed fill, a corporate action,
# a real reconciliation problem) will be far larger than this in practice.
MATERIAL_MISMATCH_TOLERANCE = Decimal("0.005")


class LiveReconciliationService:
    """Unlike PaperReconciliationService (documented as self-referential --
    no independent data source to compare against), this genuinely calls
    the broker adapter's real get_positions()/get_margins() for an
    independent comparison against the internal ledger's expected NAV.

    Deliberately does NOT hardcode any assumption about Kite Connect's
    exact real response schema for positions()/margins() -- that hasn't
    been verified against a real account yet (only data-only Kite access
    exists today). Instead, the caller supplies observed_nav_calculator,
    a real function that knows how to turn the broker's actual raw
    response into a single NAV figure once real credentials and a real
    verified schema exist. This keeps the service itself honest and fully
    testable against fakes now, without guessing at a schema that could be
    wrong."""

    def __init__(
        self,
        *,
        repository: LiveTradingRepository,
        order_adapter: Any,
        audit_log: Any,
        observed_nav_calculator: Callable[[dict[str, Any], dict[str, Any]], Decimal],
    ) -> None:
        self.repository = repository
        self.order_adapter = order_adapter
        self.audit_log = audit_log
        self.observed_nav_calculator = observed_nav_calculator

    def reconcile(
        self, *, live_portfolio_id: str, expected_nav: Decimal, correlation_id: str | None = None
    ) -> LiveReconciliationRecord:
        correlation_id = correlation_id or new_id("corr")
        portfolio = self.repository.portfolios[live_portfolio_id]

        try:
            positions = self.order_adapter.get_positions()
            margins = self.order_adapter.get_margins()
            observed_nav = money(self.observed_nav_calculator(positions, margins))
            reason_codes: list[str] = []
            status = self._status_for(expected_nav, observed_nav)
        except Exception as exc:  # noqa: BLE001 -- fail closed: can't verify means don't trust
            observed_nav = money(Decimal(0))
            status = "RED"
            reason_codes = [f"RECONCILIATION_CALL_FAILED:{exc}"]

        if status == "RED" and not reason_codes:
            reason_codes = ["NAV_MISMATCH"]

        record = LiveReconciliationRecord(
            live_portfolio_id=live_portfolio_id,
            reconciliation_time=utc_now(),
            expected_nav=money(expected_nav),
            observed_nav=observed_nav,
            status=status,
            reason_codes=reason_codes,
        )
        self.repository.add_reconciliation(record)

        if status == "RED":
            incident = LiveIncident(
                live_portfolio_id=live_portfolio_id,
                incident_type=LiveIncidentType.RECONCILIATION_INCIDENT,
                severity="CRITICAL",
                description=(
                    f"Real reconciliation mismatch: expected NAV {expected_nav}, "
                    f"broker-reported NAV {observed_nav}."
                ),
                status="OPEN",
                reason_codes=reason_codes,
            )
            self.repository.save_incident(incident)
            self.repository.save_portfolio(
                portfolio.freeze("RECONCILIATION_MISMATCH").reset_clean_fill_count()
            )
            self.audit_log.record(
                event_type="LIVE_RECONCILIATION_MISMATCH",
                entity_type="LiveReconciliationRecord",
                entity_id=record.id,
                actor_type="SYSTEM",
                actor_id="live_reconciliation_service",
                action="FREEZE_ON_RED_RECONCILIATION",
                before_state=None,
                after_state={"expected_nav": str(expected_nav), "observed_nav": str(observed_nav)},
                correlation_id=correlation_id,
            )

        return record

    def _status_for(self, expected_nav: Decimal, observed_nav: Decimal) -> str:
        if expected_nav == 0:
            return "GREEN" if observed_nav == 0 else "RED"
        deviation = abs(expected_nav - observed_nav) / abs(expected_nav)
        return "GREEN" if deviation <= MATERIAL_MISMATCH_TOLERANCE else "RED"
