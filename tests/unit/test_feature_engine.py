from __future__ import annotations

from decimal import Decimal

from aegis.feature_engine.engine import rolling_high


def test_rolling_high_is_none_below_the_lookback() -> None:
    values = [Decimal(1), Decimal(2), Decimal(3)]
    assert rolling_high(values, 5) is None


def test_rolling_high_returns_the_real_max_over_the_trailing_window() -> None:
    values = [Decimal(10), Decimal(50), Decimal(20), Decimal(30), Decimal(15)]
    # Trailing window of 3 is [20, 30, 15] -- the real max there is 30, not
    # the all-time high of 50 sitting outside the window.
    assert rolling_high(values, 3) == Decimal(30)


def test_rolling_high_at_exactly_the_lookback_boundary() -> None:
    values = [Decimal(5), Decimal(9), Decimal(7)]
    assert rolling_high(values, 3) == Decimal(9)
