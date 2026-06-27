# Architecture Mapping

| Contract Concept | Existing / Implemented AEGIS Module |
| --- | --- |
| Provider adapters | `packages/provider_adapters` |
| Provider health | `ProviderIngestionService.check_provider_health` |
| License guard | `packages/provider_adapters/license_guard.py` |
| Raw object storage | `LocalObjectStore` under `packages/data_ingestion` |
| Dataset versions | `DatasetVersion` in `packages/domain` |
| Data quality | `packages/data_quality` |
| Instrument master | `InstrumentMasterService` |
| Audit events | `AuditLog` |
| Dashboard rendering | `apps/web/app/aegis-dashboard.tsx` |
| Truth layer | `packages/data_activation` and `/api/v1/system/*` |

The contract references `docs/architecture/007_live_execution_compliance_security.md`; this repository currently uses `docs/architecture/007_live_execution_compliance_security_incident_response.md`.
