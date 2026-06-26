# Sprint 2 API Reference

Run Scenario A:

```bash
curl -X POST http://localhost:8000/api/v1/sprint-2/scenario-a \
  -H 'X-AEGIS-Role: RESEARCHER'
```

Read reports:

```bash
curl http://localhost:8000/api/v1/sprint-2/reports
```

Read feature definitions:

```bash
curl http://localhost:8000/api/v1/feature-definitions
```
