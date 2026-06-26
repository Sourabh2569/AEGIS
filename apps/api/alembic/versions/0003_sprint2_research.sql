-- Sprint 2 research, feature, risk, and report schema sketch.
CREATE TABLE research_family_sprint2 (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  economic_thesis TEXT NOT NULL,
  status TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE experiment_manifest_sprint2 (
  id TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL,
  strategy_version_id TEXT NOT NULL,
  dataset_version_id TEXT NOT NULL,
  feature_versions_json JSONB NOT NULL,
  cost_schedule_version TEXT NOT NULL,
  slippage_model_version TEXT NOT NULL,
  settlement_model_version TEXT NOT NULL,
  risk_profile_version TEXT NOT NULL,
  is_frozen BOOLEAN NOT NULL,
  frozen_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE feature_value_sprint2 (
  id TEXT PRIMARY KEY,
  instrument_id TEXT NOT NULL,
  feature_definition_id TEXT NOT NULL,
  feature_version TEXT NOT NULL,
  feature_date DATE NOT NULL,
  feature_value NUMERIC(28, 8),
  event_time TIMESTAMPTZ NOT NULL,
  available_time TIMESTAMPTZ NOT NULL,
  dataset_version_id TEXT NOT NULL,
  validation_status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE risk_assessment_sprint2 (
  risk_assessment_id TEXT PRIMARY KEY,
  portfolio_id TEXT NOT NULL,
  strategy_id TEXT NOT NULL,
  instrument_id TEXT NOT NULL,
  decision TEXT NOT NULL,
  reason_codes JSONB NOT NULL,
  risk_profile_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);
