# Sprint 3 Reuse Matrix

| Capability | Reused Module |
| --- | --- |
| Data eligibility | Sprint 0 `DatasetVersion`, `ProviderLicense`; Sprint 3 readiness service |
| Feature calculation | `packages/feature_engine/aegis/feature_engine/engine.py` |
| Strategy evaluation | `packages/strategies/aegis/strategies/baselines.py` |
| Portfolio construction | Sprint 2 risk-capped equal-weight mechanics |
| Risk assessment | `packages/risk/aegis/risk/engine.py` |
| Position sizing | `PositionSizingEngine` |
| Cost calculation | `CostModel` |
| Slippage calculation | `FixedBpsSlippageModelV0` |
| Settlement | `ResearchPortfolio` T+1 mechanics plus Sprint 3 paper ledger |
| Corporate actions | Sprint 3 supported/unsupported fixture checks |
| Ledger accounting | Sprint 3 append-only paper ledger records |
| NAV valuation | Sprint 3 reconciliation service using shared Decimal money helpers |
| Audit logging | Sprint 0 `AuditLog` |
