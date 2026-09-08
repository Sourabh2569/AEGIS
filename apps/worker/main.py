from __future__ import annotations

import time
from pathlib import Path

from aegis.audit.service import AuditLog
from aegis.backtesting.momentum_research import build_paper_strategy_resolver
from aegis.paper_trading.persistence import SqlitePaperTradingRepository
from aegis.paper_trading.queue import SqlitePaperSessionQueue
from aegis.paper_trading.services import PaperTradingCalendarService, PaperTradingOrchestrator
from aegis.provider_adapters.kite_connect_provider import CURATED_INSTRUMENT_METADATA


def main() -> None:
    paper_store_path = Path("work/paper_trading.sqlite")
    paper_store_path.parent.mkdir(parents=True, exist_ok=True)
    calendar = PaperTradingCalendarService.from_csv(
        Path("sample_data/market_calendar/market_calendar.csv")
    )
    repository = SqlitePaperTradingRepository(paper_store_path)
    object_store_root = Path("work/object_store")
    sector_by_instrument_id = {
        metadata.aegis_instrument_id: metadata.sector
        for metadata in CURATED_INSTRUMENT_METADATA.values()
    }
    orchestrator = PaperTradingOrchestrator(
        repository,
        AuditLog(),
        calendar=calendar,
        sector_by_instrument=sector_by_instrument_id,
        strategy_target_resolver=build_paper_strategy_resolver(
            object_store_root, sector_by_instrument_id
        ),
    )
    queue = SqlitePaperSessionQueue(Path("work/paper_session_queue.sqlite"))
    print(
        "AEGIS worker started. Paper session queue is active. No broker or live execution jobs are registered."
    )
    while True:
        queue.run_once(orchestrator)
        time.sleep(5)


if __name__ == "__main__":
    main()
