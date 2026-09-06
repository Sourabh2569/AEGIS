# Gap Report

## Closed In This Sprint

- Provider-neutral activation state.
- Fail-closed missing-provider state.
- Secret redaction for provider settings.
- Dashboard truth APIs.
- No live quote data when provider is not configured.
- Provider capabilities and readiness APIs.
- Market-calendar validation hook for EOD data.
- Provider name selected: Zerodha Kite Connect.
- `kite_connect` adapter implemented against the documented Kite Connect API
  (instruments, historical EOD, quotes, benchmark data), satisfying the
  existing `MarketDataProvider` protocol and generic ingestion pipeline. See
  [kite_connect_integration.md](kite_connect_integration.md). Kite Connect has
  no market-calendar or corporate-actions endpoint; those remain sourced via
  CSV import, unchanged.

## Still Blocked By External Inputs

- Production credentials: a paid Kite Connect subscription, generated API
  key/secret, and a daily-refreshed access token (`MARKET_DATA_PROVIDER_ACCESS_TOKEN`).
- Legal review of automation, dashboard display, backtesting, and retention
  rights for the Kite Connect subscription terms.
- Real historical EOD payloads from Kite Connect (adapter is implemented but
  unverified against the live API without real credentials).
