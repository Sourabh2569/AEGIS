-- Sprint 3 paper-trading schema sketch.
CREATE TABLE paper_portfolio (
  id TEXT PRIMARY KEY,
  paper_portfolio_id TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  currency TEXT NOT NULL,
  starting_capital NUMERIC(28, 8) NOT NULL,
  status TEXT NOT NULL,
  risk_profile_version_id TEXT NOT NULL,
  portfolio_configuration_version TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  activated_at_nullable TIMESTAMPTZ,
  paused_at_nullable TIMESTAMPTZ,
  completed_at_nullable TIMESTAMPTZ,
  retired_at_nullable TIMESTAMPTZ,
  failure_reason_nullable TEXT
);

CREATE TABLE paper_strategy_configuration (
  id TEXT PRIMARY KEY,
  paper_strategy_config_id TEXT NOT NULL UNIQUE,
  paper_portfolio_id TEXT NOT NULL REFERENCES paper_portfolio(paper_portfolio_id),
  strategy_id TEXT NOT NULL,
  strategy_version_id TEXT NOT NULL,
  status TEXT NOT NULL,
  frozen_at_nullable TIMESTAMPTZ,
  approved_by_nullable TEXT,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE paper_trade_intent (
  id TEXT PRIMARY KEY,
  paper_trade_intent_id TEXT NOT NULL UNIQUE,
  paper_portfolio_id TEXT NOT NULL REFERENCES paper_portfolio(paper_portfolio_id),
  paper_strategy_config_id TEXT NOT NULL,
  instrument_id TEXT NOT NULL,
  side TEXT NOT NULL,
  proposed_quantity NUMERIC(28, 8) NOT NULL,
  approved_quantity_nullable NUMERIC(28, 8),
  decision_time TIMESTAMPTZ NOT NULL,
  available_data_cutoff TIMESTAMPTZ NOT NULL,
  eligible_execution_time TIMESTAMPTZ NOT NULL,
  approval_status TEXT NOT NULL,
  intent_status TEXT NOT NULL,
  reason_codes_json JSONB NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  correlation_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE paper_order (
  id TEXT PRIMARY KEY,
  paper_order_id TEXT NOT NULL UNIQUE,
  paper_trade_intent_id TEXT NOT NULL REFERENCES paper_trade_intent(paper_trade_intent_id),
  paper_portfolio_id TEXT NOT NULL REFERENCES paper_portfolio(paper_portfolio_id),
  instrument_id TEXT NOT NULL,
  status TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE paper_fill (
  id TEXT PRIMARY KEY,
  paper_fill_id TEXT NOT NULL UNIQUE,
  paper_order_id TEXT NOT NULL REFERENCES paper_order(paper_order_id),
  paper_portfolio_id TEXT NOT NULL REFERENCES paper_portfolio(paper_portfolio_id),
  instrument_id TEXT NOT NULL,
  fill_time TIMESTAMPTZ NOT NULL,
  fill_quantity NUMERIC(28, 8) NOT NULL,
  simulated_fill_price NUMERIC(28, 8) NOT NULL,
  cost_total NUMERIC(28, 8) NOT NULL,
  settlement_date DATE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE paper_session_job (
  id TEXT PRIMARY KEY,
  paper_portfolio_id TEXT NOT NULL REFERENCES paper_portfolio(paper_portfolio_id),
  session_date DATE NOT NULL,
  status TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  payload_json JSONB NOT NULL,
  failure_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE paper_corporate_action_review (
  id TEXT PRIMARY KEY,
  paper_portfolio_id TEXT NOT NULL REFERENCES paper_portfolio(paper_portfolio_id),
  instrument_id TEXT NOT NULL,
  action_type TEXT NOT NULL,
  effective_date DATE NOT NULL,
  verification_status TEXT NOT NULL,
  support_status TEXT NOT NULL,
  decision TEXT NOT NULL,
  reviewer_id_nullable TEXT,
  incident_id_nullable TEXT,
  reason_codes_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE paper_reconciliation_record (
  id TEXT PRIMARY KEY,
  paper_portfolio_id TEXT NOT NULL REFERENCES paper_portfolio(paper_portfolio_id),
  reconciliation_time TIMESTAMPTZ NOT NULL,
  expected_nav NUMERIC(28, 8) NOT NULL,
  observed_nav NUMERIC(28, 8) NOT NULL,
  status TEXT NOT NULL,
  reason_codes_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE paper_trading_incident (
  id TEXT PRIMARY KEY,
  paper_portfolio_id TEXT NOT NULL REFERENCES paper_portfolio(paper_portfolio_id),
  incident_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL,
  reason_codes_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  resolved_at_nullable TIMESTAMPTZ
);

CREATE TABLE paper_evidence_package (
  id TEXT PRIMARY KEY,
  paper_portfolio_id TEXT NOT NULL REFERENCES paper_portfolio(paper_portfolio_id),
  paper_strategy_config_id TEXT NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL,
  payload_json JSONB NOT NULL,
  classification_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);
