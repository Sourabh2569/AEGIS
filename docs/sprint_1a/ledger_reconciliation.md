# Ledger Reconciliation

At each NAV snapshot:

```text
Portfolio NAV = Available Cash + Market Value
```

At completion:

```text
Starting Cash + Realized P&L + Unrealized P&L = Closing NAV
```

Sprint 1A uses exact Decimal arithmetic. A mismatch fails the run, emits `BACKTEST_FAILED`, and records a global audit event.
