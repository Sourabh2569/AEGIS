from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from aegis.backtesting.repositories import MarketDataReader, TradingCalendarReader


def load_calendar(path: Path) -> TradingCalendarReader:
    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    sessions = [
        date.fromisoformat(row["session_date"]) for row in rows if row["is_open"].lower() == "true"
    ]
    exchange = rows[0]["exchange"] if rows else "NSE"
    return TradingCalendarReader(sessions=sessions, exchange=exchange)


def load_market_data(path: Path, dataset_version_id: str) -> MarketDataReader:
    bars = {}
    with path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            session = date.fromisoformat(row["trade_date"])
            bars[(row["aegis_instrument_id"], session)] = {
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "available_time": datetime.fromisoformat(row["available_time"]),
            }
    return MarketDataReader(bars=bars, dataset_version_id=dataset_version_id)
