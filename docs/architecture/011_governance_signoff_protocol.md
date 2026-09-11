# 011 Governance Sign-Off Protocol (Gate 7)

Document 007 requires "explicit founder, risk, security, compliance, and legal approval" before Phase 5 (a limited live pilot). AEGIS has one operator, not five people -- this document defines what that requirement means for a solo operator, so "governance" doesn't collapse into a single vague "yeah, I approve."

## The core discipline

Wearing five hats does not mean making one decision. It means the same person must **separately, explicitly** reason through five different failure modes before a real order can ever be submitted:

- **Founder**: is this worth the real capital and real risk, given everything else in the Dossier?
- **Risk**: does the real risk-state ladder, position sizing, and kill-switch coverage (Gate 3, Gate 5) actually hold up under the worst real drawdown seen in paper trading, not just the average case?
- **Security**: could a credential leak, a bug, or an outside actor cause real harm before a human notices (Gate 4, Gate 5)?
- **Compliance**: is Gate 6 (SEBI's retail algo framework, static IP, order tagging) actually done, not just researched?
- **Legal**: beyond SEBI, is there anything else (broker T&Cs, tax treatment, personal liability) worth a second look?

A solo operator can satisfy this honestly by reviewing the *real evidence* for each concern separately and recording a separate, dated, real decision for each -- not by writing "approved" once. That's what the template below is for.

## What counts as real evidence, per concern

| Concern | Where the real evidence lives |
|---|---|
| Founder | `009_live_readiness_dossier.md` in full -- the honest, current state of every gate |
| Risk | `GET /api/v1/live-readiness/evidence` (Gate 2's real track record), Gate 3's risk-state ladder, Gate 5's kill-switch/incident mechanisms (`/operations`) |
| Security | Gate 4's section of the Dossier, CI's `pip-audit`/`check_no_secrets.py` results, the auth/rate-limiting code itself |
| Compliance | Gate 6's section of the Dossier -- and specifically, real confirmation from Zerodha, not just the research recorded there |
| Legal | Whatever the founder's own reading/consultation turns up beyond Gate 6 -- not pre-filled here, since it's genuinely open |

A sign-off that doesn't reference specific, real, current evidence (a real number from the evidence endpoint, a real commit, a real conversation with the broker) isn't a real sign-off -- it's the exact "present simulated performance as live" failure mode Document 007 opens by prohibiting, just applied to governance instead of performance.

## Process

1. Before ever setting `LIVE_EXECUTION_ENABLED=true` in real code, fill out a **new, dated copy** of `docs/governance/signoffs/TEMPLATE.md` -- e.g. `docs/governance/signoffs/2026-MM-DD.md`. Never edit a past sign-off after the fact; if circumstances change, a *new* dated sign-off supersedes it. This mirrors Document 007's "append-only tamper-evident audit records" principle, applied to governance decisions via git history itself (each sign-off is a real, timestamped commit).
2. Any single concern marked "DO NOT APPROVE" blocks the whole sign-off, full stop -- there is no majority vote with one person.
3. A completed, all-five-approved sign-off is necessary but not sufficient for Phase 5 -- it still requires Gates 1-6 to show real, sustained evidence (not just "the process was followed").
4. This protocol document itself is not a sign-off. No sign-off exists yet. Gate 7 remains **not started** until a real, dated file exists under `docs/governance/signoffs/`.
