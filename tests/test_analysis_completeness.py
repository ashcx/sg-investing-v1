from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from sg_investing.analysis import AnalysisDataError, analyze_security
from sg_investing.models import AnalysisScenario, CorporateActionType, DistributionPolicy
from tests.helpers import action, dividend, fx, price, security, tax_rule


def analyze(
    *,
    security_row,
    prices,
    fx_rates=(),
    start_date=date(2024, 1, 2),
    end_date=date(2024, 4, 1),
    initial_sgd="1000",
    scenario=None,
    dividends=(),
    corporate_actions=(),
    tax_rules=(),
):
    return analyze_security(
        security=security_row,
        prices=prices,
        fx_rates=fx_rates,
        start_date=start_date,
        end_date=end_date,
        initial_sgd=initial_sgd,
        scenario=scenario,
        dividends=dividends,
        corporate_actions=corporate_actions,
        tax_rules=tax_rules,
    )


def flat_prices(security_row, *dates, close="100"):
    return [price(security_row, trading_date, close) for trading_date in dates]


def test_dividends_disabled_do_not_change_result_or_create_warnings():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=flat_prices(sec, date(2024, 1, 2), date(2024, 4, 1)),
        fx_rates=[fx(date(2024, 1, 2)), fx(date(2024, 4, 1))],
        scenario=AnalysisScenario(dividends_enabled=False),
        dividends=[dividend(sec, date(2024, 2, 1), "10", pay_date=date(2024, 3, 1))],
    )
    assert result.investment["shares"] == Decimal("10") / Decimal("1.30")
    assert result.dividends["gross_foreign_currency"] == Decimal("0")
    assert result.dividends["cash_foreign_currency"] == Decimal("0")
    assert result.data_quality["warnings"] == []


def test_cash_dividend_mode_adds_net_cash_without_increasing_shares():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=flat_prices(sec, date(2024, 1, 2), date(2024, 2, 1), date(2024, 3, 1), date(2024, 4, 1)),
        fx_rates=[fx(date(2024, 1, 2), "1"), fx(date(2024, 4, 1), "1")],
        scenario=AnalysisScenario(reinvest_dividends=False, withholding_tax_enabled=False),
        dividends=[dividend(sec, date(2024, 2, 1), "10", pay_date=date(2024, 3, 1))],
    )
    assert result.investment["shares"] == Decimal("10")
    assert result.dividends["gross_foreign_currency"] == Decimal("100")
    assert result.dividends["cash_foreign_currency"] == Decimal("100")
    assert result.investment["final_value_foreign_currency"] == Decimal("1100")


def test_withholding_disabled_keeps_gross_dividend_as_net():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=flat_prices(sec, date(2024, 1, 2), date(2024, 2, 1), date(2024, 3, 1), date(2024, 4, 1)),
        fx_rates=[fx(date(2024, 1, 2), "1"), fx(date(2024, 4, 1), "1")],
        scenario=AnalysisScenario(reinvest_dividends=False, withholding_tax_enabled=False),
        dividends=[dividend(sec, date(2024, 2, 1), "10", pay_date=date(2024, 3, 1))],
        tax_rules=[tax_rule("0.30")],
    )
    assert result.dividends["withholding_tax_foreign_currency"] == Decimal("0")
    assert result.dividends["net_foreign_currency"] == result.dividends["gross_foreign_currency"]


def test_missing_tax_rule_is_explicit_and_assumes_zero_tax():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=flat_prices(sec, date(2024, 1, 2), date(2024, 2, 1), date(2024, 3, 1), date(2024, 4, 1)),
        fx_rates=[fx(date(2024, 1, 2), "1"), fx(date(2024, 4, 1), "1")],
        scenario=AnalysisScenario(reinvest_dividends=False),
        dividends=[dividend(sec, date(2024, 2, 1), "10", pay_date=date(2024, 3, 1))],
    )
    assert result.dividends["withholding_tax_foreign_currency"] == Decimal("0")
    assert any("No dividend tax rule" in warning for warning in result.data_quality["warnings"])


