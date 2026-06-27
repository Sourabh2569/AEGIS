# Ingestion Failure Runbook

1. Inspect `/api/v1/ingestions/{id}`.
2. Inspect `/api/v1/ingestions/{id}/errors`.
3. Check provider readiness.
4. Check license status.
5. Check raw-object capture.
6. Re-run only after correcting source, license, mapping, or calendar issues.
