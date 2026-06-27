# Provider Activation Strategy

AEGIS does not invent a provider. Until provider settings are present, the system reports `Provider setup required`.

Required backend-only configuration:

- `MARKET_DATA_PROVIDER_NAME`
- `MARKET_DATA_PROVIDER_ENVIRONMENT`
- one of `MARKET_DATA_PROVIDER_API_KEY` or `MARKET_DATA_PROVIDER_CLIENT_ID` plus `MARKET_DATA_PROVIDER_CLIENT_SECRET`
- license rights recorded as approved

Provider verification must run through backend APIs only. Frontend components never receive secrets.
