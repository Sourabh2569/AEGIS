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

**Status: real progress this pass, real gaps remain.** Full detail in `docs/architecture/010_incident_response_runbook.md`. Summary:

- Kill switches now have real teeth: activate/deactivate both work for real (deactivate used to be a complete no-op -- a kill switch could never be turned back off), both are role-gated and require a documented reason, and an active switch now also blocks order execution (`execute_approved_orders`), not just new intent generation -- closing a real gap where a re-approved, previously-blocked intent could slip through. All 9 of Document 007's kill-switch types now exist in the vocabulary (were 5 of 9).
- Incidents are real: `PaperReconciliationService` genuinely creates an incident and freezes the affected portfolio on a RED reconciliation. First-ever Cockpit UI for both kill switches and incidents (`/operations`).
- **The one thing that isn't fixed and can't be yet**: reconciliation itself is never triggered in production, and even if it were, it's self-referential (no independent broker-reported data source to compare against) -- blocked on Phase 2's broker adapter. Building a "Reconcile Now" button today would be decorative, not real safety, so it wasn't built.

Remaining: a real reconciliation trigger + independent data source (Phase 2); monitoring/alerting (currently none -- issues are found by manually opening the Cockpit); role/reason gating on incident resolution (noted as an adjacent gap in the runbook, not yet fixed); wiring the 4 newly-cataloged kill-switch types into real scope-matching once their corresponding systems exist.

## Gate 6 -- Legal and compliance readiness

**Status: real regulatory framework identified; founder action still required, not something engineering can complete.** Confirmed scope: this is for the founder's own personal trading account and capital, not a multi-user product -- a materially smaller regulatory question (a broker's retail algo-trading framework, not SEBI investment-adviser/portfolio-manager registration).

**Research findings (public sources, 2026-09-11 -- verify currency before relying on this; not legal advice):**

- SEBI issued a real, binding circular on 4 Feb 2025 ("Safer participation of retail investors in Algorithmic trading," `SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013`) covering exactly AEGIS's situation: strategy-driven orders placed via a broker API (Kite Connect), not manual clicks. Implementation was phased through late 2025, with brokers required to be fully compliant by 5 January 2026 -- i.e. this framework is **already in force today**, not a future concern.
- **Kite Connect is explicitly in scope.** Zerodha's own Kite Connect FAQ states that *"Kite Publisher"* (a manual-click order widget) falls outside SEBI's algo framework because a human places each order -- by clear implication, Kite Connect (what AEGIS's adapter uses, and what would place any future live order) does not get that exemption.
- **The real, concrete requirements found:**
  - A retail individual automating their own strategy at **≤10 orders/second (per segment per exchange)** does not need formal exchange algo-ID registration -- AEGIS's real trading pattern (monthly rebalances, single-digit order counts) is nowhere near this threshold.
  - **Even so, orders must still be tagged** -- unregistered/personal algos get a generic identifying tag rather than a unique registered algo ID, but tagging itself is not optional.
  - **A static IP dedicated to the API key is required** for API-based order placement under this framework.
  - Anything **above** 10 orders/second requires formal exchange registration with a unique algo ID, approved through the broker -- not relevant to AEGIS's actual trading pattern, but worth knowing as the line not to cross.
- **What's not publicly documented**: Zerodha's own general Kite Connect FAQ does not lay out a clear self-service page for how a personal API user actually gets tagged/registered under this framework -- the practical mechanism has to come directly from Zerodha, not from public docs.

**Remaining -- real action items for the founder, not code:**
1. Contact Zerodha's Kite Connect / API support team directly and ask, specifically: "I use the Kite Connect API to place my own trades on my own account, well under 10 orders/second -- what do I need to do under SEBI's Feb 2025 retail algo trading circular (tagging, static IP, anything else)?"
2. Read the actual SEBI circular text directly (not secondhand summaries, including this one) before relying on any of the above.
3. Set up the static IP for the API key regardless of what else is required -- it's a concrete, unambiguous requirement already identified.
4. Given this framework only fully came into force in the last few months, confirm nothing has changed since this research was done before treating this gate as evidenced.

This research is a starting point for the founder's own verification, not a substitute for it -- consistent with Document 007's stance that Gate 6 cannot be satisfied by engineering work alone.

## Gate 7 -- Governance readiness

**Status: not started.** Document 007 asks for "explicit founder, risk, security, compliance, and legal approval" before Phase 5. For a solo operator this means personally, explicitly signing off on each of those concerns -- this dossier is intended as the checklist that sign-off would be made against, once Gates 1-6 have real evidence behind them.

## Gate 8 -- Controlled live pilot readiness

Out of scope until Gates 1-7 are passed. Not evaluated here.

## Roadmap position

Per Document 007's 5-phase roadmap, this dossier and the evidence endpoint are Phase 1 work (compliance/security/governance foundation). Phase 2 (broker adapter sandbox), Phase 3 (reconciliation/operational controls), and Phases 4-5 (pilot readiness/pilot) have not been started and should not be, until Phase 1's gates show real, sustained evidence -- not because the roadmap is bureaucratic, but because Document 007's own closing line is the actual engineering discipline here: *when uncertainty exists, do not submit the order.*
