# Data Eligibility Rules

A run starts only when:

- Dataset version is `GREEN` or `GREEN_CAUTION`.
- Dataset lineage exists.
- Provider license is `APPROVED`.
- Instrument mapping confidence is at least `0.90`.
- Instrument trading status is `ACTIVE` or `ELIGIBLE`.
- Market calendar sessions exist for the run period.
- EOD bars exist for the run instrument and period.
- Execution model is `NEXT_ELIGIBLE_SESSION_OPEN_V0`.
