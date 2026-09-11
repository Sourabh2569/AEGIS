# 010 Incident Response Runbook

Grounded in what's actually wired in the code today (paper-trading only, per Document 007's phased sequencing), not generic incident-response boilerplate. Updated as real mechanisms are added.

## What actually happens today when something goes wrong

**Reconciliation → incident → freeze is real, but nothing triggers it in production.** `PaperReconciliationService.reconcile()` creates a real `PaperTradingIncident` and freezes the affected portfolio (`PaperPortfolio.status -> FROZEN`) whenever a reconciliation comes back RED. This is a genuine, tested mechanism (`packages/paper_trading/aegis/paper_trading/services.py`). But `value_and_reconcile()` -- the only thing that calls `reconcile()` -- has exactly one caller in the whole codebase: a unit test, with an explicit `inject_failure=True`. **No scheduled job, API endpoint, or lifecycle hook calls it for real.** Even if something did call it in production, it computes "expected" and "observed" NAV from the same in-memory state -- there's no independent source of truth (a real broker's reported positions/cash) to diverge from yet. A "Reconcile Now" button would always pass. This is intentionally not built until Phase 2's broker adapter exists (see `docs/architecture/009_live_readiness_dossier.md`, Gate 5).

**Kill switches are real and now have real teeth**, as of this pass:
- `POST /api/v1/kill-switches/{scope}/activate` (role: `FOUNDER`, `RISK_REVIEWER`, or `PAPER_TRADING_OPERATOR`, requires a real `reason`) creates a real, persisted `KillSwitch` and *immediately* sweeps every currently `PENDING_APPROVAL`/`APPROVED` intent to `BLOCKED`.
- `execute_approved_orders` now also checks active kill switches directly (this pass's fix) -- so an intent that gets re-approved after a kill switch swept it (a real gap: `PaperApprovalService.approve()` doesn't check kill switches before re-approving) still can't reach execution. This is the final guard.
- `POST /api/v1/kill-switches/{id}/deactivate` (role: `FOUNDER` or `RISK_REVIEWER`, requires a real `reason`) now actually clears `is_active` -- it used to be a complete no-op. **Deactivation does not un-block previously-swept intents** -- that status overwrite has no history to restore from by design, so a still-valid intent must be re-proposed and individually re-reviewed. This is deliberate: automatically resurrecting a batch of paused decisions on deactivation would defeat the point of requiring a documented reason to deactivate.
- Per ADR 0026, kill switches apply only to paper/research order generation and execution -- "No live execution exists" for them to gate yet.
- 9 kill-switch types now exist (`packages/risk/aegis/risk/engine.py:KillSwitchType`), matching Document 007's full list. Only the original 5 (`GLOBAL_TRADING`, `PORTFOLIO`, `STRATEGY`, `INSTRUMENT`, `DATA_PROVIDER`) are actually consulted anywhere -- the 4 added this pass (`BROKER_ADAPTER`, `RISK_ENGINE`, `COMPLIANCE_HOLD`, `SECURITY_INCIDENT`) are cataloged for the vocabulary but have no real consumer yet (no broker adapter, no compliance-hold workflow, no security-incident auto-freeze).
- **Known open question, not resolved here**: `DATA_PROVIDER_KILL_SWITCH`'s scope-matching is ambiguous. `PositionSizingEngine.assess()`'s current check is `switch.scope_id in {"GLOBAL", portfolio_id, strategy_id, instrument_id}` -- a data-provider switch scoped to a provider name (e.g. `"kite_connect"`) would never match this set. Whether a data-provider kill switch should block globally, by instrument, or needs its own matching logic is a real design decision for whoever wires a second data provider in, not fixed here.

**Incidents can be viewed and resolved in the Cockpit** (`/operations`, new this pass) -- previously the Cockpit had zero UI for either kill switches or incidents; `portfolio/page.tsx` only ever rendered open incidents as plain read-only text.

**A related, adjacent gap noticed but not fixed in this pass**: `POST /api/v1/paper-incidents/{id}/resolve` has no role-auth dependency and no required reason, unlike the kill-switch endpoints fixed here. Given incidents can freeze a real portfolio, resolving one arguably deserves the same treatment (a role gate + a documented reason) -- flagged for a future pass, not bundled into this one since it wasn't part of what was scoped.

## What an operator should actually do today

1. **If you see an open incident** in the Cockpit's Operations page: read the real `description`/`reason_codes`, check whether the affected portfolio is really `FROZEN` (`GET /api/v1/paper-portfolios/{id}`), and only resolve it once you understand why it fired -- resolving does not un-freeze the portfolio (that's a separate, explicit `resume` action with its own real state check).
2. **If you need to stop everything right now**: activate a `GLOBAL_TRADING_KILL_SWITCH` scoped to `"GLOBAL"` with a real reason. This immediately blocks every pending/approved intent system-wide and blocks any newly-approved-but-not-yet-executed order from executing.
3. **If you need to stop one portfolio/instrument**: activate a `PORTFOLIO_KILL_SWITCH`/`INSTRUMENT_KILL_SWITCH` scoped to that portfolio's or instrument's real id.
4. **Deactivating**: only after real review -- write down *why* it's safe to resume in the required reason field (this is what "documented review" means here, not a formality). Remember any intents the switch blocked stay blocked; re-review and re-propose them individually if still valid.
5. **This is all paper-trading only.** None of this reaches a real broker, real order, or real capital -- `LIVE_EXECUTION_ENABLED`, `BROKER_ORDER_ACCESS`, and `LIVE_BROKER_CONNECTION_ENABLED` remain hard-blocked at startup (`packages/configuration/aegis/configuration/settings.py`).

## What's still missing for real operational readiness (Gate 5, not yet passed)

- A real trigger for reconciliation, and a real independent source of truth to reconcile against (blocked on Phase 2's broker adapter).
- Monitoring/alerting -- there is currently none. Issues are found by an operator manually opening the Cockpit's Operations page. No automated notification exists for a newly-created incident or a newly-active kill switch.
- Role/reason gating on incident resolution (noted above).
- Wiring the 4 newly-cataloged kill-switch types into real scope-matching once their corresponding systems (broker adapter, compliance-hold workflow, security-incident detection) exist.
