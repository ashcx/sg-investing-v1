from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from sg_investing.analysis import AnalysisDataError
from sg_investing.calculations.dca import DcaFrequency, dca_analysis, xirr
from sg_investing.models import AnalysisScenario, DistributionPolicy
from tests.helpers import action, dividend, fx, price, security, tax_rule


def run_dca(*, security_row, prices, fx_rates=(), start_date=date(2024, 1, 1), end_date=date(2024, 4, 1), **kwargs):
    return dca_analysis(
        security=security_row,
        prices=prices,
        fx_rates=fx_rates,
        start_date=start_date,
        end_date=end_date,
        contribution_sgd=kwargs.pop("contribution_sgd", "100"),
        **kwargs,
    )


def test_quarterly_and_yearly_contributions_choose_one_date_per_period():
    sec = security()
    prices = [
        price(sec, date(2024, 1, 2)),
        price(sec, date(2024, 2, 1)),
        price(sec, date(2024, 4, 1)),
        price(sec, date(2024, 5, 1)),
        price(sec, date(2025, 1, 2)),
    ]
    rates = [fx(row.trading_date, "1") for row in prices]

    quarterly = run_dca(
        security_row=sec,
        prices=prices,
        fx_rates=rates,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 5, 1),
        frequency=DcaFrequency.QUARTERLY,
    )
    yearly = run_dca(
        security_row=sec,
        prices=prices,
        fx_rates=rates,
        start_date=date(2024, 1, 1),
        end_date=date(2025, 1, 2),
        frequency=DcaFrequency.YEARLY,
    )
    assert quarterly.contribution_dates == [date(2024, 1, 2), date(2024, 4, 1)]
    assert yearly.contribution_dates == [date(2024, 1, 2), date(2025, 1, 2)]


def test_cash_dividend_mode_keeps_net_dividend_as_cash():
    sec = security()
    prices = [price(sec, day) for day in (date(2024, 1, 2), date(2024, 2, 1), date(2024, 3, 1), date(2024, 4, 1))]
    result = run_dca(
        security_row=sec,
        prices=prices,
        fx_rates=[fx(row.trading_date, "1") for row in prices],
        scenario=AnalysisScenario(reinvest_dividends=False),
        dividends=[dividend(sec, date(2024, 1, 15), "10", pay_date=date(2024, 2, 1))],
        tax_rules=[tax_rule("0.30")],
    )
    assert result.shares == Decimal("4")
    assert result.final_value_foreign_currency == Decimal("407")
    assert result.gain_loss_foreign_currency == Decimal("7")


def test_dca_reinvestment_uses_net_dividend_after_withholding():
    sec = security()
    prices = [
        price(sec, date(2024, 1, 2), "100"),
        price(sec, date(2024, 2, 1), "100"),
        price(sec, date(2024, 3, 1), "50"),
    ]
    result = run_dca(
        security_row=sec,
        prices=prices,
        fx_rates=[fx(row.trading_date, "1") for row in prices],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 1),
        dividends=[dividend(sec, date(2024, 2, 15), "10", pay_date=date(2024, 3, 1))],
        tax_rules=[tax_rule("0.30")],
    )
    # Three S$100 contributions buy 1 + 1 + 2 shares. The first two shares
    # receive a US$10 dividend; US$14 is reinvested at US$50.
    assert result.shares == Decimal("4") + Decimal("14") / Decimal("50")


def test_dca_dividends_disabled_do_not_create_reinvestment_or_warnings():
    sec = security()
    prices = [price(sec, day) for day in (date(2024, 1, 2), date(2024, 2, 1), date(2024, 3, 1))]
    result = run_dca(
        security_row=sec,
        prices=prices,
        fx_rates=[fx(row.trading_date, "1") for row in prices],
        end_date=date(2024, 3, 1),
        scenario=AnalysisScenario(dividends_enabled=False),
        dividends=[dividend(sec, date(2024, 1, 15), "10", pay_date=date(2024, 2, 1))],
    )
    assert result.shares == Decimal("3")
    assert result.data_quality["warnings"] == []


