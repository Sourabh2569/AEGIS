# 009 Live Readiness Dossier

Living evidence tracker for Document 007's 8 Live Readiness Gates. Not itself an authorization to go live -- Document 007 remains the constitution; this is the checkable record of where each gate actually stands, updated as real evidence accumulates.

`GET /api/v1/live-readiness/evidence` and the Cockpit's Live Readiness view (`/live-readiness`) report the real, current numbers for Gates 1 and 2 automatically. The rest of this document is updated by hand as work on the other gates progresses.

## Gate 1 -- Research integrity

**Status: substantially in place.** Real backtests run against `ACTUAL_PROVIDER_DATA` (real Kite Connect EOD history), a real 50-instrument Nifty universe, real dataset snapshot hashes, and a documented, testable strategy rule set (see `TrendFollowingBaselineStrategyV0` and its benchmarks). Live count via the evidence endpoint.

Remaining: no independent second-reviewer sign-off process yet for a strategy's research methodology before it's considered "approved" for live candidacy.

## Gate 2 -- Paper-trading evidence

**Status: evidence clock restarted at zero (2026-09-10).** The paper-trading database was intentionally wiped this session to remove test scaffolding. There is currently no accumulated real paper-trading track record. Live count via the evidence endpoint (portfolio count, real session count, days active, drawdown, reconciliation mismatches).

Remaining: accumulate a real, sustained track record (real duration, real rebalance cycles, real reconciliation cleanliness) before this gate can be considered passed. No fixed threshold is set here deliberately -- "how long is enough" is a judgment call for whoever signs off on Gate 7, not something to fabricate a number for.

## Gate 3 -- Portfolio and risk readiness

**Status: substantially in place.** `PortfolioRiskState` (`packages/risk/aegis/risk/engine.py`) implements a 6-state drawdown ladder: `NORMAL`/`CAUTION`/`DEFENSIVE`/`CAPITAL_PRESERVATION`/`FROZEN` (automatic, drawdown-derived) plus `EMERGENCY_EXIT` (a true hard stop, reserved for an explicit external trigger, escalated for human review rather than auto-clearing). This is a real implementation of what Document 007 calls the `EMERGENCY_REVIEW` state -- same semantics (explicit trigger, human escalation, no auto-clear), different name. `PAUSED` exists today at the portfolio-lifecycle level (`PaperPortfolioStatus.PAUSED`), not as a risk-assessment state; whether that's sufficient or whether `PositionSizingEngine.assess()` should also take portfolio-pause as an explicit input is an open design question, not yet resolved.

Remaining: decide and (if needed) implement whether lifecycle-level `PAUSED` needs to flow into risk assessments directly; consider renaming `EMERGENCY_EXIT` to `EMERGENCY_REVIEW` for terminology consistency with this document (a cosmetic rename touching tested code -- low priority, not blocking).

## Gate 4 -- Security readiness

**Status: strong foundation, one closed gap this pass.** Real JWT auth, bcrypt password hashing, per-username login rate limiting, no plaintext credentials in the auth path, a secrets-pattern CI check (`check_no_secrets.py`), and CVE remediation history (postcss, vitest/esbuild/vite dependency chain). This pass added `pip-audit` to CI for Python dependency vulnerability scanning -- one real finding surfaced immediately (`PYSEC-2020-25` in `autobahn`, pinned by `kiteconnect` for its unused WebSocket ticker component) and is tracked as an accepted, documented risk in `.github/workflows/ci.yml` pending revisit before any phase that would use real-time order-status streaming.

Remaining: `check_no_secrets.py` is a narrow regex (GitHub/AWS tokens, PEM keys) -- consider a more general secret-scanning tool before real broker credentials are ever involved (today only read-only market-data credentials exist in `.env`). No formal secrets-manager (Vault, cloud KMS, etc.) yet -- `.env` on disk is the only mechanism today.

## Gate 5 -- Operational readiness

**Status: scaffolding only.** `KillSwitch`/`KillSwitchType` dataclasses exist and are wired into `PositionSizingEngine.assess()`, but per ADR 0026 they currently only ever gate simulated/paper order creation -- there is no live execution for them to actually kill yet. No incident-response runbook exists beyond Document 007's high-level principles (capital protection, containment, evidence preservation, facts, reconciliation, controlled recovery).

Remaining: a real incident-response runbook; monitoring/alerting design (currently none -- issues are found by manually watching the Cockpit).

## Gate 6 -- Legal and compliance readiness

**Status: not started, and not something engineering can complete.** Confirmed scope: this is for the founder's own personal trading account and capital, not a multi-user product -- a materially smaller regulatory question (a broker's retail algo-trading framework, not SEBI investment-adviser/portfolio-manager registration). Still requires: confirming directly with Zerodha whether a personal Kite Connect app used for automated order placement needs algo-ID tagging or other disclosure under SEBI's current algo-trading framework for retail investors, and reading that framework directly.

Remaining: everything. This is a real action item for the founder, not a code change.

## Gate 7 -- Governance readiness

**Status: not started.** Document 007 asks for "explicit founder, risk, security, compliance, and legal approval" before Phase 5. For a solo operator this means personally, explicitly signing off on each of those concerns -- this dossier is intended as the checklist that sign-off would be made against, once Gates 1-6 have real evidence behind them.

## Gate 8 -- Controlled live pilot readiness

Out of scope until Gates 1-7 are passed. Not evaluated here.

## Roadmap position

Per Document 007's 5-phase roadmap, this dossier and the evidence endpoint are Phase 1 work (compliance/security/governance foundation). Phase 2 (broker adapter sandbox), Phase 3 (reconciliation/operational controls), and Phases 4-5 (pilot readiness/pilot) have not been started and should not be, until Phase 1's gates show real, sustained evidence -- not because the roadmap is bureaucratic, but because Document 007's own closing line is the actual engineering discipline here: *when uncertainty exists, do not submit the order.*
