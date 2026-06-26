FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY apps ./apps
COPY packages ./packages
COPY infrastructure ./infrastructure
RUN pip install --no-cache-dir -e .
ENV PYTHONPATH=/app/packages/shared:/app/packages/domain:/app/packages/configuration:/app/packages/audit:/app/packages/data_quality:/app/packages/provider_adapters:/app/packages/data_ingestion:/app/packages/instrument_master:/app/packages/corporate_actions:/app/packages/research_registry:/app/packages/backtesting:/app/packages/feature_engine:/app/packages/risk:/app/packages/strategies:/app/packages/portfolio:/app/packages/paper_trading
CMD ["uvicorn", "apps.api.aegis_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
