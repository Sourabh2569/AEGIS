# AEGIS Project Inventory

This repository is organized as a full-stack, read-only/live-readiness investment intelligence platform. It intentionally separates product code, architecture records, test fixtures, runtime artifacts, and local-only generated state.

## Product Source

- `apps/api/` - FastAPI application surface, governance endpoints, paper operations APIs, live-readonly data endpoints, and Alembic schema sketches.
- `apps/web/` - Next.js dashboard for command center, dataset lineage, provider licensing, feature versioning, research lab, risk attribution, drift statistics, corporate actions, paper operations, live readiness, incidents, compliance, and database internals.
- `apps/worker/` - Worker entrypoint for asynchronous or queued operational processes.
- `packages/` - Domain packages for shared types, provider adapters, ingestion, data quality, instrument master, backtesting, feature engine, research registry, portfolio logic, risk, and paper trading.

## Architecture And Governance

- `docs/architecture/` - System architecture records, data governance, research validation, backtesting, risk and position sizing, paper trading, operational readiness, live compliance, and live-readonly market data integration.
- `docs/adr/` - Architecture decision records covering immutability, timestamps, live-execution lockout, event-driven clocks, settlement, cost/slippage, risk caps, approvals, reconciliation, drift, and evidence packages.
- `docs/sprint_0/` - Foundation implementation plan and architecture gap report.
- `docs/sprint_1a/` - Event-driven backtesting implementation details, assumptions, ledgers, eligibility, API reference, and test scenarios.
- `docs/sprint_2/` - Research lab, feature contracts, experiment manifests, risk sizing, attribution, settlement, corporate actions, and baselines.
- `docs/sprint_3/` - Paper portfolio operations, operational hardening, approval workflow, kill switch runbook, reconciliation, drift detection, incidents, dashboards, and acceptance criteria.
- `docs/frontend_redesign/` - Premium dashboard redesign system: information architecture, component inventory, design tokens, navigation, charts, responsive behavior, accessibility, visual regression, and completion checklist.
- `docs/runbooks/` - Operational response guides for failed ingestion, provider license expiry, database migration failure, dataset red state, emergency stop, object storage outage, and environment reset.

## Data Fixtures

- `sample_data/instruments/` - Instrument master fixture.
- `sample_data/eod_prices/` - EOD OHLCV fixture.
- `sample_data/backtesting/` - Backtesting fixture set, including valid and invalid data cases.
- `sample_data/sprint_2/` - Research workflow fixtures for instruments, prices, benchmark, calendar, memberships, costs, corporate actions, and sector clusters.
- `sample_data/sprint_3/` - Forward-only paper operations fixtures for instruments, prices, calendars, provider health, risk profile, strategy configuration, costs, universe memberships, and corporate actions.

## Infrastructure And Automation

- `.github/workflows/ci.yml` - GitHub Actions workflow for continuous verification.
- `docker-compose.yml` - Local service orchestration for API, dashboard, and supporting services.
- `infrastructure/docker/` - Docker build assets.
- `infrastructure/scripts/` - Scenario runners for ingestion, backtesting, research, paper trading, operational hardening, failure scenarios, and live-readonly data sync.
- `Makefile` - Common local development commands.

## Tests

- `tests/unit/` - Unit coverage for Sprint 0 guardrails, Sprint 1A backtesting, Sprint 2 research, Sprint 3 paper trading, and live-readonly market data.
- `tests/integration/` - API integration coverage for Sprint 3 paper APIs and live-readonly provider APIs.
- `apps/web/app/page.runtime.test.mjs` - Dashboard runtime module exposure test.

## Brand And Static Assets

- `apps/web/public/brand/aegis-logo.png` - Current AEGIS logo lockup used by the Next.js dashboard.

## Local-Only Artifacts

The following are deliberately excluded from GitHub by `.gitignore`:

- `.venv/`, `.pip-cache/`, `.pnpm-store/`, `node_modules/`, `.next/`
- `__pycache__/`, `.pytest_cache/`, Python bytecode, and coverage output
- `work/`, local SQLite databases, WAL/SHM files, raw runtime object stores, and generated operational state
- `outputs/` generated local HTML exports
- `.env` and local secrets
