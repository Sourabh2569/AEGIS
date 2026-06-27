# Architecture Mapping

Binding document mapping:

- `001_system_architecture.md`: modular monolith, fail-closed service boundaries.
- `002_data_governance.md`: provider, dataset version, lineage, license, calendar gates.
- `003_research_validation.md`: results are not validation or promotion evidence.
- `004_backtesting_portfolio_attribution.md`: event clock and next-session execution.
- `005_portfolio_risk_position_sizing.md`: risk engine owns final sizing.
- `006_paper_trading_architecture.md`: compatibility shim for paper operational readiness.
- `007_live_execution_compliance_security.md`: mapped to `007_live_execution_compliance_security_incident_response.md`.
- `008_live_readonly_market_data_integration.md`: read-only actual provider activation.

Implementation mapping:

- Actual eligibility: `packages/research_activation/aegis/research_activation/service.py`.
- Provider/data truth: `packages/data_activation/aegis/data_activation/service.py`.
- Raw object storage: `packages/data_ingestion/aegis/data_ingestion/service.py`.
- Research API orchestration: `apps/api/aegis_api/main.py`.
- Actual research jobs: `packages/research_activation/aegis/research_activation/jobs.py`.
- Dashboard truth layer: `apps/web/app/aegis-dashboard.tsx`, `apps/web/app/aegis-adapter.ts`, `apps/web/app/page.tsx`.
