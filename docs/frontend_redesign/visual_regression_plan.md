# Visual Regression Plan

## Current Manual Verification

- Run `./node_modules/.bin/next build`.
- Open the dashboard via the Next dev server.
- Verify computed styles load from Tailwind/CSS tokens.
- Inspect Command Center and Data Health.

## Future Automated Checks

- Add Playwright screenshots for desktop, laptop, tablet, and mobile.
- Capture each navigation section.
- Compare shell, status rail, page header, KPI row, primary chart area, and evidence table.
- Include empty API/fallback mode and live-readonly API mode.
