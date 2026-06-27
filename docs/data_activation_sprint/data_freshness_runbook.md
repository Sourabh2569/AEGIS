# Data Freshness Runbook

1. Inspect `/api/v1/system/data-freshness-summary`.
2. Confirm latest available time.
3. Confirm provider health.
4. Run ingestion if provider rights and health allow it.
5. Keep stale data labelled stale until a successful fresh ingestion occurs.
