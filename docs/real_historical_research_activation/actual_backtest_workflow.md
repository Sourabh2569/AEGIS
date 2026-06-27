# Actual Backtest Workflow

Workflow:

1. Validate market-calendar session.
2. Apply due settlements.
3. Apply supported corporate actions.
4. Process next-session fills.
5. Apply cost, slippage, settlement, and ledger entries.
6. Validate EOD data.
7. Compute point-in-time features.
8. Generate signals on permitted dates.
9. Apply portfolio construction and risk sizing.
10. Create next-session intents.
11. Mark NAV, exposure, drawdown, and snapshots.
12. Emit audit and backtest events.

No same-close execution is permitted.
