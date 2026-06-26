-- Sprint 1A backtesting and portfolio ledger schema sketch.
CREATE TABLE backtest_run (
  id UUID PRIMARY KEY,
  backtest_run_id TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL,
  simulation_classification TEXT NOT NULL CHECK (simulation_classification = 'FOUNDATION_SIMULATION_ONLY'),
  dataset_version_id UUID NOT NULL,
  instrument_master_version TEXT NOT NULL,
  portfolio_id TEXT NOT NULL,
  instrument_id TEXT NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  starting_cash NUMERIC(28, 8) NOT NULL,
  currency TEXT NOT NULL,
  execution_model_version TEXT NOT NULL,
  cost_model_version TEXT NOT NULL CHECK (cost_model_version = 'ZERO_COST_V0'),
  settlement_model_version TEXT NOT NULL CHECK (settlement_model_version = 'IMMEDIATE_SETTLEMENT_SIMULATION_V0'),
  engine_version TEXT NOT NULL,
  software_commit_hash TEXT NOT NULL,
  random_seed_nullable INTEGER,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  failure_reason_nullable TEXT,
  validation_eligibility TEXT NOT NULL CHECK (validation_eligibility = 'NOT_ELIGIBLE')
);

CREATE TABLE backtest_event (
  id UUID PRIMARY KEY,
  backtest_run_id TEXT NOT NULL REFERENCES backtest_run(backtest_run_id),
  sequence_number INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  event_time TIMESTAMPTZ NOT NULL,
  market_session_date_nullable DATE,
  entity_type_nullable TEXT,
  entity_id_nullable TEXT,
  payload_json JSONB NOT NULL,
  correlation_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  UNIQUE(backtest_run_id, sequence_number)
);

CREATE TABLE simulated_portfolio (
  id TEXT PRIMARY KEY,
  backtest_run_id TEXT NOT NULL UNIQUE REFERENCES backtest_run(backtest_run_id),
  name TEXT NOT NULL,
  currency TEXT NOT NULL,
  starting_cash NUMERIC(28, 8) NOT NULL,
  current_available_cash NUMERIC(28, 8) NOT NULL,
  current_reserved_cash NUMERIC(28, 8) NOT NULL,
  current_market_value NUMERIC(28, 8) NOT NULL,
  current_nav NUMERIC(28, 8) NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE cash_ledger_entry (
  id UUID PRIMARY KEY,
  backtest_run_id TEXT NOT NULL REFERENCES backtest_run(backtest_run_id),
  portfolio_id TEXT NOT NULL REFERENCES simulated_portfolio(id),
  entry_type TEXT NOT NULL,
  effective_time TIMESTAMPTZ NOT NULL,
  currency TEXT NOT NULL,
  amount NUMERIC(28, 8) NOT NULL,
  balance_after NUMERIC(28, 8) NOT NULL,
  reference_entity_type TEXT NOT NULL,
  reference_entity_id TEXT NOT NULL,
  description TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE position_ledger_entry (
  id UUID PRIMARY KEY,
  backtest_run_id TEXT NOT NULL REFERENCES backtest_run(backtest_run_id),
  portfolio_id TEXT NOT NULL REFERENCES simulated_portfolio(id),
  instrument_id TEXT NOT NULL,
  entry_type TEXT NOT NULL,
  effective_time TIMESTAMPTZ NOT NULL,
  quantity_delta NUMERIC(28, 8) NOT NULL,
  quantity_after NUMERIC(28, 8) NOT NULL CHECK (quantity_after >= 0),
  price_reference NUMERIC(28, 8) NOT NULL,
  gross_notional NUMERIC(28, 8) NOT NULL,
  cost_basis_after NUMERIC(28, 8) NOT NULL,
  realized_pnl_delta NUMERIC(28, 8) NOT NULL,
  reference_entity_type TEXT NOT NULL,
  reference_entity_id TEXT NOT NULL,
  description TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);