def test_latest_effective_tax_rule_is_selected_for_the_ex_date():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=flat_prices(sec, date(2024, 1, 2), date(2024, 2, 1), date(2024, 3, 1), date(2024, 4, 1)),
        fx_rates=[fx(date(2024, 1, 2), "1"), fx(date(2024, 4, 1), "1")],
        scenario=AnalysisScenario(reinvest_dividends=False),
        dividends=[dividend(sec, date(2024, 2, 1), "10", pay_date=date(2024, 3, 1))],
        tax_rules=[
            tax_rule("0.30", effective_from=date(1900, 1, 1), rule_id="old"),
            tax_rule("0.20", effective_from=date(2024, 1, 1), rule_id="current"),
        ],
    )
    assert result.dividends["gross_foreign_currency"] == Decimal("100")
    assert result.dividends["withholding_tax_foreign_currency"] == Decimal("20")


def test_accumulating_security_ignores_dividends_with_a_warning():
    sec = security(distribution_policy=DistributionPolicy.ACCUMULATING)
    result = analyze(
        security_row=sec,
        prices=flat_prices(sec, date(2024, 1, 2), date(2024, 2, 1), date(2024, 3, 1), date(2024, 4, 1)),
        fx_rates=[fx(date(2024, 1, 2), "1"), fx(date(2024, 4, 1), "1")],
        dividends=[dividend(sec, date(2024, 2, 1), "10", pay_date=date(2024, 3, 1))],
    )
    assert result.dividends["gross_foreign_currency"] == Decimal("0")
    assert any("accumulating" in warning for warning in result.data_quality["warnings"])


def test_sgd_security_does_not_require_fx_history():
    sec = security(currency="SGD", market="SG", exchange="SGX", income_source_country="SG")
    result = analyze(
        security_row=sec,
        prices=flat_prices(sec, date(2024, 1, 2), date(2024, 4, 1), close="100"),
        initial_sgd="1000",
    )
    assert result.initial_investment_foreign_currency == Decimal("1000")
    assert result.investment["final_value_sgd"] == Decimal("1000")
    assert result.fx == {"start_rate": Decimal("1"), "end_rate": Decimal("1")}


def test_weekend_purchase_and_valuation_use_documented_trading_day_rules():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=[
            price(sec, date(2024, 1, 5), "100"),
            price(sec, date(2024, 1, 8), "110"),
            price(sec, date(2024, 1, 9), "120"),
        ],
        fx_rates=[fx(date(2024, 1, 5), "1"), fx(date(2024, 1, 8), "1")],
        start_date=date(2024, 1, 6),
        end_date=date(2024, 1, 9),
    )
    assert result.period == {"start_date": date(2024, 1, 8), "end_date": date(2024, 1, 9)}


def test_dividend_on_purchase_date_is_not_received():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=flat_prices(sec, date(2024, 1, 2), date(2024, 2, 1), date(2024, 3, 1), date(2024, 4, 1)),
        fx_rates=[fx(date(2024, 1, 2), "1"), fx(date(2024, 4, 1), "1")],
        dividends=[dividend(sec, date(2024, 1, 2), "10", pay_date=date(2024, 2, 1))],
    )
    assert result.dividends["gross_foreign_currency"] == Decimal("0")


def test_same_day_split_is_applied_before_same_day_dividend():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=[
            price(sec, date(2024, 1, 2), "100"),
            price(sec, date(2024, 2, 1), "50"),
            price(sec, date(2024, 3, 1), "50"),
        ],
        fx_rates=[fx(date(2024, 1, 2), "1"), fx(date(2024, 3, 1), "1")],
        start_date=date(2024, 1, 2),
        end_date=date(2024, 3, 1),
        corporate_actions=[action(sec, date(2024, 2, 1), "2")],
        dividends=[dividend(sec, date(2024, 2, 1), "1", pay_date=date(2024, 2, 1))],
        tax_rules=[tax_rule("0")],
    )
    assert result.dividends["gross_foreign_currency"] == Decimal("20")
    assert result.investment["shares"] == Decimal("20.4")


