# Project AEGIS

AEGIS is an internal investment-intelligence operating foundation for Indian listed cash equities. Sprint 0 builds governed infrastructure only: provider registration, immutable raw-data capture, dataset governance, instrument identity, corporate-action workflow states, research-governance records, audit events, and an internal operations dashboard.

Sprint 0 explicitly does not include stock picking, strategies, backtesting, ML models, broker integration, paper-trading order flow, live execution, or buy/sell controls.

Sprint 1A adds a deterministic, event-driven, long-only, daily EOD backtesting and portfolio-ledger foundation. It supports manually created simulation order intents, next-eligible-session-open fills, Decimal cash and position ledgers, NAV snapshots, drawdown, reconciliation, and audit integration.

Every Sprint 1A result remains:

```text
FOUNDATION_SIMULATION_ONLY
NOT_VALIDATED
NOT_PAPER_TRADING_ELIGIBLE
NOT_LIVE_TRADING_ELIGIBLE
ZERO_COST_MODEL
IMMEDIATE_SETTLEMENT_SIMULATION
SINGLE_INSTRUMENT_ONLY
```

Sprint 2 adds a research-only workflow for feature computation, baseline strategies, risk-capped multi-position allocation, fixture cost/slippage, conservative T+1 settlement mechanics, and research reports.

Every Sprint 2 output remains:

```text
RESEARCH_ONLY
NOT_VALIDATED
NOT_PAPER_TRADING_ELIGIBLE
NOT_LIVE_TRADING_ELIGIBLE
```

Architecture Document 006 has been captured as the paper-trading operating constitution. Sprint 2 remains research-only; Sprint 3 adds the first paper-trading scaffold.

Sprint 3 adds a forward-only paper-trading scaffold using the same research/risk/cost/slippage/settlement primitives. It creates paper portfolios, paper strategy configurations, readiness checks, mandatory human approval, simulated paper fills, paper reconciliation, incidents, drift checks, kill switches, and evidence packages.

Every Sprint 3 record remains:

```text
PAPER_TRADING_ONLY
NO_REAL_CAPITAL_DEPLOYED
NOT_LIVE_APPROVED
NOT_BROKER_CONNECTED
PAPER_RESULTS_DO_NOT_GUARANTEE_LIVE_PERFORMANCE
```

## Data Activation Sprint

The Data Activation Sprint makes AEGIS ready for governed market-data activation:

```text
DATA-LIVE OR PROVIDER-SETUP-REQUIRED
NOT MONEY-LIVE
READ-ONLY
NO REAL CAPITAL DEPLOYED
BROKER ORDER ACCESS DISABLED
LIVE EXECUTION LOCKED
PAPER TRADING USE OF ACTUAL DATA DISABLED
```

No actual provider has been selected or configured in this repository. Without backend provider configuration and approved source rights, the API and dashboard report `Provider setup required` and keep fixtures clearly labelled as fixture data.

Required provider settings are backend-only and secrets are redacted:

```bash
DATA_SOURCE_MODE=LIVE_READONLY
MARKET_DATA_ENABLED=true
MARKET_DATA_PROVIDER_NAME=
MARKET_DATA_PROVIDER_ENVIRONMENT=
MARKET_DATA_PROVIDER_BASE_URL=
MARKET_DATA_PROVIDER_CLIENT_ID=
MARKET_DATA_PROVIDER_CLIENT_SECRET=
MARKET_DATA_PROVIDER_API_KEY=
MARKET_DATA_PROVIDER_REDIRECT_URI=
MARKET_DATA_EOD_ENABLED=true
MARKET_DATA_QUOTES_ENABLED=false
MARKET_DATA_CORPORATE_ACTIONS_ENABLED=true
MARKET_DATA_CALENDAR_ENABLED=true
MARKET_DATA_BENCHMARK_ENABLED=true
BROKER_ORDER_ACCESS=false
LIVE_BROKER_CONNECTION_ENABLED=false
LIVE_EXECUTION_ENABLED=false
PAPER_TRADING_USE_LIVE_DATA=false
```

