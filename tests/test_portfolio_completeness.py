from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from sg_investing.analysis import AnalysisDataError
from sg_investing.calculations.portfolio import analyze_portfolio
from sg_investing.models import PortfolioTransaction, TransactionType
from tests.helpers import OTHER_SECURITY_ID, fx, price, security


def tx(
    transaction_type: TransactionType,
    *,
    day: date,
    security_id=None,
    quantity: str = "0",
    cash_amount: str = "0",
    currency: str = "USD",
    fees: str = "0",
    transaction_id: str | None = None,
) -> PortfolioTransaction:
    return PortfolioTransaction(
        transaction_id=UUID(transaction_id) if transaction_id else UUID("33333333-3333-3333-3333-333333333333"),
        transaction_date=day,
        security_id=security_id,
        transaction_type=transaction_type,
        quantity=Decimal(quantity),
        cash_amount=Decimal(cash_amount),
        currency=currency,
        fees=Decimal(fees),
    )


def test_fees_reduce_cash_and_realized_profit_and_increase_buy_basis():
    sec = security()
    result = analyze_portfolio(
        transactions=[
            tx(TransactionType.CASH_DEPOSIT, day=date(2024, 1, 1), cash_amount="2000"),
            tx(TransactionType.BUY, day=date(2024, 1, 2), security_id=sec.security_id, quantity="10", cash_amount="1000", fees="10"),
            tx(TransactionType.SELL, day=date(2024, 2, 1), security_id=sec.security_id, quantity="5", cash_amount="600", fees="5"),
        ],
        securities={sec.security_id: sec},
        prices=[price(sec, date(2024, 3, 1), "120")],
        fx_rates=[fx(date(2024, 3, 1), "1")],
        as_of=date(2024, 3, 1),
    )
    holding = result.holdings[0]
    assert holding.quantity == Decimal("5")
    assert holding.weighted_average_cost == Decimal("101")
    assert holding.cost_basis_native == Decimal("505")
    assert holding.realized_pl_native == Decimal("90")
    assert result.cash_by_currency["USD"] == Decimal("1585")
    assert result.total_market_value_sgd == Decimal("2185")


def test_dividends_withdrawals_and_future_transactions_are_handled():
    sec = security()
    result = analyze_portfolio(
        transactions=[
            tx(TransactionType.CASH_DEPOSIT, day=date(2024, 1, 1), cash_amount="1000"),
            tx(TransactionType.BUY, day=date(2024, 1, 2), security_id=sec.security_id, quantity="5", cash_amount="500"),
            tx(TransactionType.DIVIDEND, day=date(2024, 2, 1), security_id=sec.security_id, cash_amount="25"),
            tx(TransactionType.CASH_WITHDRAWAL, day=date(2024, 2, 2), cash_amount="100"),
            tx(TransactionType.CASH_DEPOSIT, day=date(2024, 4, 1), cash_amount="999"),
        ],
        securities={sec.security_id: sec},
        prices=[price(sec, date(2024, 3, 1), "120")],
        fx_rates=[fx(date(2024, 3, 1), "1")],
        as_of=date(2024, 3, 1),
    )
    assert result.cash_by_currency["USD"] == Decimal("425")
    assert result.total_market_value_sgd == Decimal("1025")


def test_multiple_currencies_include_cash_and_market_value_in_sgd():
    usd = security()
    sgd = security(
        security_id=OTHER_SECURITY_ID,
        ticker="SGDTEST",
        currency="SGD",
        market="SG",
        exchange="SGX",
        income_source_country="SG",
    )
    result = analyze_portfolio(
        transactions=[
            tx(TransactionType.CASH_DEPOSIT, day=date(2024, 1, 1), cash_amount="1000", currency="USD"),
            tx(TransactionType.BUY, day=date(2024, 1, 2), security_id=usd.security_id, quantity="5", cash_amount="500", currency="USD"),
            tx(TransactionType.CASH_DEPOSIT, day=date(2024, 1, 1), cash_amount="1000", currency="SGD"),
            tx(TransactionType.BUY, day=date(2024, 1, 2), security_id=sgd.security_id, quantity="10", cash_amount="1000", currency="SGD"),
        ],
        securities={usd.security_id: usd, sgd.security_id: sgd},
        prices=[price(usd, date(2024, 3, 1), "120"), price(sgd, date(2024, 3, 1), "110")],
        fx_rates=[fx(date(2024, 3, 1), "1.4")],
        as_of=date(2024, 3, 1),
    )
    assert result.cash_by_currency == {"USD": Decimal("500"), "SGD": Decimal("0")}
    assert result.total_market_value_sgd == Decimal("700") + Decimal("840") + Decimal("1100")


def test_selling_all_shares_removes_holding_but_retains_realized_pl():
    sec = security()
    result = analyze_portfolio(
        transactions=[
            tx(TransactionType.BUY, day=date(2024, 1, 2), security_id=sec.security_id, quantity="5", cash_amount="500"),
            tx(TransactionType.SELL, day=date(2024, 2, 1), security_id=sec.security_id, quantity="5", cash_amount="600"),
        ],
        securities={sec.security_id: sec},
        prices=[],
        fx_rates=[fx(date(2024, 3, 1), "1")],
        as_of=date(2024, 3, 1),
    )
    assert result.holdings == []
    assert result.realized_pl_native == {"USD": Decimal("100")}


@pytest.mark.parametrize(
    "transactions",
    [
        [tx(TransactionType.SELL, day=date(2024, 1, 1), security_id=UUID("99999999-9999-9999-9999-999999999999"), quantity="1", cash_amount="1")],
        [tx(TransactionType.SELL, day=date(2024, 1, 1), security_id=security().security_id, quantity="1", cash_amount="1")],
    ],
)
def test_invalid_security_transactions_are_rejected(transactions):
    sec = security()
    with pytest.raises(ValueError):
        analyze_portfolio(
            transactions=transactions,
            securities={sec.security_id: sec},
            prices=[],
            fx_rates=[],
            as_of=date(2024, 3, 1),
        )


def test_currency_mismatch_and_oversell_are_rejected():
    sec = security()
    with pytest.raises(ValueError, match="currency"):
        analyze_portfolio(
            transactions=[tx(TransactionType.BUY, day=date(2024, 1, 1), security_id=sec.security_id, quantity="1", cash_amount="100", currency="SGD")],
            securities={sec.security_id: sec},
            prices=[],
            fx_rates=[],
            as_of=date(2024, 3, 1),
        )

    with pytest.raises(ValueError, match="more shares"):
        analyze_portfolio(
            transactions=[tx(TransactionType.SELL, day=date(2024, 1, 1), security_id=sec.security_id, quantity="1", cash_amount="100")],
            securities={sec.security_id: sec},
            prices=[],
            fx_rates=[],
            as_of=date(2024, 3, 1),
        )


def test_missing_price_for_nonzero_holding_is_explicit():
    sec = security()
    with pytest.raises(AnalysisDataError, match="No price"):
        analyze_portfolio(
            transactions=[tx(TransactionType.BUY, day=date(2024, 1, 1), security_id=sec.security_id, quantity="1", cash_amount="100")],
            securities={sec.security_id: sec},
            prices=[],
            fx_rates=[fx(date(2024, 3, 1), "1")],
            as_of=date(2024, 3, 1),
        )
