# Authentication

## What changed and why

Previously, every privileged endpoint trusted a client-supplied `X-AEGIS-Role`
header with zero verification -- any caller could set
`X-AEGIS-Role: FOUNDER` and get full access, including self-approving paper
trade intents at the `POST /api/v1/paper-trade-intents/{id}/approve` endpoint
that the entire Sprint 3 "mandatory human approval" design depends on. There
was no authentication anywhere in the codebase: `JWT_SECRET` existed in
config but nothing actually signed or verified a token with it.

This is now closed by real authentication: password-based login issuing a
signed JWT, with the token's verified role -- not a header -- deciding
access. The header still works, but only as an explicit, environment-gated
convenience for local development, never outside it.

## How it works

1. `POST /api/v1/auth/login` with `{"username": "...", "password": "..."}`.
   On success: `{"access_token": "...", "token_type": "bearer", "role": "...", "expires_in_minutes": ...}`.
2. Send `Authorization: Bearer <access_token>` on subsequent requests.
   `authenticated_role()` in `apps/api/aegis_api/main.py` verifies the
   token's signature and expiry (`packages/auth/aegis/auth/tokens.py`) and
   uses the role claim from inside it.
3. If no Bearer token is present, the request falls back to trusting the
   `X-AEGIS-Role` header **only if** `AUTH_ALLOW_INSECURE_HEADER_FALLBACK` is
   true. `Settings.validate_startup()` (`packages/configuration/aegis/configuration/settings.py`)
   raises at startup if that flag is true anywhere other than
   `ENVIRONMENT=development` or `test` -- there is no way to enable it in a
   real deployment.
4. Outside `development`/`test`, `validate_startup()` also requires
   `AUTH_USERS_FILE` or `AUTH_USERS_JSON` to be configured, and rejects the
   default placeholder `JWT_SECRET` or any secret under 32 characters.

## Provisioning real users

Never hardcode credentials. Generate a bcrypt hash interactively:

```bash
make hash-password
```

This prints a JSON object (`{"username", "password_hash", "role"}`) to paste
into a JSON array in a local, gitignored file (`auth_users*.json` is
gitignored by pattern) referenced by `AUTH_USERS_FILE`, or into a deployment
secret consumed as `AUTH_USERS_JSON`. Roles must be one of the `Role` enum
values in `packages/domain/aegis/domain/models.py` (`FOUNDER`,
`DATA_STEWARD`, `RESEARCHER`, `RISK_REVIEWER`, `PAPER_TRADING_OPERATOR`,
`ENGINEER`, `READ_ONLY`, `SYSTEM_SERVICE`).

## What this does not yet cover

- **No token revocation.** A leaked token is valid until it expires
  (`JWT_ACCESS_TOKEN_TTL_MINUTES`, default 720 = 12h). If this becomes a
  concern, add a revocation list or move to shorter-lived tokens with
  refresh tokens.
- **No rate limiting on `/api/v1/auth/login`.** Nothing currently slows down
  password-guessing attempts. Worth adding before this is internet-reachable.
- **No password complexity enforcement beyond a 12-character minimum** in
  `hash_password.py` -- it's a CLI you run yourself, not a public signup form,
  so this is a soft floor, not a security boundary.
- **Single shared secret (`JWT_SECRET`) signs all tokens.** Rotating it
  invalidates every outstanding token, which is the correct behavior for an
  internal tool at this scale, but won't scale to per-user key rotation.
