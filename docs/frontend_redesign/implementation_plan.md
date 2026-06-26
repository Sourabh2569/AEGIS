# AEGIS Frontend Redesign Implementation Plan

## Objective

Move AEGIS from a technical specification console to a premium analytics command center while preserving safety, audit, paper-only, live-lock, and read-only market-data constraints.

## Implementation Sequence

1. Audit existing frontend routes, API fetches, page modules, styling, and brand assets.
2. Establish fallback AEGIS design tokens because no official logo/brand asset exists in `apps/web`.
3. Add a frontend adapter layer for formatting, status-language mapping, tone mapping, and chart-ready view models.
4. Redesign the shell: grouped sidebar, page-aware top command bar, compact operating-status rail, page header, drawer.
5. Replace table-first page bodies with KPI rows, visual summaries, comparative analytics, alert panels, and secondary evidence tables.
6. Keep canonical technical values in tooltips/drawers/tables while showing readable labels in primary UI.
7. Verify build, runtime test, safety language, and responsive CSS.

## Implemented

- `apps/web/app/aegis-adapter.ts`
- `apps/web/app/aegis-dashboard.tsx`
- `apps/web/app/globals.css`

## Deferred

- A dedicated chart library such as Recharts can replace the current CSS-based chart primitives when package policy allows.
- Visual regression automation can be added with Playwright screenshots.