Provider activation flow:

1. Record approved provider rights and retention policy.
2. Configure provider secrets only in backend environment variables.
3. Verify read-only connection:

```bash
curl -X POST http://localhost:8000/api/v1/providers/{provider_id}/verify-read-only-connection \
  -H 'X-AEGIS-Role: DATA_STEWARD'
```

4. Run instrument sync:

```bash
curl -X POST http://localhost:8000/api/v1/ingestions/instruments/run \
  -H 'X-AEGIS-Role: DATA_STEWARD'
```

5. Run market calendar and historical EOD ingestion:

```bash
curl -X POST http://localhost:8000/api/v1/ingestions/market-calendar/run \
  -H 'X-AEGIS-Role: DATA_STEWARD'
curl -X POST http://localhost:8000/api/v1/ingestions/eod/run \
  -H 'X-AEGIS-Role: DATA_STEWARD'
```

6. Inspect truth, lineage, validation, and blockers:

```bash
curl http://localhost:8000/api/v1/system/data-truth-summary
curl http://localhost:8000/api/v1/system/provider-readiness
curl http://localhost:8000/api/v1/system/data-blockers
curl http://localhost:8000/api/v1/dataset-versions/{dataset_version_id}/lineage
curl http://localhost:8000/api/v1/dataset-versions/{dataset_version_id}/quality
curl http://localhost:8000/api/v1/instrument-mapping-exceptions
```

To revert to fixture mode, remove provider credentials and keep `BROKER_ORDER_ACCESS=false`, `LIVE_EXECUTION_ENABLED=false`, and `PAPER_TRADING_USE_LIVE_DATA=false`.

## Real Historical Research Activation

The Real Historical Research Activation Sprint adds the governed workflow for:

```text
ACTUAL HISTORICAL DATA
→ POINT-IN-TIME FEATURES
→ FROZEN EXPERIMENT MANIFEST
→ BASELINE STRATEGY BACKTEST
→ EVIDENCE PACKAGE
```

This repository currently reports `Research blocked` because no configured, approved, healthy actual provider dataset exists. The seeded EOD dataset is explicitly `FIXTURE_DATA` and is blocked from actual-data research.

Actual-data research accepts only:

```text
ACTUAL_PROVIDER_DATA
APPROVED_FILE_IMPORT
```

All actual research output remains:

```text
ACTUAL_HISTORICAL_RESEARCH_ONLY
NOT_VALIDATED
NOT_PAPER_TRADING_ELIGIBLE
NOT_LIVE_TRADING_ELIGIBLE
NO_REAL_CAPITAL_DEPLOYED
BROKER_ORDER_ACCESS_DISABLED
LIVE_EXECUTION_LOCKED
```

Readiness and blocker checks:

```bash
curl http://localhost:8000/api/v1/research/actual-data/readiness
curl http://localhost:8000/api/v1/research/actual-data/blockers
curl http://localhost:8000/api/v1/research/actual-data/universe-readiness
curl http://localhost:8000/api/v1/research/actual-data/benchmark-readiness
curl http://localhost:8000/api/v1/research/actual-data/feature-readiness
curl http://localhost:8000/api/v1/research/actual-data/evidence-reviews/baselines
```

Actual feature computation, baseline experiment creation, manifest freezing, backtest execution, and evidence inspection:

