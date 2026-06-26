# Sprint 2 Scope Guard

Sprint 2 outputs are research mechanics only.

Forbidden:

- Live trading.
- Broker credentials or broker API calls.
- Paper-trading lifecycle.
- Paper-trading admission, approval, order queue, simulated paper portfolio operation, or future live-candidate review.
- ML or AI-generated strategies.
- Derivatives, leverage, short selling, intraday trading.
- Public investment advice.
- Automatic promotion to validation, paper trading, or live status.

Mandatory classification:

```text
RESEARCH_ONLY
NOT_VALIDATED
NOT_PAPER_TRADING_ELIGIBLE
NOT_LIVE_TRADING_ELIGIBLE
```

Any API, report, dashboard, or script output must preserve this classification.
