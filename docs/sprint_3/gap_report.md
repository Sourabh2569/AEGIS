# Sprint 3 Gap Report

Preflight findings:

- No real SQLAlchemy persistence exists.
- Alembic is represented by SQL sketches only.
- Worker framework is a placeholder loop, not a durable queue.
- Local environment lacks Python 3.12, `pytest`, `fastapi`, and `npm`.
- Sprint 2 implemented research mechanics, not database-backed production workflow.
- There is no real provider-health service; fixtures provide deterministic health state.

Minimum compatible Sprint 3 remediation:

- Add in-memory paper trading repository and orchestrator.
- Add deterministic forward fixtures.
- Add scenario scripts for successful paper cycle, approval expiry, settlement restriction, data failure, reconciliation freeze, drift, kill switch, and unsupported corporate action.
- Add migration sketch and API/dashboard summary surfaces.
