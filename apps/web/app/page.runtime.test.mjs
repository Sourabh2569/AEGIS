import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const pageSource = readFileSync(new URL("./page.tsx", import.meta.url), "utf8");
const dashboardSource = readFileSync(new URL("./aegis-dashboard.tsx", import.meta.url), "utf8");

test("aegis dashboard exposes full-spec product modules", () => {
  assert.match(pageSource, /AegisDashboard/);
  assert.match(pageSource, /\/api\/v1\/paper-session-jobs/);
  assert.match(pageSource, /\/api\/v1\/paper-corporate-action-reviews/);
  assert.match(dashboardSource, /Dataset Lineage/);
  assert.match(dashboardSource, /Provider Licensing/);
  assert.match(dashboardSource, /Feature Versioning/);
  assert.match(dashboardSource, /Risk Attribution/);
  assert.match(dashboardSource, /Drift Statistics/);
  assert.match(dashboardSource, /Corporate Actions/);
  assert.match(dashboardSource, /Paper Operations/);
  assert.match(dashboardSource, /Live Readiness/);
  assert.match(dashboardSource, /Compliance & Security/);
  assert.match(dashboardSource, /Live Ops & Incidents/);
  assert.match(dashboardSource, /LIVE_EXECUTION_ENABLED=false/);
  assert.match(dashboardSource, /NOT_BROKER_CONNECTED/);
});