def test_reverse_split_preserves_economic_value():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=[price(sec, date(2024, 1, 2), "100"), price(sec, date(2024, 4, 1), "200")],
        fx_rates=[fx(date(2024, 1, 2), "1"), fx(date(2024, 4, 1), "1")],
        corporate_actions=[action(sec, date(2024, 2, 1), "0.5", action_type=CorporateActionType.REVERSE_SPLIT)],
    )
    assert result.investment["shares"] == Decimal("5")
    assert result.investment["final_value_sgd"] == Decimal("1000")


def test_pay_date_on_non_trading_day_uses_next_trading_day_close():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=[
            price(sec, date(2024, 1, 2), "100"),
            price(sec, date(2024, 2, 1), "100"),
            price(sec, date(2024, 2, 5), "50"),
            price(sec, date(2024, 4, 1), "50"),
        ],
        fx_rates=[fx(date(2024, 1, 2), "1"), fx(date(2024, 4, 1), "1")],
        dividends=[dividend(sec, date(2024, 2, 1), "10", pay_date=date(2024, 2, 3))],
        tax_rules=[tax_rule("0")],
    )
    assert result.investment["shares"] == Decimal("12")


def test_weekend_payment_uses_the_prior_available_fx_rate():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=[
            price(sec, date(2024, 1, 2), "100"),
            price(sec, date(2024, 2, 1), "100"),
            price(sec, date(2024, 2, 5), "50"),
            price(sec, date(2024, 4, 1), "50"),
        ],
        fx_rates=[
            fx(date(2024, 1, 2), "1"),
            fx(date(2024, 2, 2), "1.25"),
            fx(date(2024, 4, 1), "1"),
        ],
        dividends=[dividend(sec, date(2024, 2, 1), "10", pay_date=date(2024, 2, 3))],
        tax_rules=[tax_rule("0")],
    )

    assert result.investment["shares"] == Decimal("12")
    assert result.dividends["gross_sgd_at_payment"] == Decimal("125")


def test_dividend_available_after_valuation_is_not_added_to_end_value():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=[price(sec, date(2024, 1, 2)), price(sec, date(2024, 2, 1)), price(sec, date(2024, 3, 1))],
        fx_rates=[fx(date(2024, 1, 2), "1"), fx(date(2024, 2, 1), "1")],
        end_date=date(2024, 2, 1),
        dividends=[dividend(sec, date(2024, 1, 15), "10", pay_date=date(2024, 3, 1))],
        tax_rules=[tax_rule("0")],
    )
    assert result.investment["shares"] == Decimal("10")
    assert result.dividends["gross_foreign_currency"] == Decimal("0")
    assert result.dividends["withholding_tax_foreign_currency"] == Decimal("0")
    assert result.dividends["net_foreign_currency"] == Decimal("0")
    assert result.dividends["cash_foreign_currency"] == Decimal("0")
    assert any("after valuation" in warning for warning in result.data_quality["warnings"])


def test_dividend_pay_date_before_ex_date_is_rejected():
    sec = security()
    with pytest.raises(AnalysisDataError, match="pay date precedes ex-date"):
        analyze(
            security_row=sec,
            prices=flat_prices(sec, date(2024, 1, 2), date(2024, 2, 1), date(2024, 3, 1)),
            fx_rates=[fx(date(2024, 1, 2), "1"), fx(date(2024, 3, 1), "1")],
            end_date=date(2024, 3, 1),
            dividends=[dividend(sec, date(2024, 2, 1), "1", pay_date=date(2024, 1, 1))],
        )


def test_degenerate_period_has_no_cagr():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=[price(sec, date(2024, 1, 2), "100")],
        fx_rates=[fx(date(2024, 1, 2), "1")],
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 2),
        initial_sgd="1000",
    )

    assert result.returns["cagr"] is None
    assert result.returns["cagr_foreign_currency"] is None


def test_fx_fallback_surfaces_a_staleness_warning():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=[price(sec, date(2024, 1, 2), "100"), price(sec, date(2024, 1, 10), "100")],
        fx_rates=[fx(date(2024, 1, 2), "1.30")],
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 10),
    )

    assert any("stale" in warning for warning in result.data_quality["warnings"])


