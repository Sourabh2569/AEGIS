.PHONY: test lint format typecheck mock-ingest csv-ingest sprint3-operational-hardening

test:
	PYTHONPATH=apps/api:packages/shared:packages/domain:packages/configuration:packages/audit:packages/auth:packages/data_quality:packages/data_activation:packages/provider_adapters:packages/data_ingestion:packages/instrument_master:packages/corporate_actions:packages/research_registry:packages/research_activation:packages/backtesting:packages/feature_engine:packages/risk:packages/strategies:packages/portfolio:packages/paper_trading pytest

lint:
	ruff check apps packages tests

format:
	ruff format apps packages tests

typecheck:
	mypy packages apps/api || true

hash-password:
	PYTHONPATH=packages/auth python infrastructure/scripts/hash_password.py

kite-login:
	python infrastructure/scripts/kite_login.py

mock-ingest:
	PYTHONPATH=packages/shared:packages/domain:packages/configuration:packages/audit:packages/data_quality:packages/provider_adapters:packages/data_ingestion:packages/backtesting python infrastructure/scripts/run_mock_ingestion.py

csv-ingest:
	PYTHONPATH=packages/shared:packages/domain:packages/configuration:packages/audit:packages/data_quality:packages/provider_adapters:packages/data_ingestion:packages/backtesting python infrastructure/scripts/run_csv_ingestion.py

sprint1a-scenario-a:
	PYTHONPATH=packages/shared:packages/domain:packages/configuration:packages/audit:packages/data_quality:packages/provider_adapters:packages/data_ingestion:packages/instrument_master:packages/corporate_actions:packages/research_registry:packages/backtesting python infrastructure/scripts/run_sprint1a_scenario_a.py

sprint2-scenario-a:
	PYTHONPATH=packages/shared:packages/domain:packages/configuration:packages/audit:packages/data_quality:packages/provider_adapters:packages/data_ingestion:packages/instrument_master:packages/corporate_actions:packages/research_registry:packages/backtesting:packages/feature_engine:packages/risk:packages/strategies:packages/portfolio python infrastructure/scripts/run_sprint2_scenario_a.py

sprint2-scenario-b:
	PYTHONPATH=packages/shared:packages/domain:packages/configuration:packages/audit:packages/data_quality:packages/provider_adapters:packages/data_ingestion:packages/instrument_master:packages/corporate_actions:packages/research_registry:packages/backtesting:packages/feature_engine:packages/risk:packages/strategies:packages/portfolio python infrastructure/scripts/run_sprint2_scenario_b.py

sprint3-scenario-a:
	PYTHONPATH=packages/shared:packages/domain:packages/configuration:packages/audit:packages/data_quality:packages/provider_adapters:packages/data_ingestion:packages/instrument_master:packages/corporate_actions:packages/research_registry:packages/backtesting:packages/feature_engine:packages/risk:packages/strategies:packages/portfolio:packages/paper_trading python infrastructure/scripts/run_sprint3_scenario_a.py

sprint3-failure-scenarios:
	PYTHONPATH=packages/shared:packages/domain:packages/configuration:packages/audit:packages/data_quality:packages/provider_adapters:packages/data_ingestion:packages/instrument_master:packages/corporate_actions:packages/research_registry:packages/backtesting:packages/feature_engine:packages/risk:packages/strategies:packages/portfolio:packages/paper_trading python infrastructure/scripts/run_sprint3_failure_scenarios.py

sprint3-operational-hardening:
	PYTHONPATH=packages/shared:packages/domain:packages/configuration:packages/audit:packages/data_quality:packages/provider_adapters:packages/data_ingestion:packages/instrument_master:packages/corporate_actions:packages/research_registry:packages/backtesting:packages/feature_engine:packages/risk:packages/strategies:packages/portfolio:packages/paper_trading python infrastructure/scripts/run_sprint3_operational_hardening.py
