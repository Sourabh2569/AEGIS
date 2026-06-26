# AEGIS System Architecture

AEGIS is a modular monolith. API, worker, provider adapters, data governance, backtesting, portfolio accounting, and dashboard modules share one repository and communicate through explicit service and repository interfaces.

Sprint 1A extends the foundation with deterministic event-driven backtesting only. It does not add strategy generation, broker execution, live trading, paper trading, or recommendation capabilities.

Core safety rules:

- Fail closed when governed data, auditability, causality, or ledger reconciliation is unavailable.
- Use internal immutable instrument IDs.
- Preserve all material events through append-only event logs and audit events.
- Treat Sprint 1A results as foundation simulations only.
