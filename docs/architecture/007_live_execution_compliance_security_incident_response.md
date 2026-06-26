# AEGIS Document 007

Live Execution, Compliance, Security & Incident Response Constitution.

Status: foundational control document.

Document 007 does not authorize live execution. It defines the gates and controls that must exist before a future broker-connected pilot can even be considered.

Core operating principle:

```text
LIVE_EXECUTION_ENABLED = false
```

Live execution is a restricted operational privilege, not a feature toggle.

## Current Prohibitions

AEGIS remains limited to research, backtesting, paper trading, and operational validation. It is not authorized to connect to a broker, store broker credentials, retrieve real balances or holdings, place real orders, cancel real orders, automate capital allocation, operate live strategies, or present simulated performance as live performance.

## Required Live Readiness Gates

1. Research integrity.
2. Paper-trading evidence.
3. Portfolio and risk readiness.
4. Security readiness.
5. Operational readiness.
6. Legal and compliance readiness.
7. Governance readiness.
8. Controlled live pilot readiness.

No strategy may enter live candidacy until every gate is passed and evidenced.

## Required Live Architecture

```text
Governed Market Data
Point-in-Time Feature Engine
Approved Strategy Version
Portfolio Construction
Risk Assessment Engine
Human Approval Workflow
Live Order Intent Registry
Execution Preflight Gate
Execution Gateway
Broker-Specific Adapter
Broker Acknowledgement
Order Status Monitor
Trade and Settlement Reconciliation
Portfolio Ledger and Audit Trail
```

No direct `Strategy -> Broker API` path is permitted.

## Mandatory Controls

- Dedicated execution gateway.
- Broker-specific isolated adapters.
- Human approval for every live order.
- Live preflight before every real order.
- Two-person approval for material actions.
- Fail-closed behavior for uncertainty.
- Strict portfolio, capital, exposure, cash, sector, cluster, settlement, and broker constraints.
- Dynamic risk states: `NORMAL`, `CAUTION`, `DEFENSIVE`, `CAPITAL_PRESERVATION`, `PAUSED`, `FROZEN`, `EMERGENCY_REVIEW`.
- Strong identity, access, secrets, environment, cryptography, and supply-chain security controls.
- Append-only tamper-evident audit records.
- Broker, order, trade, position, cash, settlement, and corporate-action reconciliation.
- Material reconciliation mismatch freezes the affected live portfolio.
- Incident response prioritizes capital protection, containment, evidence preservation, facts, reconciliation, and controlled recovery.
- Kill switches for global live execution, portfolio, strategy, instrument, broker adapter, data provider, risk engine, compliance hold, and security incidents.

## Future Data Model

Document 007 requires future entities including:

- `LivePortfolio`
- `LivePortfolioConfiguration`
- `LiveStrategyConfiguration`
- `LiveBrokerAccountReference`
- `BrokerAdapterConfiguration`
- `LiveOrderIntent`
- `LiveExecutionPreflight`
- `LiveOrder`
- `LiveOrderAcknowledgement`
- `LiveFill`
- `LiveSettlementRecord`
- `LiveCashLedger`
- `LivePositionLedger`
- `LiveCorporateActionLedger`
- `LiveNavSnapshot`
- `LiveExposureSnapshot`
- `LiveRiskSnapshot`
- `LiveReconciliationRecord`
- `LiveComplianceCheck`
- `LiveApproval`
- `LiveIncident`
- `LiveEvidencePackage`
- `LivePilotReview`
- `BrokerHealthSnapshot`
- `ExecutionGatewayEvent`

No entity may store raw credentials in plain text.

## Roadmap

Phase 1: compliance, security, governance foundation.

Phase 2: broker adapter sandbox foundation.

Phase 3: reconciliation and operational controls.

Phase 4: controlled live pilot readiness.

Phase 5: limited live pilot only after explicit founder, risk, security, compliance, and legal approval.

When uncertainty exists:

```text
Do not submit the order.
```
