# Backtesting And Portfolio Attribution

Sprint 1A implements only a daily, long-only, single-instrument, event-driven simulation clock.

The execution model is `NEXT_ELIGIBLE_SESSION_OPEN_V0`: a manual order intent created after available data cutoff may execute no earlier than the next eligible session open.

Portfolio accounting uses append-only cash and position ledgers, weighted-average cost basis, daily NAV snapshots, high-water mark, drawdown, and exact reconciliation. Transaction costs, slippage, settlement delay, corporate actions, dividends, benchmark attribution, and strategy logic are out of scope.
