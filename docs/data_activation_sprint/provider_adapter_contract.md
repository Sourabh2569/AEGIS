# Provider Adapter Contract

Adapters must implement:

- `fetch_instruments`
- `fetch_historical_eod_bars`
- `fetch_live_quotes`
- `fetch_market_calendar`
- `fetch_corporate_actions`
- `fetch_benchmark_data`
- `get_source_metadata`
- `get_license_status`
- `get_health_status`
- `validate_read_only_scope`

Adapters must not expose order, holdings, margin, or broker account methods. All data calls must route through governed ingestion services.
