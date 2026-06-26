# Paper Reconciliation

At valuation:

```text
NAV = Available Cash + Reserved Cash + Unsettled Receivables + Market Value - Unsettled Payables - Pending Costs
```

Any mismatch creates a `RECONCILIATION_INCIDENT`, freezes the paper portfolio, and blocks new orders.
