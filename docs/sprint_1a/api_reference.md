# Sprint 1A API Reference

Create a run:

```bash
curl -X POST http://localhost:8000/api/v1/backtest-runs \
  -H 'Content-Type: application/json' \
  -H 'X-AEGIS-Role: RESEARCHER' \
  -d '{"name":"Scenario A","starting_cash":"100000"}'
```

Create an order intent:

```bash
curl -X POST http://localhost:8000/api/v1/backtest-runs/{id}/order-intents \
  -H 'Content-Type: application/json' \
  -H 'X-AEGIS-Role: RESEARCHER' \
  -d '{"side":"BUY","requested_quantity":"100","decision_time":"2026-06-25T10:45:00+00:00","available_data_cutoff":"2026-06-25T10:30:00+00:00"}'
```

Start:

```bash
curl -X POST http://localhost:8000/api/v1/backtest-runs/{id}/start \
  -H 'X-AEGIS-Role: RESEARCHER'
```
