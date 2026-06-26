# Paper Execution And Settlement

Default execution model:

```text
NEXT_ELIGIBLE_SESSION_OPEN_WITH_CONFIGURED_FRICTION_V0
```

Default settlement:

```text
T_PLUS_1_CONSERVATIVE_V0
```

No broker API is called. Fills are simulated with fixture reference prices, fixed-BPS slippage, fixture cost schedule, and append-only ledger records.
