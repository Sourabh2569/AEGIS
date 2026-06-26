# Backtest Failure

1. Read `/api/v1/backtest-runs/{id}/summary`.
2. Inspect `/events` for `BACKTEST_FAILED`.
3. Inspect rejected orders and reason codes.
4. Confirm dataset eligibility, license status, instrument mapping, market calendar, and open/close prices.
5. Do not modify the completed or failed run in place. Clone inputs into a new run after correction.
