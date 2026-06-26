# Data Governance

Market data must enter AEGIS through governed providers and dataset versions. Simulation modules do not call providers directly and do not read ad hoc CSV files at runtime.

Required eligibility for Sprint 1A:

- Dataset version is `GREEN` or `GREEN_CAUTION`.
- Lineage exists.
- Provider license is `APPROVED`.
- Instrument identity is resolved and eligible.
- Market calendar exists for the requested range.
- EOD bars include required open and close references.
