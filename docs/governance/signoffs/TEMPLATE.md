<!--
Governance sign-off template -- see docs/architecture/011_governance_signoff_protocol.md
for the process this belongs to.

To use: copy this file to docs/governance/signoffs/YYYY-MM-DD.md, fill it out
honestly, and commit it. Never edit a past sign-off after the fact -- a new
dated copy supersedes an old one. A blank or template-boilerplate answer in
any section is not a real sign-off.
-->

# Live Trading Governance Sign-Off -- [DATE]

## Scope of what's being approved

- Real capital ceiling for this pilot: [amount -- be specific, not "some"]
- Real instrument/strategy scope: [e.g. "TrendFollowingBaselineStrategyV0 only, Nifty 50 universe"]
- Real duration before mandatory re-review: [e.g. "30 real trading days, then a new sign-off is required regardless of outcome"]
- Real stop conditions (what automatically or manually ends this pilot): [reference real kill-switch scopes/thresholds, not vague language]

## Founder review

- What in `009_live_readiness_dossier.md` gives real confidence this is worth the capital and risk at stake, right now?
- What's the single weakest gate, honestly, and why is it acceptable to proceed anyway (or is it not)?
- Decision: [ ] APPROVE [ ] DO NOT APPROVE
- Reasoning:

## Risk review

- Real numbers pulled from `GET /api/v1/live-readiness/evidence` as of this sign-off: [paste the real Gate 2 numbers -- portfolio count, longest track record, worst drawdown, reconciliation mismatches]
- Does the real risk-state ladder (Gate 3) and kill-switch coverage (Gate 5) actually cover the worst case seen in that real track record?
- Decision: [ ] APPROVE [ ] DO NOT APPROVE
- Reasoning:

## Security review

- Real state of Gate 4 as of this sign-off (CI `pip-audit`/`check_no_secrets.py` status, any open findings):
- Anything about credential handling for a *real* broker connection (not just read-only market data) that changes the security posture?
- Decision: [ ] APPROVE [ ] DO NOT APPROVE
- Reasoning:

## Compliance review

- Real confirmation obtained from Zerodha (not just the research in Gate 6) -- what exactly did they say, and when?
- Is order tagging and the static IP actually configured and verified working, not just planned?
- Decision: [ ] APPROVE [ ] DO NOT APPROVE
- Reasoning:

## Legal review

- Anything beyond SEBI's retail algo framework worth a second look (broker T&Cs, tax treatment, personal liability)?
- Decision: [ ] APPROVE [ ] DO NOT APPROVE
- Reasoning:

## Overall

All five above must be APPROVE for this sign-off to authorize anything. A single DO NOT APPROVE blocks the whole thing.

Overall decision: [ ] AUTHORIZED TO PROCEED TO PHASE 5 [ ] NOT AUTHORIZED

Signed: [name] -- [date]
