# Sprint 2 Architecture Mapping

Sprint 2 maps to the existing scaffold as follows:

- Sprint 0 `AuditLog` remains the global audit-event integration point.
- Sprint 0 `Role` remains the role model.
- Sprint 0 `DatasetVersion`, `ProviderLicense`, and `Instrument` remain eligibility inputs.
- Sprint 1A Decimal primitives and next-session-open causality rules are reused.
- Sprint 1A in-memory repository style is preserved.
- Sprint 2 adds `feature_engine`, `risk`, `strategies`, and `portfolio` packages instead of replacing Sprint 1A.

Material deviations:

- The contract expects database-backed entities and background jobs. The repository currently has SQL sketches and in-memory services only.
- Dashboard data remains API-backed when the API is running, but not database-backed.
- Worker jobs are represented by idempotent script/service entrypoints, not queue-backed jobs.
- Corporate action support is mechanics-level for fixtures, not a full governed production processor.
