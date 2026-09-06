FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY apps ./apps
COPY packages ./packages
COPY infrastructure ./infrastructure
COPY sample_data ./sample_data
RUN pip install --no-cache-dir -e .
ENV PYTHONPATH=/app/packages/shared:/app/packages/domain:/app/packages/configuration:/app/packages/audit:/app/packages/auth:/app/packages/data_quality:/app/packages/data_activation:/app/packages/provider_adapters:/app/packages/data_ingestion:/app/packages/instrument_master:/app/packages/corporate_actions:/app/packages/research_registry:/app/packages/research_activation:/app/packages/backtesting:/app/packages/feature_engine:/app/packages/risk:/app/packages/strategies:/app/packages/portfolio:/app/packages/paper_trading
# Run as a non-root user. main.py and worker/main.py create ./work/ (sqlite
# db, local object store) at runtime, so it needs to own /app, not just read it.
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin aegis \
    && chown -R aegis:aegis /app
USER aegis
CMD ["uvicorn", "apps.api.aegis_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
