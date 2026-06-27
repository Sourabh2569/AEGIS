# ADR 0050: Actual Data Versus Fixture Isolation

Status: accepted.

Formal actual historical research must carry explicit `data_origin`. Accepted origins are `ACTUAL_PROVIDER_DATA` and `APPROVED_FILE_IMPORT`. `FIXTURE_DATA` and `TEST_DATA` are blocked from formal research.

Reason: fixture data is useful for mechanics and UI tests, but it cannot support real historical research conclusions.
