# Data Truth Rules

- Missing provider configuration means `Provider setup required`.
- Fixtures are displayed as fixture data only.
- No provider is `Connected and healthy` until backend health verification succeeds.
- No data is `Fresh actual data` unless a real ingestion run completed and freshness is within policy.
- RED datasets are blocked.
- Actual data never enables paper trading in this sprint.
