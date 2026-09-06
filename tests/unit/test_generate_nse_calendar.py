from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "infrastructure" / "scripts" / "generate_nse_calendar.py"
)
spec = importlib.util.spec_from_file_location("generate_nse_calendar", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
generate_nse_calendar = importlib.util.module_from_spec(spec)
sys.modules["generate_nse_calendar"] = generate_nse_calendar
spec.loader.exec_module(generate_nse_calendar)


def test_weekends_are_excluded() -> None:
    # 2026-09-05 is a Saturday, 2026-09-06 a Sunday.
    sessions = generate_nse_calendar.generate_sessions(date(2026, 9, 4), date(2026, 9, 7))
    assert sessions == [date(2026, 9, 4), date(2026, 9, 7)]


def test_fixed_date_national_holidays_are_excluded() -> None:
    sessions = generate_nse_calendar.generate_sessions(date(2026, 10, 1), date(2026, 10, 3))
    assert date(2026, 10, 2) not in sessions  # Gandhi Jayanti
    assert date(2026, 10, 1) in sessions
    assert date(2026, 10, 3) not in sessions  # Saturday


def test_does_not_claim_lunar_holidays_are_handled() -> None:
    """Documentation check, not a data check: this generator has no concept
    of festival/lunar holidays at all -- a session on e.g. a real Diwali date
    would incorrectly come back as "open" here. Callers must not treat this
    output as authoritative without manual verification against NSE's
    published calendar."""
    assert "lunar" in generate_nse_calendar.__doc__.lower()
    assert "official" in generate_nse_calendar.__doc__.lower()
