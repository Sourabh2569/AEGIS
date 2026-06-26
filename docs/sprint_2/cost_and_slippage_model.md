# Cost And Slippage Model

Sprint 2 includes fixture-labelled cost schedules and `FixedBpsSlippageModelV0`.

Formula:

```text
buy_fill_price = reference_price * (1 + buy_bps / 10000)
sell_fill_price = reference_price * (1 - sell_bps / 10000)
```

Fixture costs are not current Indian statutory rates.
