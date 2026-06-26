# Sprint 3 Architecture Mapping

Existing names differ from the Sprint 3 contract in several places:

- `docs/architecture/006_paper_trading_operational_readiness.md` is the existing Document 006 reference. `006_paper_trading_architecture.md` was added as an alias.
- Sprint 2 risk controls live in `packages/risk/aegis/risk/engine.py`.
- Sprint 2 cost, slippage, settlement, and research portfolio mechanics live in `packages/portfolio/aegis/portfolio/sprint2.py`.
- Sprint 2 strategies live in `packages/strategies/aegis/strategies/baselines.py`.
- Sprint 2 scenario mechanics live in `packages/backtesting/aegis/backtesting/sprint2.py`.
- Sprint 3 adds orchestration in `packages/paper_trading/aegis/paper_trading/`.

Material deviation:

- The contract expects database models and queue-backed jobs. This repo currently uses in-memory repositories and SQL migration sketches. Sprint 3 follows the existing pattern and documents persistence as a gap.
