# Backtest Engine Overview

Sprint 1A implements a deterministic daily event-driven runner. A run creates one simulated portfolio, one initial cash ledger entry, append-only backtest events, optional manual order intents, simulated full fills or rejections, position ledger entries, and daily NAV snapshots.

The engine reads market data through `MarketDataReader` and sessions through `TradingCalendarReader`. It does not call provider adapters or CSV files directly.
