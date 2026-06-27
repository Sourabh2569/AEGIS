# Data Activation Sprint Implementation Plan

AEGIS moves to `DATA-LIVE / NOT MONEY-LIVE` by adding a governed read-only market-data activation layer. The implementation is provider-neutral until an approved provider, credentials, and license terms are supplied.

## Sequence

1. Preserve Sprint 0-3 modules and extend them through provider activation, not trading.
2. Make missing provider configuration visible as `Provider setup required`.
3. Enforce `BROKER_ORDER_ACCESS=false`, `LIVE_EXECUTION_ENABLED=false`, and `PAPER_TRADING_USE_LIVE_DATA=false`.
4. Route all provider calls through backend ingestion services.
5. Capture immutable raw objects before normalization and dataset versioning.
6. Surface dashboard truth through `/api/v1/system/data-truth-summary`.
7. Keep paper workflows fixture-labelled until an explicit future activation.

## Current Provider State

No actual provider credentials or provider SDK are present. AEGIS therefore starts in `NOT_CONFIGURED` and must not display healthy/live data.
