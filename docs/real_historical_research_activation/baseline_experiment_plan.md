# Baseline Experiment Plan

Allowed strategies only:

- `BuyAndHoldBenchmarkStrategyV0`
- `EqualWeightUniverseBenchmarkStrategyV0`
- `TrendFollowingBaselineStrategyV0`

Rules:

- No optimization.
- No same-close execution.
- Frozen manifest required before run.
- Shared cost, slippage, settlement, ledger, risk, and backtest services must be used.
- Result classification remains `ACTUAL_HISTORICAL_RESEARCH_ONLY`.

Current local state: experiment creation is blocked until readiness passes.
