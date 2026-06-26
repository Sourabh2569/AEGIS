# Sprint 2 Gap Report

Preflight findings:

- `docs/architecture/005_portfolio_risk_position_sizing.md` was missing and has been added.
- PostgreSQL persistence is not implemented in code.
- Alembic is represented by SQL sketches, not a runnable migration environment.
- The worker framework is still a placeholder.
- Local machine has Python 3.9.6, no `python3.12`, no `pytest`, no `npm`, and no installed FastAPI.
- Sprint 1A is a deterministic in-memory foundation, not a production-complete backtesting engine.

Minimum Sprint 2 remediation:

- Add deterministic in-memory research, feature, risk, strategy, and scenario services.
- Add migration sketches for future persistence.
- Add direct scenario scripts so mechanics can be verified without API runtime dependencies.
- Preserve all research-only labels and fail-closed behavior.
