# Architecture Overview

AEGIS starts as a modular monolith with a Python API, Python worker, TypeScript dashboard, PostgreSQL metadata store, Redis coordination layer, and MinIO-compatible object storage.

Data access flows through provider adapters. Raw data is captured immutably before validation. Dataset versions carry lineage to raw objects. Critical validation failures set the dataset version to `RED`. No module contains live execution credentials or order-placement behavior.

Architecture references `001` through `006` now cover system architecture, data governance, research validation, backtesting and attribution, portfolio risk and position sizing, and future paper-trading operational readiness.