def test_split_price_return_uses_the_documented_raw_close_convention():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=[price(sec, date(2024, 1, 2), "100"), price(sec, date(2024, 7, 1), "55")],
        fx_rates=[fx(date(2024, 1, 2), "1"), fx(date(2024, 7, 1), "1")],
        start_date=date(2024, 1, 2),
        end_date=date(2024, 7, 1),
        corporate_actions=[action(sec, date(2024, 6, 1), "2")],
    )

    assert result.price_return["foreign_currency"] == Decimal("55") / Decimal("100") - Decimal("1")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"initial_sgd": "0"},
        {"initial_sgd": "-1"},
        {"start_date": date(2024, 4, 2), "end_date": date(2024, 4, 1)},
    ],
)
def test_invalid_analysis_arguments_are_rejected(kwargs):
    sec = security()
    with pytest.raises(ValueError):
        analyze(
            security_row=sec,
            prices=flat_prices(sec, date(2024, 1, 2), date(2024, 4, 1)),
            fx_rates=[fx(date(2024, 1, 2)), fx(date(2024, 4, 1))],
            **kwargs,
        )


def test_duplicate_prices_and_wrong_currency_are_rejected():
    sec = security()
    with pytest.raises(AnalysisDataError, match="duplicate"):
        analyze(
            security_row=sec,
            prices=flat_prices(sec, date(2024, 1, 2), date(2024, 1, 2)),
            fx_rates=[fx(date(2024, 1, 2))],
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 2),
        )

    wrong_currency = price(sec, date(2024, 1, 2), "100").model_copy(update={"currency": "SGD"})
    with pytest.raises(AnalysisDataError, match="currency"):
        analyze(
            security_row=sec,
            prices=[wrong_currency, price(sec, date(2024, 4, 1), "100")],
            fx_rates=[fx(date(2024, 1, 2)), fx(date(2024, 4, 1))],
        )


def test_missing_fx_and_unsupported_date_rule_are_explicit_errors():
    sec = security()
    prices = flat_prices(sec, date(2024, 1, 2), date(2024, 4, 1))
    with pytest.raises(AnalysisDataError, match="FX history"):
        analyze(security_row=sec, prices=prices)

    with pytest.raises(AnalysisDataError, match="Unsupported date rule"):
        analyze(
            security_row=sec,
            prices=prices,
            fx_rates=[fx(date(2024, 1, 2)), fx(date(2024, 4, 1))],
            scenario=AnalysisScenario(purchase_date_rule="middle_of_day"),
        )

    with pytest.raises(AnalysisDataError, match="on or before"):
        analyze(
            security_row=sec,
            prices=prices,
            fx_rates=[fx(date(2024, 4, 1))],
        )


def test_price_resolution_fails_when_no_eligible_observation_exists():
    sec = security()
    prices = [price(sec, date(2024, 1, 2)), price(sec, date(2024, 4, 1))]
    rates = [fx(date(2024, 1, 2)), fx(date(2024, 4, 1))]
    with pytest.raises(AnalysisDataError, match="on or after"):
        analyze(
            security_row=sec,
            prices=prices,
            fx_rates=rates,
            start_date=date(2024, 5, 1),
            end_date=date(2024, 5, 2),
        )
    with pytest.raises(AnalysisDataError, match="on or before"):
        analyze(
            security_row=sec,
            prices=prices,
            fx_rates=rates,
            start_date=date(2023, 12, 1),
            end_date=date(2023, 12, 2),
        )


def test_analysis_result_obeys_core_value_identities():
    sec = security()
    result = analyze(
        security_row=sec,
        prices=flat_prices(sec, date(2024, 1, 2), date(2024, 2, 1), date(2024, 3, 1), date(2024, 4, 1)),
        fx_rates=[fx(date(2024, 1, 2), "1"), fx(date(2024, 4, 1), "1.4")],
        dividends=[dividend(sec, date(2024, 2, 1), "1", pay_date=date(2024, 3, 1))],
        tax_rules=[tax_rule("0.30")],
    )
    dividends = result.dividends
    assert dividends["net_foreign_currency"] == (
        dividends["gross_foreign_currency"] - dividends["withholding_tax_foreign_currency"]
    )
    assert result.investment["final_value_sgd"] == result.investment["final_value_foreign_currency"] * Decimal("1.4")
    assert result.returns["total_return"] == result.investment["final_value_sgd"] / Decimal("1000") - Decimal("1")
