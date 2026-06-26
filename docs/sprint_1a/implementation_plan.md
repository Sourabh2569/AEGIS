# Sprint 1A Implementation Plan

1. Document Sprint 0 mapping and gaps.
2. Add shared Decimal money, timestamp, ID, error, and reconciliation helpers.
3. Add Sprint 1A domain models for runs, events, portfolios, ledgers, order intents, orders, fills, and NAV snapshots.
4. Add read-only market-data and trading-calendar repository abstractions backed by deterministic fixtures.
5. Implement data eligibility, instrument eligibility, next-session lookup, causality validation, and same-close protection.
6. Implement `NextEligibleSessionOpenExecutionModelV0`.
7. Implement event-driven runner with append-only event sequencing, fills, ledger entries, NAV snapshots, and reconciliation.
8. Add API endpoints and dashboard views without trading or recommendation language.
9. Add fixtures, tests, migration sketch, documentation, and runbooks.
