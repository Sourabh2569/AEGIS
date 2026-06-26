# Paper Order Lifecycle

Paper order flow:

```text
Trade Intent -> Risk Assessment -> Human Approval -> Scheduled Order -> Eligible Session -> Simulated Fill or Block
```

Orders are full-fill-or-reject in this scaffold. Duplicate execution is blocked through idempotency and completed intent state.
