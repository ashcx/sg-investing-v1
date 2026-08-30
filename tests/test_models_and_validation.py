from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from sg_investing.data.validation import (
    validate_corporate_actions,
    validate_dividends,
    validate_fx,
    validate_prices,
)
from sg_investing.models import (
    CorporateAction,
    CorporateActionType,
    DividendEvent,
    FxRate,
    PortfolioTransaction,
    PriceBar,
    TransactionType,
)
from tests.helpers import security, price


def test_model_identifiers_are_normalized():
    row = security(ticker=" test ", currency="usd", market="us", exchange="nyse")
    assert row.ticker == "TEST"
    assert row.currency == "USD"
    assert row.market == "US"
    assert row.exchange == "NYSE"


@pytest.mark.parametrize(
    ("field", "value"),
    [("ticker", ""), ("exchange", ""), ("market", ""), ("name", "")],
)
def test_security_requires_non_empty_identifiers(field, value):
    with pytest.raises(ValidationError):
        security(**{field: value})


def test_money_and_positive_ratio_constraints_are_enforced():
    with pytest.raises(ValidationError):
        price(security(), date(2024, 1, 2), close="-1")
    with pytest.raises(ValidationError):
        FxRate(rate_date=date(2024, 1, 2), base_currency="USD", rate_to_sgd=Decimal("0"), source="test")
    with pytest.raises(ValidationError):
        CorporateAction(
            security_id=security().security_id,
            effective_date=date(2024, 1, 2),
            action_type=CorporateActionType.SPLIT,
            ratio=Decimal("0"),
            source="test",
        )


def test_portfolio_transaction_normalizes_currency_and_rejects_negative_fees():
    transaction = PortfolioTransaction(
        transaction_date=date(2024, 1, 2),
        transaction_type=TransactionType.CASH_DEPOSIT,
        cash_amount=Decimal("100"),
        currency="usd",
    )
    assert transaction.currency == "USD"
    with pytest.raises(ValidationError):
        PortfolioTransaction(
            transaction_date=date(2024, 1, 2),
            transaction_type=TransactionType.CASH_DEPOSIT,
            cash_amount=Decimal("100"),
            currency="USD",
            fees=Decimal("-0.01"),
        )


def test_tax_rule_date_boundaries_are_inclusive():
    from tests.helpers import tax_rule

    rule = tax_rule("0.30", effective_from=date(2024, 1, 1), effective_to=date(2024, 12, 31))
    assert rule.applies_on(date(2024, 1, 1))
    assert rule.applies_on(date(2024, 12, 31))
    assert not rule.applies_on(date(2023, 12, 31))
    assert not rule.applies_on(date(2025, 1, 1))


def test_validate_prices_detects_duplicates_and_ohlc_errors():
    row = price(security(), date(2024, 1, 2), close="100", high="90", low="80")
    report = validate_prices([row, row])
    assert report.status.value == "FAILED"
    assert any("Duplicate price" in error for error in report.errors)
    assert any("Invalid OHLC" in error for error in report.errors)


def test_validate_prices_rejects_zero_close():
    row = price(security(), date(2024, 1, 2), close="0", open_price="0", high="0", low="0")
    report = validate_prices([row])
    assert report.status.value == "FAILED"
    assert any("zero close" in error for error in report.errors)


def test_validate_dividends_rejects_pay_date_before_ex_date():
    row = DividendEvent(
        security_id=security().security_id,
        ex_date=date(2024, 2, 1),
        pay_date=date(2024, 1, 1),
        amount=Decimal("1"),
        currency="USD",
        source="test",
    )
    report = validate_dividends([row])
    assert report.status.value == "FAILED"
    assert report.errors


def test_validate_dividends_and_fx_detect_canonical_duplicates():
    sec = security()
    dividend_row = DividendEvent(
        security_id=sec.security_id,
        ex_date=date(2024, 2, 1),
        amount=Decimal("1"),
        currency="USD",
        source="test",
    )
    dividend_report = validate_dividends([dividend_row, dividend_row])
    assert dividend_report.status.value == "FAILED"

    rate = FxRate(rate_date=date(2024, 2, 1), base_currency="USD", rate_to_sgd=Decimal("1.3"), source="test")
    fx_report = validate_fx([rate, rate])
    assert fx_report.status.value == "FAILED"


def test_validate_fx_requires_sgd_to_sgd_rate_of_one():
    rate = FxRate(rate_date=date(2024, 2, 1), base_currency="SGD", rate_to_sgd=Decimal("1.3"), source="test")
    report = validate_fx([rate])
    assert report.status.value == "FAILED"
    assert any("SGD/SGD" in error for error in report.errors)


def test_validate_corporate_actions_accepts_positive_ratios():
    row = CorporateAction(
        security_id=security().security_id,
        effective_date=date(2024, 2, 1),
        action_type=CorporateActionType.REVERSE_SPLIT,
        ratio=Decimal("0.5"),
        source="test",
    )
    report = validate_corporate_actions([row])
    assert report.status.value == "OK"
