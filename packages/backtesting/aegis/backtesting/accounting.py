from __future__ import annotations

from decimal import Decimal

from aegis.shared.money import money, quantity


def gross_notional(fill_quantity: Decimal, fill_price: Decimal) -> Decimal:
    return money(quantity(fill_quantity) * money(fill_price))


def weighted_average_cost_basis(
    existing_quantity: Decimal,
    existing_average_cost: Decimal,
    new_quantity: Decimal,
    new_fill_price: Decimal,
) -> Decimal:
    existing_quantity = quantity(existing_quantity)
    new_quantity = quantity(new_quantity)
    total_quantity = existing_quantity + new_quantity
    if total_quantity <= 0:
        return money(0)
    return money(
        (
            (existing_quantity * money(existing_average_cost))
            + (new_quantity * money(new_fill_price))
        )
        / total_quantity
    )


def realized_pnl(
    fill_price: Decimal, average_cost_basis: Decimal, fill_quantity: Decimal
) -> Decimal:
    return money((money(fill_price) - money(average_cost_basis)) * quantity(fill_quantity))


def nav(available_cash: Decimal, market_value: Decimal) -> Decimal:
    return money(available_cash + market_value)


def unrealized_pnl(
    mark_price: Decimal, average_cost_basis: Decimal, quantity_after: Decimal
) -> Decimal:
    return money((money(mark_price) - money(average_cost_basis)) * quantity(quantity_after))


def high_water_mark(previous: Decimal, current_nav: Decimal) -> Decimal:
    return money(max(money(previous), money(current_nav)))


def drawdown(current_nav: Decimal, hwm: Decimal) -> Decimal:
    hwm = money(hwm)
    if hwm <= 0:
        raise ValueError("High-water mark must be positive.")
    return money((money(current_nav) - hwm) / hwm)
