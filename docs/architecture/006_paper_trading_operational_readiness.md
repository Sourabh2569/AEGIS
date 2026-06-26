# Paper Trading, Forward Validation And Operational Readiness

This reference is derived from AEGIS Document 006. Paper trading is a forward-only, production-like validation environment. Its purpose is not simulated profit; its purpose is to expose the gap between historical backtest assumptions and forward operational reality before capital is exposed.

Paper trading must remain separate from research, backtesting, future live-candidate review, and any future controlled live environment.

Mandatory principles:

- Paper trading is forward only.
- Original signals, data snapshots, risk assessments, order intents, simulated fills, and ledger events are immutable.
- Corrections are new events, never silent edits.
- Paper workflows must use the same governed data, feature, strategy, risk, portfolio, cost, slippage, settlement, corporate-action, audit, incident, and kill-switch components intended for production-like operation.
- Paper performance is not live performance.
- Paper completion is not automatic live approval.
- No paper service may contain live broker credentials, live order APIs, actual capital balances, or hidden execution pathways.

## Admission Gate

A strategy may enter paper trading only after formal admission review. Required evidence includes:

- Approved research family and hypothesis.
- Immutable strategy version.
- Completed backtest evidence package.
- Frozen experiment manifest.
- Dataset lineage and point-in-time integrity.
- Corporate-action, cost, slippage, settlement, risk, and position-sizing configuration.
- Market-regime compatibility and failure regimes.
- Robustness tests.
- Kill-switch test evidence.
- Monitoring and incident plans.
- Founder approval.

Automatic rejection applies when any core evidence is missing, mutable, unresolved, or affected by look-ahead bias, unversioned costs, unresolved corporate actions, reused holdout tuning, untested kill switches, or materially different paper versus backtest workflow.

## Paper Strategy Configuration

Paper strategy configuration becomes immutable after activation. Any change to strategy logic, risk profile, cost model, execution model, universe, or material policy requires a new configuration version. Historical paper records remain linked to the configuration that created them.

## Data And Workflow

Every paper decision preserves:

```text
event_time
available_time
ingested_time
decision_time
order_time
execution_time
settlement_time
```

Before each paper decision cycle, AEGIS must verify dataset status, provider license and health, freshness, instrument mapping, market calendar, required features, corporate-action status, frozen strategy configuration, risk-engine health, audit-log health, and inactive relevant kill switches.

Failure produces `NO_NEW_PAPER_ORDER`, data/risk/audit events, dashboard alert, reason code, and incident when severity requires it.

## Order Lifecycle And Approval

Paper orders use a governed lifecycle:

```text
DRAFT
PENDING_APPROVAL
APPROVED
REJECTED
SCHEDULED
ELIGIBLE
PARTIALLY_FILLED
FILLED
UNFILLED
CANCELLED
EXPIRED
BLOCKED
FAILED
```

`HUMAN_APPROVAL_REQUIRED=true` for every paper-trade intent. Approval cannot override hard risk controls, expires by policy, and does not survive material risk-state changes, data-quality failures, strategy pauses, or material configuration changes.

## Execution And Settlement

Default V1 model:

```text
NEXT_ELIGIBLE_SESSION_OPEN_WITH_CONFIGURED_FRICTION_V0
```

Every fill stores reference price, reference timestamp, slippage model, slippage amount, cost schedule, cost line items, settlement model, fill status, and reason codes.

Default settlement:

```text
T_PLUS_1_CONSERVATIVE_V0
```

Sale proceeds become unsettled receivables and cannot fund new purchases until settlement. `IMMEDIATE_SETTLEMENT_SIMULATION_V0` is restricted to engine/mechanics testing and explicit backtest comparability.

## Risk, Monitoring And Incidents

No paper order may be created or executed without a current risk assessment. Required gates include data eligibility, instrument eligibility, strategy eligibility, regime compatibility, position sizing, cash reserve, position/sector/cluster/liquidity limits, drawdown state, kill switches, and approval.

Paper monitoring covers:

- Data health.
- System health.
- Execution quality.
- Portfolio risk.
- Strategy behaviour.

Backtest-to-paper comparison tracks signal frequency, candidate quality, execution timing, slippage, cost drag, turnover, fill rate, drawdown, exposure, cash weight, regime compatibility, and strategy performance distribution.

Divergence states:

```text
WITHIN_EXPECTATION
WATCH
MATERIAL_DIVERGENCE
CRITICAL_DIVERGENCE
```

Critical incidents immediately freeze new paper orders when audit logging, risk engine, data quality, reconciliation, corporate actions, duplicate fills, configuration drift, unauthorized action, kill switches, or data-timing integrity fail.

## Paper Portfolio State Machine

Required states:

```text
DRAFT
SETUP_PENDING
READY
ACTIVE
CAUTION
DEFENSIVE
CAPITAL_PRESERVATION
PAUSED
FROZEN
COMPLETED
RETIRED
FAILED
```

Completion permits only structured review. Possible review outcomes include continuing paper trading, extending observation, reducing allocation, pausing and revalidating, retiring, or future live-candidate review. Future live-candidate review is not live approval.

## Security Boundary

Paper trading must never become disguised live trading. It must not contain live broker credentials, live order APIs, live account tokens, real capital balances, live holdings, production execution permissions, or hidden execution pathways.

## Deferred Implementation

Document 006 is binding architecture for a future paper-trading sprint. It is not implemented in Sprint 2. Current Sprint 2 outputs remain:

```text
RESEARCH_ONLY
NOT_VALIDATED
NOT_PAPER_TRADING_ELIGIBLE
NOT_LIVE_TRADING_ELIGIBLE
```
