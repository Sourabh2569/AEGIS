# Operational Hardening

Sprint 3 now includes a local operational-hardening path:

- `SqlitePaperTradingRepository` persists paper records into named SQLite tables with JSON payloads.
- `SqlitePaperSessionQueue` stores queued paper session jobs and supports claim/complete/fail transitions.
- `PaperTradingCalendarService` chooses the next governed open session from `sample_data/sprint_3/forward_market_calendar.csv`.
- `PaperCorporateActionReviewService` records supported reviews and freezes the paper portfolio on unsupported or unverified actions.
- The API exposes paper session jobs and corporate-action review endpoints.
- The dashboard exposes paper jobs and corporate-action review panels.

Run:

```bash
make sprint3-operational-hardening
```

This proves persistence reload, queued session execution, governed Friday-to-Monday execution timing, and unsupported corporate-action freeze.

Remaining production hardening:

- Replace local SQLite adapters with SQLAlchemy/PostgreSQL repositories.
- Replace the local SQLite queue with Redis or another production queue.
- Add dependency-injected API repositories for isolated integration tests.
- Add browser-level dashboard checks when Node/npm and browser tooling are available.
- Expand corporate-action handling from review/freeze to full ledger adjustment for supported actions.
