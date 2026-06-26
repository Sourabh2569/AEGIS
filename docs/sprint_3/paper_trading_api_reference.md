# Paper Trading API Reference

Create portfolio:

```bash
curl -X POST http://localhost:8000/api/v1/paper-portfolios \
  -H 'Content-Type: application/json' \
  -H 'X-AEGIS-Role: FOUNDER' \
  -d '{"name":"Paper Test","starting_capital":"100000"}'
```

Activate:

```bash
curl -X POST http://localhost:8000/api/v1/paper-portfolios/{paper_portfolio_id}/activate \
  -H 'X-AEGIS-Role: FOUNDER'
```

Run decision cycle:

```bash
curl -X POST http://localhost:8000/api/v1/paper-trading-sessions/run \
  -H 'Content-Type: application/json' \
  -d '{"paper_portfolio_id":"...","session_date":"2026-06-26"}'
```

Enqueue a decision cycle job:

```bash
curl -X POST http://localhost:8000/api/v1/paper-session-jobs \
  -H 'Content-Type: application/json' \
  -d '{"paper_portfolio_id":"...","session_date":"2026-06-26","reference_prices":{"AEGIS-IN-000001":"112"}}'
```

Run the next queued paper job:

```bash
curl -X POST http://localhost:8000/api/v1/paper-session-jobs/run-next
```

Approve intent:

```bash
curl -X POST http://localhost:8000/api/v1/paper-trade-intents/{paper_trade_intent_id}/approve \
  -H 'X-AEGIS-Role: RISK_REVIEWER'
```

Review a paper corporate action:

```bash
curl -X POST http://localhost:8000/api/v1/paper-corporate-action-reviews \
  -H 'Content-Type: application/json' \
  -H 'X-AEGIS-Role: DATA_STEWARD' \
  -d '{"paper_portfolio_id":"...","instrument_id":"AEGIS-IN-000001","action_type":"DEMERGER","effective_date":"2026-06-30","verification_status":"PENDING","supported":false}'
```
