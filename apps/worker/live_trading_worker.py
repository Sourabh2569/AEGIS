from __future__ import annotations

import os
import time
from pathlib import Path

from aegis.audit.service import AuditLog
from aegis.configuration.settings import Settings
from aegis.live_trading.persistence import SqliteLiveTradingRepository
from aegis.live_trading.services import LiveOrderStatusMonitor
from aegis.provider_adapters.kite_connect_order_adapter import KiteConnectOrderAdapter


def main() -> None:
    # A SEPARATE entrypoint from apps/worker/main.py -- paper trading's
    # worker keeps running independently of whether this one ever starts.
    # This process is only ever started manually by the founder; it is not
    # wired into any default process list (docker-compose, systemd, etc.).
    settings = Settings.from_env()
    # Raises ValueError only if live_execution_enabled/broker_order_access/
    # live_broker_connection_enabled were ever somehow set true -- they
    # default false, so this normally passes and the worker starts, but can
    # never place a real order regardless (see the adapter construction
    # below), since those same flags gate every real call it could make.
    settings.validate_startup()

    work_dir = Path(os.environ.get("AEGIS_WORK_DIR", "work"))
    live_store_path = work_dir / "live_trading.sqlite"
    live_store_path.parent.mkdir(parents=True, exist_ok=True)
    repository = SqliteLiveTradingRepository(live_store_path)

    # No real order-placement client is constructed here -- none exists yet
    # (the founder currently has Kite Connect data-only access, not order-
    # placement access). Constructing the adapter with client=None keeps it
    # honestly unconfigured/unhealthy; the moment real credentials exist,
    # wiring them in here is the only change this file needs. Even with a
    # real client, this adapter still cannot place a real order: it checks
    # live_execution_enabled/broker_order_access itself on every real call
    # (defense in depth), and those flags stay unconditionally false via
    # packages/configuration/aegis/configuration/settings.py's own guard
    # until the founder personally edits it, after their own Gate 6/7 work.
    order_adapter = KiteConnectOrderAdapter(
        client=None,
        live_execution_enabled=settings.live_execution_enabled,
        broker_order_access_setting=settings.broker_order_access,
        configured=False,
    )
    monitor = LiveOrderStatusMonitor(
        repository=repository, order_adapter=order_adapter, audit_log=AuditLog()
    )

    print(
        "AEGIS live-trading worker started. LIVE_EXECUTION_ENABLED and "
        "BROKER_ORDER_ACCESS remain hard-blocked at startup -- this process "
        "will poll but can place no real orders until the founder personally "
        "clears Gates 6/7 and edits Settings.validate_startup()."
    )
    while True:
        monitor.poll_open_orders()
        time.sleep(5)


if __name__ == "__main__":
    main()
