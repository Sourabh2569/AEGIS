# Real Historical Research Activation Implementation Plan

Status: implemented as a blocked-but-ready activation surface until governed actual data exists.

Sequence:

1. Preflight and isolation: verify provider, license, dataset origin, raw objects, validation, lineage, health, and safety flags.
2. Actual feature activation: expose blocked feature-run orchestration until actual research readiness passes.
3. Experiment governance: allow only approved baseline strategies and require frozen manifests.
4. Backtest execution: block formal actual-data runs until readiness is not blocked.
5. Evidence and dashboard: expose exact blockers, labels, and empty states.
6. Hardening: unit, integration, lint, type, build, and secret scans.

Current local readiness: `BLOCKED`.

Primary blocker: no configured, approved, healthy actual provider dataset; the seeded dataset is `FIXTURE_DATA`.
