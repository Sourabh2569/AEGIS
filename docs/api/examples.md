# API Examples

Register a provider:

```bash
curl -X POST http://localhost:8000/api/v1/providers \
  -H 'Content-Type: application/json' \
  -H 'X-AEGIS-Role: DATA_STEWARD' \
  -d '{"name":"local_csv","provider_type":"CSV","base_url_or_reference":"sample_data"}'
```

Run mock ingestion:

```bash
curl -X POST http://localhost:8000/api/v1/ingestions/mock
```

Read audit events:

```bash
curl http://localhost:8000/api/v1/audit-events
```
