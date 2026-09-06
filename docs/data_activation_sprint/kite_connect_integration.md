# Kite Connect Integration

AEGIS's `kite_connect` adapter (`packages/provider_adapters/aegis/provider_adapters/kite_connect_provider.py`)
implements the `MarketDataProvider` protocol against Zerodha's Kite Connect API.
It is read-only: it never calls order, holdings, margin, or position endpoints
(enforced by `__getattr__` and `validate_read_only_scope`), matching
[provider_adapter_contract.md](provider_adapter_contract.md).

## What it provides

- `fetch_instruments` / `fetch_historical_eod_bars` / `fetch_eod_prices` — real
  daily OHLCV history via Kite's `historical_data` endpoint, chunked to respect
  Kite's per-request date-range limit.
- `fetch_live_quotes` — via Kite's `quote` endpoint (only used once
  `MARKET_DATA_QUOTES_ENABLED=true`).
- `fetch_benchmark_data` — resolves and fetches NIFTY 50 index history the same
  way as an equity instrument.
- `get_health_status` — calls Kite's `profile` endpoint as a lightweight
  connectivity check.

## Known gaps (do not fabricate data for these)

- **Market calendar**: Kite Connect has no trading-holiday/session-calendar
  endpoint. `fetch_market_calendar` returns an empty payload. Keep sourcing the
  NSE calendar via the existing `csv_provider.py` / `APPROVED_FILE_IMPORT` path
  per [market_calendar_governance.md](market_calendar_governance.md).
- **Corporate actions**: same reasoning — `fetch_corporate_actions` returns
  empty. Source via CSV import per
  [corporate_actions_ingestion.md](corporate_actions_ingestion.md).
- **Instrument metadata**: Kite's instrument dump has no ISIN, listing date,
  sector, or industry. The adapter cross-references a small curated table
  (`CURATED_INSTRUMENT_METADATA`) instead of guessing; any tradingsymbol not in
  that table is skipped and reported in `metadata["unmapped_symbols"]`. Extend
  the table only with values verified against an authoritative source (e.g.
  the official NSE instrument master), matching AEGIS's
  no-fabrication/mapping-exception governance model.

## Setup steps (external, cannot be automated by AEGIS)

1. Subscribe to Kite Connect at https://kite.trade (₹2,000/month, requires an
   existing Zerodha trading/demat account).
2. Create a Connect app in the Kite developer console to get an `api_key` and
   `api_secret`.
3. Complete the daily login flow to obtain an `access_token`:
   - Redirect to `https://kite.zerodha.com/connect/login?api_key=<api_key>&v=3`,
     log in, and capture the `request_token` from the redirect.
   - Exchange it server-side: `KiteConnect(api_key).generate_session(request_token, api_secret=api_secret)`
     returns an `access_token`.
   - **This token expires daily** (Kite invalidates it every login cycle). A
     manual or scripted re-login is required each trading day before
     ingestion runs — there is no long-lived refresh token in the standard
     Kite Connect plan.
4. Set backend-only environment variables (never in frontend code):
   ```
   MARKET_DATA_PROVIDER_NAME=kite_connect
   MARKET_DATA_PROVIDER_ENVIRONMENT=production
   MARKET_DATA_PROVIDER_API_KEY=<api_key>
   MARKET_DATA_PROVIDER_CLIENT_SECRET=<api_secret>
   MARKET_DATA_PROVIDER_ACCESS_TOKEN=<access_token, refreshed daily>
   ```
5. Record the license/rights review per
   [source_rights_checklist.md](source_rights_checklist.md) — confirm Kite
   Connect's terms actually permit automation, backtesting, and dashboard
   display before flipping the provider license to `APPROVED`
   (`ProviderLicenseGuard` blocks ingestion until then, by design).
6. Run the existing activation flow from the README's provider activation
   section (`verify-read-only-connection`, instrument sync, EOD ingestion,
   `data-truth-summary`).

## Not yet done

This adapter has been implemented and unit-tested against a fake Kite client
(no network calls) — see `tests/unit/test_kite_connect_provider.py`. It has
**not** been exercised against the real Kite Connect API, since that requires
your own paid subscription and credentials. Before trusting it for real
research or eventual live trading, run it once against your real account and
sanity-check the returned bars against a known source (e.g. NSE bhavcopy) for
a few instruments and dates.
