# Limitations And Deferred Scope

Implemented as a deterministic paper-trading scaffold with an in-memory repository and a local SQLite-backed repository/queue adapter for operational hardening checks.

Deferred:

- SQLAlchemy/PostgreSQL persistence wiring.
- Redis or production queue wiring.
- Real browser dashboard interaction tests.
- Full corporate-action paper ledger.
- Full drift distribution comparison.
- Full paper review workflow.
- Production exchange-calendar source and holiday governance beyond fixtures.
- Any broker or live execution capability.
