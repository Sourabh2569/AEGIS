from __future__ import annotations

import time
from pathlib import Path

from aegis.audit.service import AuditLog
from aegis.paper_trading.persistence import SqlitePaperTradingRepository
from aegis.paper_trading.queue import SqlitePaperSessionQueue
from aegis.paper_trading.services import PaperTradingCalendarService, PaperTradingOrchestrator


def main() -> None:
    paper_store_path = Path("work/paper_trading.sqlite")
    paper_store_path.parent.mkdir(parents=True, exist_ok=True)
    calendar = PaperTradingCalendarService.from_csv(Path("sample_data/sprint_3/forward_market_calendar.csv"))
    repository = SqlitePaperTradingRepository(paper_store_path)
    orchestrator = PaperTradingOrchestrator(repository, AuditLog(), calendar=calendar)
    queue = SqlitePaperSessionQueue(Path("work/paper_session_queue.sqlite"))
    print("AEGIS worker started. Paper session queue is active. No broker or live execution jobs are registered.")
    while True:
        queue.run_once(orchestrator)
        time.sleep(5)


if __name__ == "__main__":
    main()
