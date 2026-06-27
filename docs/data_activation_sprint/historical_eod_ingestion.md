# Historical EOD Ingestion

Historical EOD ingestion captures provider payloads as immutable raw objects, normalizes OHLCV bars, validates OHLC structure, checks instrument mapping, preserves event/available/ingested timestamps, creates dataset versions, and exposes lineage.

Raw, tradable, adjusted, and total-return prices must remain separate.
