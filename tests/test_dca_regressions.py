from datetime import date, timedelta
from decimal import Decimal

import pytest

from sg_investing.calculations.dca import dca_analysis, xirr
from sg_investing.models import AnalysisScenario
from tests.helpers import dividend, fx, price, security


@pytest.mark.parametrize('initial', [0, 1000])
def test_same_day_dca_has_no_annualized_return(initial):
    s = security(currency='SGD')
    day = date(2024, 1, 2)
    result = dca_analysis(
        security=s, prices=[price(s, day)], fx_rates=[], start_date=day, end_date=day,
        contribution_sgd=100, initial_sgd=initial,
    )
    assert result.final_value_sgd == result.total_contributed_sgd == Decimal(100 + initial)
    assert result.xirr is None
    assert result.xirr_foreign_currency is None


def test_same_day_xirr_is_undefined_but_elapsed_flat_return_is_zero():
    day = date(2024, 1, 2)
    assert xirr([(day, Decimal(-100)), (day, Decimal(100))]) is None
    assert abs(xirr([(day, Decimal(-100)), (date(2025, 1, 2), Decimal(100))])) < Decimal('1e-9')


@pytest.mark.parametrize('lag', [7, 8, 1462])
def test_dca_warns_at_existing_fx_staleness_threshold(lag):
    s = security()
    day = date(2024, 1, 2)
    result = dca_analysis(
        security=s, prices=[price(s, day)], fx_rates=[fx(day - timedelta(days=lag))],
        start_date=day, end_date=day, contribution_sgd=100, initial_sgd=100,
    )
    expected = [f'USD/SGD FX rate for {day} is {lag} days stale.'] if lag > 7 else []
    assert result.data_quality['warnings'] == expected
    assert result.data_quality['status'] == ('WARNING' if expected else 'OK')


def test_dca_warns_for_valuation_without_a_contribution():
    s = security()
    start, end = date(2024, 1, 2), date(2024, 1, 31)
    result = dca_analysis(
        security=s, prices=[price(s, start), price(s, end)], fx_rates=[fx(start)],
        start_date=start, end_date=end, contribution_sgd=100,
    )
    assert result.data_quality['warnings'] == ['USD/SGD FX rate for 2024-01-31 is 29 days stale.']


def test_dca_warns_for_dividend_payment_currency():
    s = security(currency='SGD')
    start, ex, pay = date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 15)
    result = dca_analysis(
        security=s, prices=[price(s, start), price(s, ex), price(s, pay)],
        fx_rates=[fx(start, currency='JPY', rate='0.01')], start_date=start, end_date=pay,
        contribution_sgd=100,
        dividends=[dividend(s, ex, pay_date=pay, currency='JPY')],
        scenario=AnalysisScenario(
            withholding_tax_enabled=False,
        ),
    )
    assert result.data_quality['warnings'] == ['JPY/SGD FX rate for 2024-01-15 is 13 days stale.']
