# Portfolio Risk, Position Sizing And Capital Preservation

This reference is derived from AEGIS Document 005. Its governing principle is that capital preservation comes before return generation. A missed opportunity is recoverable; a large avoidable loss can permanently damage compounding.

Risk is hierarchical:

```text
System Risk
↓
Portfolio Risk
↓
Strategy Risk
↓
Market-Regime Risk
↓
Sector / Theme Risk
↓
Position Risk
↓
Order Risk
↓
Data and Operational Risk
```

A lower-level approval never overrides a higher-level breach. A valid signal cannot override a portfolio freeze, a high-confidence strategy cannot override a sector cap, and a manual decision cannot override critical data-quality or operational failure.

Required portfolio risk states:

- `NORMAL`
- `CAUTION`
- `DEFENSIVE`
- `CAPITAL_PRESERVATION`
- `FROZEN`
- `EMERGENCY_EXIT`

`EMERGENCY_EXIT` remains a future controlled state. No automatic live liquidation may exist in V1.

Position sizing is determined by risk capacity, not conviction. Final quantity is the minimum of allocation cap, risk-per-position cap, liquidity cap, portfolio exposure cap, sector/cluster cap, strategy allocation cap, drawdown-state multiplier, cash-reserve cap, and instrument eligibility cap.

Every proposed position must define:

- Entry assumption.
- Invalidation condition.
- Expected downside boundary.
- Gap-risk adjustment.
- Liquidity assessment.
- Portfolio-risk assessment.
- Risk-budget impact.
- Exit or pause plan.

Cash is a deliberate risk-control position when opportunity quality, data quality, regime suitability, liquidity, or operational health is uncertain. A zero allocation is valid.

Sprint 2 starts with `AEGIS_CONSERVATIVE_V0`, a research-only engineering profile. It is not a return promise, personal recommendation, or permanent policy.
