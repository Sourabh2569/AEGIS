# 008 Live-Readonly Market Data Integration

AEGIS supports actual market-data ingestion only through `DATA_SOURCE_MODE=LIVE_READONLY`.

The live-readonly adapter is a data provider, not a broker execution adapter. It exposes instrument-master synchronization, historical EOD OHLCV ingestion, live quote ingestion, market-calendar synchronization, provider health checks, and freshness checks. It does not expose order placement, order mutation, cancellation, holdings mutation, live trading, or broker execution authority.

Required runtime flags:

```text
LIVE_EXECUTION_ENABLED=false
BROKER_ORDER_ACCESS=false
DATA_SOURCE_MODE=LIVE_READONLY
```

## Governed Data Path

1. Provider payload is fetched through `LiveReadOnlyMarketDataProvider`.
2. License guard blocks disallowed ingestion before data fetch.
3. Raw payload is written immutably under object-store `raw/`.
4. Normalized payload is written under `normalized/`.
5. Quality-passed payload is written under `curated/`.
6. Dataset versions, quality results, freshness snapshots, provider health snapshots, and audit events are recorded.
7. Dashboard APIs expose mode, provider health, freshness, quotes, and market-calendar visibility.

## API Surfaces

- `GET /api/v1/data-source/mode`
- `POST /api/v1/data-source/live-readonly/sync`
- `GET /api/v1/provider-health`
- `GET /api/v1/data-freshness`
- `GET /api/v1/live-quotes`
- `GET /api/v1/market-calendar`

## Prohibited Surfaces

- `place_order`
- `submit_order`
- `modify_order`
- `cancel_order`
- `fetch_holdings`
- `mutate_holdings`
- live trading or broker execution

If `BROKER_ORDER_ACCESS=true`, startup validation fails.