def test_dca_missing_pay_date_is_fallback_and_after_valuation_is_reported():
    sec = security()
    prices = [price(sec, day) for day in (date(2024, 1, 2), date(2024, 2, 1), date(2024, 3, 4))]
    result = run_dca(
        security_row=sec,
        prices=prices,
        fx_rates=[fx(row.trading_date, "1") for row in prices],
        end_date=date(2024, 3, 4),
        dividends=[dividend(sec, date(2024, 2, 1), "1")],
    )
    assert any("Approximated dividend pay date" in warning for warning in result.data_quality["warnings"])

    after = run_dca(
        security_row=sec,
        prices=prices,
        fx_rates=[fx(row.trading_date, "1") for row in prices],
        end_date=date(2024, 2, 1),
        dividends=[dividend(sec, date(2024, 1, 15), "1", pay_date=date(2024, 3, 1))],
    )
    assert any("after valuation" in warning for warning in after.data_quality["warnings"])


def test_dca_rejects_a_pay_date_before_the_ex_date():
    sec = security()
    prices = [price(sec, day) for day in (date(2024, 1, 2), date(2024, 2, 1), date(2024, 3, 1))]

    with pytest.raises(AnalysisDataError, match="pay date precedes ex-date"):
        run_dca(
            security_row=sec,
            prices=prices,
            fx_rates=[fx(row.trading_date, "1") for row in prices],
            end_date=date(2024, 3, 1),
            dividends=[dividend(sec, date(2024, 2, 1), "1", pay_date=date(2024, 1, 15))],
        )


def test_dca_split_is_applied_before_later_valuation():
    sec = security()
    prices = [
        price(sec, date(2024, 1, 2), "100"),
        price(sec, date(2024, 2, 1), "50"),
        price(sec, date(2024, 3, 1), "50"),
    ]
    result = run_dca(
        security_row=sec,
        prices=prices,
        fx_rates=[fx(row.trading_date, "1") for row in prices],
        end_date=date(2024, 3, 1),
        corporate_actions=[action(sec, date(2024, 2, 1), "2")],
    )
    assert result.shares == Decimal("2") + Decimal("2") + Decimal("2")
    assert result.final_value_foreign_currency == Decimal("300")


def test_accumulating_dca_security_surfaces_ignored_dividends():
    sec = security(distribution_policy=DistributionPolicy.ACCUMULATING)
    prices = [price(sec, day) for day in (date(2024, 1, 2), date(2024, 2, 1), date(2024, 3, 1))]
    result = run_dca(
        security_row=sec,
        prices=prices,
        fx_rates=[fx(row.trading_date, "1") for row in prices],
        end_date=date(2024, 3, 1),
        dividends=[dividend(sec, date(2024, 1, 15), "1", pay_date=date(2024, 2, 1))],
    )
    assert result.shares == Decimal("3")
    assert result.data_quality["warnings"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"contribution_sgd": "0"},
        {"contribution_sgd": "-1"},
        {"start_date": date(2024, 4, 2), "end_date": date(2024, 4, 1)},
    ],
)
def test_invalid_dca_arguments_are_rejected(kwargs):
    sec = security()
    prices = [price(sec, date(2024, 1, 2)), price(sec, date(2024, 4, 1))]
    with pytest.raises(ValueError):
        run_dca(
            security_row=sec,
            prices=prices,
            fx_rates=[fx(date(2024, 1, 2)), fx(date(2024, 4, 1))],
            **kwargs,
        )


def test_dca_requires_a_trading_date_and_fx_history():
    sec = security()
    with pytest.raises(AnalysisDataError, match="No trading dates"):
        run_dca(
            security_row=sec,
            prices=[price(sec, date(2024, 5, 1))],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 1),
            fx_rates=[],
        )

    with pytest.raises(AnalysisDataError, match="FX history"):
        run_dca(
            security_row=sec,
            prices=[price(sec, date(2024, 1, 2)), price(sec, date(2024, 4, 1))],
            fx_rates=[],
        )


def test_xirr_handles_known_zero_return_unsorted_cash_flows_and_invalid_signs():
    assert xirr([(date(2025, 1, 1), Decimal("110")), (date(2024, 1, 1), Decimal("-100"))]) is not None
    assert xirr([(date(2024, 1, 1), Decimal("-100")), (date(2025, 1, 1), Decimal("100"))]) == pytest.approx(0, abs=1e-10)
    assert xirr([(date(2024, 1, 1), Decimal("100"))]) is None
    assert xirr([(date(2024, 1, 1), Decimal("-100")), (date(2025, 1, 1), Decimal("-100"))]) is None


def test_xirr_matches_an_independent_known_answer():
    result = xirr(
        [
            (date(2025, 1, 1), Decimal("-100")),
            (date(2026, 1, 1), Decimal("110")),
        ]
    )
    expected = (1.10 ** (365.2425 / 365.0)) - 1.0

    assert result is not None
    assert float(result) == pytest.approx(expected, rel=1e-12, abs=1e-12)
