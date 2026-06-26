# Feature Engine Contract

Features must be deterministic and point-in-time safe.

Eligibility rule:

```text
feature_available_time <= decision_time
```

Initial V0 features include daily return, rolling return, SMA, EMA, RSI, ATR, rolling volatility, rolling average daily volume, rolling average daily value traded, momentum, and price-to-moving-average distance.
