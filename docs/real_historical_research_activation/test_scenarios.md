# Test Scenarios

Covered locally:

- Fixture dataset is blocked from actual research.
- Actual-looking dataset requires explicit origin.
- Raw object linkage is required.
- Provider health is required.
- RED validation and missing lineage block activation.
- Actual research mutation endpoints fail closed when readiness is blocked.
- Actual research background jobs are idempotent and fail closed when readiness is blocked.
- Evidence review gate returns `RESEARCH_ONLY_NEEDS_FIXES` for all three baseline strategies when no actual evidence package exists.

Deferred until provider data exists:

- Full actual provider ingestion to feature run to frozen manifest to backtest to evidence package.
