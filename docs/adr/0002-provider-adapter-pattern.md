# ADR 0002: Provider Adapter Pattern

External market-data access must flow through `MarketDataProvider` implementations. Business logic, API routes, dashboard code, and future strategy modules must not call providers directly.
