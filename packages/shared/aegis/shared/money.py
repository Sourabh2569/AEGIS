from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

INR = "INR"
MONEY_QUANT = Decimal("0.0001")
QTY_QUANT = Decimal("0.000001")


def decimal(value: str | int | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money(value: str | int | Decimal) -> Decimal:
    return decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def quantity(value: str | int | Decimal) -> Decimal:
    return decimal(value).quantize(QTY_QUANT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = INR

    @classmethod
    def of(cls, value: str | int | Decimal, currency: str = INR) -> Money:
        return cls(money(value), currency)

    def assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError("Currency mismatch.")

    def __add__(self, other: Money) -> Money:
        self.assert_same_currency(other)
        return Money(money(self.amount + other.amount), self.currency)

    def __sub__(self, other: Money) -> Money:
        self.assert_same_currency(other)
        return Money(money(self.amount - other.amount), self.currency)
