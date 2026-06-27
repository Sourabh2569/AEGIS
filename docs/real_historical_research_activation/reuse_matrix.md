# Reuse Matrix

| Capability | Existing module reused |
| --- | --- |
| Provider licensing | `ProviderLicense`, `ProviderLicenseGuard`, `DataActivationService` |
| Dataset lineage | `DatasetVersion`, `RawDataObject`, object store layers |
| Dataset eligibility | `ActualHistoricalResearchEligibilityService` extending data activation truth |
| Instrument mapping | `InstrumentMasterService` and internal AEGIS instrument IDs |
| Universe membership | `AEGIS_LIQUID_EQUITY_RESEARCH_UNIVERSE_V0` readiness surface |
| Market calendar | Backtesting and paper calendar services |
| Corporate actions | `CorporateAction` models and paper review workflows |
| Feature computation | Existing `feature_engine` definitions and feature-run API surface |
| Feature storage | Actual feature-run registry in API pending durable persistence |
| Strategy execution | Existing backtesting strategy/run interfaces |
| Experiment manifest creation | Existing research registry concepts plus actual-data baseline API |
| Risk sizing | `risk` package and AEGIS conservative risk profile |
| Cost calculations | ADR-backed versioned cost schedules |
| Slippage calculations | ADR-backed fixed bps slippage model |
| Settlement | T+1 conservative settlement ADR and paper/backtest settlement services |
| Backtesting | Existing event-driven backtesting service |
| Benchmark comparison | Existing Sprint 2 report/backtest surfaces |
| Attribution | Existing report surfaces, blocked until actual run exists |
| Evidence packaging | Existing paper/research evidence concepts, actual package endpoint |
| Audit logging | `AuditLog` |
| Background jobs | `ActualResearchJobRunner` local idempotent job runner |
| Dashboard rendering | Next.js dashboard adapter and Research Lab |