```bash
curl -X POST http://localhost:8000/api/v1/feature-runs/actual-data \
  -H 'Content-Type: application/json' \
  -H 'X-AEGIS-Role: RESEARCHER' \
  -d '{"feature_definition_ids":["SMA_50","SMA_200","MOMENTUM_60"]}'

curl -X POST http://localhost:8000/api/v1/experiments/actual-data/baseline \
  -H 'Content-Type: application/json' \
  -H 'X-AEGIS-Role: RESEARCHER' \
  -d '{"strategy_version_id":"TrendFollowingBaselineStrategyV0"}'

curl -X POST http://localhost:8000/api/v1/experiments/{experiment_id}/freeze-manifest \
  -H 'X-AEGIS-Role: RESEARCHER'

curl -X POST http://localhost:8000/api/v1/experiments/{experiment_id}/run \
  -H 'X-AEGIS-Role: RESEARCHER'

curl http://localhost:8000/api/v1/experiments/{experiment_id}/evidence-package
```

When readiness is blocked, mutation endpoints return `409` with structured reason codes instead of creating fake feature runs or backtests.

Dashboard route: open `http://127.0.0.1:3001` and use Research Lab for the Actual Historical Research workspace. It shows actual-data blockers, eligible datasets, and fixture isolation status.

## Local Setup

```bash
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Docker Setup

```bash
docker compose up --build
```

Services:

- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Web dashboard: `http://localhost:3000`
- MinIO console: `http://localhost:9001`

## Commands

```bash
make test
make lint
make format
make typecheck
make mock-ingest
make csv-ingest
make sprint2-scenario-a
make sprint2-scenario-b
make sprint3-scenario-a
make sprint3-failure-scenarios
make sprint3-operational-hardening
```

## Sprint 1A Scenario A

1. Start the API with Docker Compose or Uvicorn.
2. Create a run:

```bash
curl -X POST http://localhost:8000/api/v1/backtest-runs \
  -H 'Content-Type: application/json' \
  -H 'X-AEGIS-Role: RESEARCHER' \
  -d '{"name":"Scenario A","starting_cash":"100000"}'
```

3. Create a buy intent using the returned `backtest_run_id`.
4. Start the run:

```bash
curl -X POST http://localhost:8000/api/v1/backtest-runs/{backtest_run_id}/start \
  -H 'X-AEGIS-Role: RESEARCHER'
```

5. Inspect `/summary`, `/cash-ledger`, `/position-ledger`, and `/nav-history`.

## Migrations

The initial schema is documented in [0001_sprint0_foundation.sql](apps/api/alembic/versions/0001_sprint0_foundation.sql). In a full Alembic environment, apply it after setting `DATABASE_URL`.

Sprint 1A schema sketch: [0002_sprint1a_backtesting.sql](apps/api/alembic/versions/0002_sprint1a_backtesting.sql).

Sprint 2 schema sketch: [0003_sprint2_research.sql](apps/api/alembic/versions/0003_sprint2_research.sql).

Sprint 3 schema sketch: [0004_sprint3_paper_trading.sql](apps/api/alembic/versions/0004_sprint3_paper_trading.sql).

## Authentication

Real auth: `POST /api/v1/auth/login` with `{"username", "password"}` returns a signed, short-lived JWT (`Authorization: Bearer <token>`); the role in the verified token -- never a client-supplied header -- determines access. Users come from `AUTH_USERS_FILE` or `AUTH_USERS_JSON` (bcrypt password hashes; generate an entry with `make hash-password`), never hardcoded.

Local development also accepts the plain `X-AEGIS-Role` header with no token, purely for dev/test convenience (`AUTH_ALLOW_INSECURE_HEADER_FALLBACK=true` in `.env.example`). `Settings.validate_startup()` refuses to let that flag be true, or `AUTH_USERS_FILE`/`AUTH_USERS_JSON` be unset, outside `development`/`test` -- so this convenience path cannot reach a real deployment. See [docs/security/authentication.md](docs/security/authentication.md).

## Safety Defaults

`LIVE_EXECUTION_ENABLED=false`, `PAPER_TRADING_ENABLED=false`, and `HUMAN_APPROVAL_REQUIRED=true`. Sprint 0 contains no order-placement modules or execution controls.

## Reset Local Environment

```bash
docker compose down -v
docker compose up --build
```
