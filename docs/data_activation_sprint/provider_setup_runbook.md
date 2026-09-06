# Provider Setup Runbook

For Zerodha Kite Connect specifically, see
[kite_connect_integration.md](kite_connect_integration.md) for the concrete
subscription, key-generation, and daily-access-token steps referenced below.

1. Record provider contract and allowed usage.
2. Set backend-only provider environment variables.
3. Record approved license rights.
4. Run `POST /api/v1/providers/{provider_id}/verify-read-only-connection`.
5. Run health check.
6. Sync instruments.
7. Ingest market calendar.
8. Ingest historical EOD.
9. Review data truth summary.
