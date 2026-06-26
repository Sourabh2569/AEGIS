# Paper Trading Architecture

This file is the Sprint 3 compatibility reference for the binding architecture name expected by the build contract.

The canonical local architecture content is maintained in:

```text
docs/architecture/006_paper_trading_operational_readiness.md
```

Summary:

- Paper trading is forward-only.
- Paper trading uses no real capital, broker credentials, broker APIs, or live execution path.
- Every paper trade intent requires risk approval and human approval.
- Paper configuration is immutable after activation.
- T+1 conservative settlement is the default.
- Reconciliation failure freezes the affected paper portfolio.
- Paper performance never creates live approval.
