# Sprint 1A Backtesting Fixtures

These fixtures support deterministic foundation simulations only.

- `market_calendar.csv`: three NSE sessions.
- `valid_eod_prices.csv`: valid EOD bars for Scenario A and B.
- `missing_open_price.csv`: Scenario E failure fixture.
- `invalid_ohlc.csv`: quality-failure fixture.
- `instrument_fixture.csv`: one eligible Indian cash-equity-style instrument.

All results remain `FOUNDATION_SIMULATION_ONLY`, `NOT_VALIDATED`, `NOT_PAPER_TRADING_ELIGIBLE`, and `NOT_LIVE_TRADING_ELIGIBLE`.
