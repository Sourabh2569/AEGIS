# Sprint 1A Gap Report

Existing gaps found before implementation:

- Required architecture docs `001` through `004` were missing and were added as binding local references.
- Sprint 0 has a SQL migration sketch but no live Alembic environment.
- Sprint 0 has in-memory repositories, not PostgreSQL-backed SQLAlchemy repositories.
- Sprint 0 worker is a placeholder loop, not a real queue worker.
- Sprint 0 has no curated EOD market-data repository abstraction.
- Sprint 0 has no trading-calendar reader.
- Local environment lacks `pytest` and `npm`, so full toolchain execution may be blocked.

Minimum compatible Sprint 1A extensions:

- In-memory backtest repository.
- Deterministic fixture-backed market data and calendar readers.
- Synchronous idempotent backtest job service.
- SQL migration sketch for future persistence.
- Unit tests covering accounting, causality, and failure modes.
