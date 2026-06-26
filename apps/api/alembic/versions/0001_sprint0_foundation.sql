-- Sprint 0 foundation schema sketch. Apply through Alembic in a configured environment.
CREATE TABLE data_provider (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  provider_type TEXT NOT NULL,
  status TEXT NOT NULL,
  priority INTEGER NOT NULL,
  base_url_or_reference TEXT,
  is_active BOOLEAN NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE provider_license (
  id UUID PRIMARY KEY,
  provider_id UUID NOT NULL REFERENCES data_provider(id),
  license_status TEXT NOT NULL CHECK (license_status IN ('APPROVED','CONDITIONAL','PENDING','EXPIRED','REJECTED')),
  permitted_use TEXT NOT NULL,
  automation_rights BOOLEAN NOT NULL,
  backtesting_rights BOOLEAN NOT NULL,
  model_training_rights BOOLEAN NOT NULL,
  dashboard_display_rights BOOLEAN NOT NULL,
  data_retention_period TEXT NOT NULL,
  expiry_date DATE,
  legal_review_status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE audit_event (
  id UUID PRIMARY KEY,
  event_type TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  actor_type TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  action TEXT NOT NULL,
  before_state_json JSONB,
  after_state_json JSONB,
  metadata_json JSONB NOT NULL,
  correlation_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE dataset (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  domain TEXT NOT NULL,
  description TEXT NOT NULL,
  owner TEXT NOT NULL,
  criticality TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE dataset_version (
  id UUID PRIMARY KEY,
  dataset_id UUID NOT NULL REFERENCES dataset(id),
  provider_id UUID NOT NULL REFERENCES data_provider(id),
  schema_version TEXT NOT NULL,
  raw_snapshot_hash TEXT NOT NULL,
  transformation_version TEXT NOT NULL,
  instrument_master_version TEXT NOT NULL,
  corporate_action_version TEXT NOT NULL,
  validation_status TEXT NOT NULL CHECK (validation_status IN ('GREEN','GREEN_CAUTION','AMBER','RED')),
  quality_score NUMERIC NOT NULL,
  approved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE instrument (
  id UUID PRIMARY KEY,
  aegis_instrument_id TEXT NOT NULL UNIQUE,
  isin TEXT,
  company_legal_name TEXT NOT NULL,
  security_type TEXT NOT NULL,
  current_symbol TEXT NOT NULL,
  primary_exchange TEXT NOT NULL,
  listing_date DATE NOT NULL,
  delisting_date DATE,
  trading_status TEXT NOT NULL,
  sector TEXT,
  industry TEXT,
  currency TEXT NOT NULL,
  lot_size INTEGER NOT NULL,
  tick_size NUMERIC NOT NULL,
  liquidity_classification TEXT NOT NULL,
  mapping_confidence_score NUMERIC NOT NULL,
  last_verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE instrument_alias (
  id UUID PRIMARY KEY,
  instrument_id UUID NOT NULL REFERENCES instrument(id),
  alias_type TEXT NOT NULL,
  alias_value TEXT NOT NULL,
  source_provider TEXT NOT NULL,
  valid_from DATE NOT NULL,
  valid_to DATE,
  created_at TIMESTAMPTZ NOT NULL
);
