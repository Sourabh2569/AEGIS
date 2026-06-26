# Current UI Audit

## Routes

The frontend currently exposes one Next.js route:

- `/` via `apps/web/app/page.tsx`

The page fetches API data from:

- `/api/v1/system/overview`
- `/api/v1/providers`
- `/api/v1/datasets`
- `/api/v1/ingestions`
- `/api/v1/instruments`
- `/api/v1/audit-events`
- `/api/v1/backtest-runs`
- `/api/v1/sprint-2/reports`
- `/api/v1/paper-*`
- `/api/v1/data-source/mode`
- `/api/v1/provider-health`
- `/api/v1/data-freshness`
- `/api/v1/live-quotes`
- `/api/v1/market-calendar`

## Findings

- The old UI used repeated equal-weight cards and tables.
- Safety states were visible but too technical for primary surfaces.
- The repeated banner consumed vertical space.
- Navigation was ungrouped and long.
- No official logo or brand-token asset was found in frontend paths during the initial redesign.
- The user later supplied the AEGIS logo board and palette, now reflected in the app token system.
- Styling is correctly served only through the Next app server.

## Preserve

- Paper-only messaging.
- Live execution lock.
- Broker disconnected state.
- Read-only data mode.
- Audit evidence access.
- Data lineage and quality records.
