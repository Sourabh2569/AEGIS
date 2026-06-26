# Sprint 0 Implementation Plan

1. Establish the modular monolith repository shape.
2. Add typed configuration with fail-closed execution defaults.
3. Implement core domain models, audit events, provider contracts, and ingestion guardrails.
4. Add mock and CSV providers only.
5. Preserve raw payloads immutably and derive deterministic content hashes.
6. Validate EOD OHLCV records, instrument mapping, duplicate bars, and point-in-time timestamps.
7. Expose versioned API endpoints for system, providers, datasets, ingestions, instruments, corporate actions, research registry, and audit.
8. Build an internal dashboard with operational tables only.
9. Add unit tests for mandatory safety failures.
10. Document ADRs, runbooks, setup, and known limits.
