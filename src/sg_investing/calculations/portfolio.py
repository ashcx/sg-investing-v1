"""Transaction-ledger portfolio reconstruction using weighted-average cost."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from sg_investing.analysis import AnalysisDataError, _rate_for_date
from sg_investing.models import FxRate, PortfolioTransaction, PriceBar, Security, TransactionType

_ZERO = Decimal("0")


class HoldingSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    security_id: str
    ticker: str
    quantity: Decimal
    weighted_average_cost: Decimal
    cost_basis_native: Decimal
    market_value_native: Decimal
    market_value_sgd: Decimal
    unrealized_pl_native: Decimal
    realized_pl_native: Decimal


class PortfolioResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: date
    holdings: list[HoldingSnapshot]
    cash_by_currency: dict[str, Decimal]
    realized_pl_native: dict[str, Decimal]
    total_market_value_sgd: Decimal
    methodology: dict[str, str]


def _last_close_on_or_before(rows: Iterable[PriceBar], *, security_id: object, as_of: date) -> PriceBar:
    eligible = sorted(
        (row for row in rows if row.security_id == security_id and row.trading_date <= as_of),
        key=lambda row: row.trading_date,
    )
    if not eligible:
        raise AnalysisDataError(f"No price on or before {as_of} for security {security_id}.")
    return eligible[-1]


def analyze_portfolio(
    *,
    transactions: Iterable[PortfolioTransaction],
    securities: Mapping[object, Security],
    prices: Iterable[PriceBar],
    fx_rates: Iterable[FxRate],
    as_of: date,
) -> PortfolioResult:
    """Reconstruct holdings and P/L using weighted-average cost basis.

    The basis is an explicit reporting convention. It does not attempt to model
    Singapore capital-gains tax or tax lots.
    """

    quantity: dict[object, Decimal] = defaultdict(lambda: _ZERO)
    cost_basis: dict[object, Decimal] = defaultdict(lambda: _ZERO)
    realized: dict[object, Decimal] = defaultdict(lambda: _ZERO)
    cash: dict[str, Decimal] = defaultdict(lambda: _ZERO)

    for transaction in sorted(
        (item for item in transactions if item.transaction_date <= as_of),
        key=lambda item: (item.transaction_date, str(item.transaction_id)),
    ):
        security_id = transaction.security_id
        if transaction.transaction_type in {TransactionType.BUY, TransactionType.SELL, TransactionType.DIVIDEND}:
            if security_id is None or security_id not in securities:
                raise ValueError("Security transaction refers to an unknown security.")
            if securities[security_id].currency != transaction.currency:
                raise ValueError("Security transaction currency does not match security currency.")

        if transaction.transaction_type == TransactionType.BUY:
            quantity[security_id] += transaction.quantity
            cost_basis[security_id] += transaction.cash_amount + transaction.fees
            cash[transaction.currency] -= transaction.cash_amount + transaction.fees
        elif transaction.transaction_type == TransactionType.SELL:
            if transaction.quantity > quantity[security_id]:
                raise ValueError("Cannot sell more shares than the weighted-average ledger holds.")
            average_cost = cost_basis[security_id] / quantity[security_id] if quantity[security_id] else _ZERO
            disposed_cost = average_cost * transaction.quantity
            proceeds = transaction.cash_amount - transaction.fees
            realized[security_id] += proceeds - disposed_cost
            quantity[security_id] -= transaction.quantity
            cost_basis[security_id] -= disposed_cost
            cash[transaction.currency] += proceeds
        elif transaction.transaction_type == TransactionType.DIVIDEND:
            cash[transaction.currency] += transaction.cash_amount - transaction.fees
        elif transaction.transaction_type == TransactionType.CASH_DEPOSIT:
            cash[transaction.currency] += transaction.cash_amount
        elif transaction.transaction_type == TransactionType.CASH_WITHDRAWAL:
            cash[transaction.currency] -= transaction.cash_amount

    snapshots: list[HoldingSnapshot] = []
    total_sgd = _ZERO
    realized_by_currency: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    for security_id, shares in quantity.items():
        if shares == _ZERO:
            continue
        security = securities[security_id]
        close = _last_close_on_or_before(prices, security_id=security_id, as_of=as_of)
        market_value = shares * close.close
        rate = _rate_for_date(security.currency, as_of, fx_rates)
        market_sgd = market_value * rate
        total_sgd += market_sgd
        average_cost = cost_basis[security_id] / shares
        snapshots.append(
            HoldingSnapshot(
                security_id=str(security_id),
                ticker=security.ticker,
                quantity=shares,
                weighted_average_cost=average_cost,
                cost_basis_native=cost_basis[security_id],
                market_value_native=market_value,
                market_value_sgd=market_sgd,
                unrealized_pl_native=market_value - cost_basis[security_id],
                realized_pl_native=realized[security_id],
            )
        )
    for security_id, amount in realized.items():
        if security_id in securities:
            realized_by_currency[securities[security_id].currency] += amount
    for currency, amount in cash.items():
        total_sgd += amount * _rate_for_date(currency, as_of, fx_rates)
    return PortfolioResult(
        as_of=as_of,
        holdings=sorted(snapshots, key=lambda holding: holding.ticker),
        cash_by_currency=dict(cash),
        realized_pl_native=dict(realized_by_currency),
        total_market_value_sgd=total_sgd,
        methodology={"cost_basis": "weighted_average", "end_value": "mark_to_market"},
    )
