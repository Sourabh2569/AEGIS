"""Generate an approximate NSE trading-session calendar CSV.

IMPORTANT, READ BEFORE TRUSTING THIS FOR REAL PAPER TRADING DECISIONS:

This marks every weekday (Mon-Fri) as open, then excludes only a handful of
FIXED-DATE national holidays (Republic Day, Ambedkar Jayanti, Independence
Day, Gandhi Jayanti, Christmas) that fall on the same calendar date every
year. It deliberately does NOT include lunar/festival holidays that shift
every year -- Holi, Good Friday, Ram Navami, Eid, Ganesh Chaturthi, Dussehra,
Diwali (Laxmi Puja + Muhurat trading), Guru Nanak Jayanti, and any
NSE-declared special trading/non-trading sessions. Those dates cannot be
guessed reliably; using a wrong one would create a session that looks
"open" in AEGIS while the real exchange is actually closed, or vice versa.

Before relying on this near any Indian festival period, cross-check and
patch the output against NSE's official published holiday circular
(nseindia.com -> Markets -> Trading Holidays) for the relevant year, then
regenerate or hand-edit the CSV. This script is a starting point, not a
source of truth.

Usage:
    python infrastructure/scripts/generate_nse_calendar.py \
        --start 2026-09-01 --end 2026-12-31 \
        --out sample_data/market_calendar/market_calendar.csv
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

# (month, day) -- fixed every year, high confidence these are NSE holidays.
FIXED_DATE_HOLIDAYS = {
    (1, 26): "Republic Day",
    (4, 14): "Ambedkar Jayanti",
    (8, 15): "Independence Day",
    (10, 2): "Gandhi Jayanti",
    (12, 25): "Christmas",
}


def generate_sessions(start: date, end: date) -> list[date]:
    sessions = []
    current = start
    while current <= end:
        if current.weekday() < 5 and (current.month, current.day) not in FIXED_DATE_HOLIDAYS:
            sessions.append(current)
        current += timedelta(days=1)
    return sessions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--exchange", default="NSE")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    sessions = generate_sessions(args.start, args.end)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["exchange", "session_date", "is_open"])
        for session in sessions:
            writer.writerow([args.exchange, session.isoformat(), "true"])

    print(f"Wrote {len(sessions)} approximate trading sessions to {args.out}")
    print(
        "This excludes only fixed-date national holidays -- lunar/festival "
        "holidays are NOT included. Verify against NSE's official holiday "
        "circular before relying on this near a festival period."
    )


if __name__ == "__main__":
    main()
