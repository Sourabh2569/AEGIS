# Live Trading Operations

Operational reference for `packages/live_trading/`. See `docs/architecture/007_live_execution_compliance_security_incident_response.md` for the governing constitution and `docs/architecture/009_live_readiness_dossier.md` for current gate status -- this document is "how to operate it," not "whether it's ready to."

**Everything in this pipeline is categorically inert until the founder personally completes Gate 6 (SEBI/Zerodha compliance) and files a dated Gate 7 sign-off, then edits `Settings.validate_startup()` themselves.** No procedure below can change that; it exists so that day, when it comes, is not the first time anyone has read it.

## Starting the live order-status worker

```bash
AEGIS_WORK_DIR=work python apps/worker/live_trading_worker.py
```

A separate process from `apps/worker/main.py` (the paper-trading worker) -- starting one never starts or affects the other. Polls every open `LiveOrder` against the broker adapter every 5 seconds. Not wired into any default process list; the founder starts it manually. An on-demand alternative exists for local testing without running this process at all: `POST /api/v1/live-orders/poll`.

## The pilot capital cap

Set once at portfolio creation (`POST /api/v1/live-portfolios`, `pilot_capital_cap`), enforced by `ExecutionPreflightGate`'s `capital_cap` check: `existing_deployed_notional + proposed_order_notional <= pilot_capital_cap`, checked fresh against the whole batch on every execution attempt while `capital_tier == PILOT`.

**Why this session's own recommended figure (~₹4,00,000, not the originally-discussed ₹25,000-50,000 "token money") is what it is**: `DiversifiedRiskOverlayStrategyV2` (the strategy this pilot was built for) holds the *entire* eligible universe -- roughly 50 uncapped positions weighted by real proximity to each stock's own 252-day high. That breadth is exactly what made the strategy work in backtesting (see `docs/architecture/` strategy evidence from this session). At ₹25,000-50,000, real position-level math showed 37-40 of those 50 positions would round to zero shares -- the pilot would silently become a different, untested, price-biased strategy. At ₹4,00,000, only 5 of 50 round to zero (the highest-priced names), and zero positions fall below the risk engine's ₹500 minimum-trade-notional floor. If a future pilot targets a different, more concentrated strategy, redo this math for that strategy's real position count and price distribution -- do not assume this figure transfers.

## Clean fills and graduation

A "clean fill" is a real broker fill recorded with zero associated error: no rejection, no reconciliation mismatch. `LivePortfolio.clean_fill_count` increments by exactly one per clean fill (`LiveOrderStatusMonitor._record_fill`) and resets to zero on any broker rejection (`_record_rejection`) or RED reconciliation (`LiveReconciliationService.reconcile`). It does not reset on a pause or freeze -- only on evidence something actually went wrong.

Graduation (`PILOT` -> `FULL` capital tier) is **never automatic** -- Document 007 explicitly prohibits automating capital allocation. `POST /api/v1/live-portfolios/{id}/graduate` is the only code path that can do it:

- `Role.FOUNDER` only.
- Requires `clean_fill_count >= 20` (`GRADUATION_CLEAN_FILL_THRESHOLD`).
- Requires a non-empty `reason` and a positive `confirmed_new_capital_amount` -- the Cockpit's typed-confirmation control makes the founder retype the exact amount before the button enables, as a deliberate friction point for a one-way decision.
- Writes a `LIVE_PORTFOLIO_GRADUATED` audit event with the clean-fill count at the moment of graduation, so the decision is reconstructable later.

There is no path back from `FULL` to `PILOT` -- if that's ever needed, it's a new portfolio, not a state transition.

## Real order-cost consideration (not yet quantified)

Because `DiversifiedRiskOverlayStrategyV2` rebalances its whole ~50-position book monthly, a live pilot places on the order of dozens of small real orders per month, not the 1-8 a concentrated strategy would need. This is nowhere near SEBI's 10-orders/second threshold (Gate 6). It **is** a real, unquantified brokerage/slippage drag on ~₹6,000-8,000 average per-position allocations that the founder should check against Zerodha's actual fee schedule before ever going live -- this document does not estimate a number without real data to back it.

## Reading the audit trail

Every mutating action records an `AuditLog` event: `LIVE_INTENT_APPROVED`, `LIVE_INTENT_REJECTED` (both audited, unlike paper trading's approve-only asymmetry), `LIVE_ORDER_SUBMITTED`, `LIVE_ORDER_FILLED`, `LIVE_ORDER_REJECTED`, `LIVE_RECONCILIATION_MISMATCH`, `LIVE_PORTFOLIO_GRADUATED`, `LIVE_DECISION_CYCLE_SKIPPED`. Query via the shared `AuditLog` instance the API wires up (`audit_log` in `apps/api/aegis_api/main.py`) -- there is no separate live-trading-only audit store.

## What is deliberately not built yet

See Phase 1 of the live-trading plan for the full list and reasoning; the short version: `LiveBrokerAccountReference` (no real credentials to reference), a real-time websocket order-status stream (polling only), multi-broker support, and any form of automatic capital scaling. None of these are missing by oversight -- each was a deliberate scope decision, recorded so a future reader doesn't have to re-derive why.
