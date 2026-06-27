# Fixture Isolation Policy

Formal actual-data research accepts only:

- `ACTUAL_PROVIDER_DATA`
- `APPROVED_FILE_IMPORT`

Blocked origins:

- `FIXTURE_DATA`
- `TEST_DATA`

Mixed-origin formal experiments are blocked with `MIXED_DATA_ORIGIN_NOT_ALLOWED`.

Fixture output may be used only for unit tests, integration tests, demo mode, UI regression tests, and engine mechanics validation. It must be labelled: fixture data, not actual market research.
