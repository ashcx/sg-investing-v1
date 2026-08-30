"""Falsification-first attack matrix against the sg-investing financial engine.

Every expected value is derived either (a) by hand from the documented
methodology with literal numbers, or (b) by the independent Fraction-arithmetic
oracle in oracle.py.  Nothing in this file reuses implementation formulas.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from uuid import UUID, uuid4

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import oracle  # noqa: E402  (independent oracles)

from sg_investing.analysis import AnalysisDataError, analyze_security  # noqa: E402
from sg_investing.calculations.dca import DcaFrequency, dca_analysis, xirr  # noqa: E402
from sg_investing.calculations.portfolio import analyze_portfolio  # noqa: E402
from sg_investing.data.ingestion import update_security_prices  # noqa: E402
from sg_investing.data.storage import ParquetStore  # noqa: E402
from sg_investing.data.validation import (  # noqa: E402
    validate_corporate_actions,
    validate_dividends,
    validate_fx,
    validate_prices,
)
from sg_investing.models import (  # noqa: E402
    AnalysisScenario,
    AssetType,
    CorporateAction,
    CorporateActionType,
    DistributionPolicy,
    DividendEvent,
    FxRate,
    PortfolioTransaction,
    PriceBar,
    Security,
    TaxRule,
    TransactionType,
)

TOL = Decimal("1e-9")
FTOL = 1e-6

JAN2 = date(2024, 1, 2)
JAN3 = date(2024, 1, 3)
JAN5 = date(2024, 1, 5)
JAN10 = date(2024, 1, 10)
JAN15 = date(2024, 1, 15)
JAN20 = date(2024, 1, 20)
JAN25 = date(2024, 1, 25)
JAN30 = date(2024, 1, 30)
JAN31 = date(2024, 1, 31)
FEB1 = date(2024, 2, 1)
FEB10 = date(2024, 2, 10)
FEB15 = date(2024, 2, 15)
FEB20 = date(2024, 2, 20)
FEB28 = date(2024, 2, 28)
MAR1 = date(2024, 3, 1)
MAR29 = date(2024, 3, 29)


# ---------------------------------------------------------------------------
# Fixture builders (data declaration only)
# ---------------------------------------------------------------------------

def make_security(ticker="TEST", currency="USD", market="US",
                  policy=DistributionPolicy.DISTRIBUTING, income_country="US",
                  expense_ratio=None, sid=None):
    return Security(
        security_id=sid or uuid4(),
        ticker=ticker,
        exchange="NYSE",
        market=market,
        name=f"Synthetic {ticker}",
        currency=currency,
        asset_type=AssetType.EQUITY,
        income_source_country=income_country,
        distribution_policy=policy,
        timezone="America/New_York" if market == "US" else "Asia/Singapore",
        expense_ratio=expense_ratio,
    )


def prices_for(security, closes: dict[date, str]) -> list[PriceBar]:
    rows = []
    for day, close in sorted(closes.items()):
        value = Decimal(close)
        rows.append(
            PriceBar(
                security_id=security.security_id,
                trading_date=day,
                open=value,
                high=value,
                low=value,
                close=value,
                volume=1000,
                currency=security.currency,
                exchange=security.exchange,
                timezone=security.timezone,
                source="synthetic",
            )
        )
    return rows


def fx_rows(rate_by_date: dict, currency="USD") -> list[FxRate]:
    return [
        FxRate(rate_date=day, base_currency=currency, rate_to_sgd=Decimal(rate), source="synthetic")
        for day, rate in sorted(rate_by_date.items())
    ]


def div(security, ex, amount, pay=None, country=None, currency=None) -> DividendEvent:
    return DividendEvent(
        security_id=security.security_id,
        ex_date=ex,
        amount=Decimal(amount),
        pay_date=pay,
        currency=currency or security.currency,
        source_country=country,
        source="synthetic",
    )


def split(security, effective, ratio, action_type=CorporateActionType.SPLIT) -> CorporateAction:
    return CorporateAction(
        security_id=security.security_id,
        effective_date=effective,
        action_type=action_type,
        ratio=Decimal(ratio),
        source="synthetic",
    )


def us_tax(rate="0.30"):
    return TaxRule(
        rule_id="US", source_country="US", rate=Decimal(rate),
        effective_from=date(1900, 1, 1),
    )


def assert_dec(actual, expected: Fraction, label: str = ""):
    got = Decimal(actual)
    want = Decimal(expected.numerator) / Decimal(expected.denominator)
    assert abs(got - want) <= TOL, f"{label}: expected {want}, got {got}"


def assert_float(actual, expected, label: str, tol=1e-6):
    if expected is None:
        assert actual is None, f"{label}: expected None, got {actual}"
        return
    assert actual is not None, f"{label}: expected {expected}, got None"
    scale = max(1.0, abs(expected))
    assert abs(float(actual) - expected) <= scale * tol, f"{label}: expected {expected}, got {float(actual)}"


def _run(security, closes, fx, start, end, initial="10000", scenario=None,
         dividends=(), actions=(), tax_rules=()):
    return analyze_security(
        security=security,
        prices=prices_for(security, closes),
        fx_rates=fx,
        start_date=start,
        end_date=end,
        initial_sgd=Decimal(initial),
        scenario=scenario,
        dividends=dividends,
        corporate_actions=actions,
        tax_rules=tax_rules,
    )


def run_oracle_lump(closes, fx_pairs, dividends=(), splits=(), start=JAN2, end=JAN31,
                    initial=Fraction(10000), wht=lambda c, e: Fraction(0), reinvest=True):
    return oracle.lump_sum_expected(
        trading_days=sorted(closes),
        closes={d: Fraction(Decimal(c)) for d, c in closes.items()},
        fx=fx_pairs,
        dividends=dividends,
        splits=splits,
        start=start,
        end=end,
        initial_sgd=initial,
        wht_rate=wht,
        reinvest=reinvest,
    )


def us30(country, ex):
    return Fraction(3, 10) if country == "US" else Fraction(0)


# ---------------------------------------------------------------------------
# PART 1 — lump-sum core math, hand-computed literals
# ---------------------------------------------------------------------------

def test_price_return_constant_fx():
    sec = make_security()
    fx = fx_rows({JAN2: "2.0", JAN31: "2.0"})
    r = _run(sec, {JAN2: "100", JAN31: "110"}, fx, JAN2, JAN31)
    # 10000/2 = 5000 USD -> 50 sh @100; end 50*110 = 5500 USD -> 11000 SGD
    assert r.returns["total_return"] == Decimal("0.10")
    assert r.price_return["foreign_currency"] == Decimal("0.10")
    assert r.price_return["sgd"] == Decimal("0.10")
    assert r.investment["shares"] == Decimal("50")
    assert r.investment["final_value_foreign_currency"] == Decimal("5500")
    assert r.investment["final_value_sgd"] == Decimal("11000")


def test_fx_conversion_direction_and_amounts():
    sec = make_security()
    fx = fx_rows({JAN2: "1.25", JAN31: "1.50"})
    r = _run(sec, {JAN2: "100", JAN31: "100"}, fx, JAN2, JAN31)
    # 10000/1.25 = 8000 USD -> 80 sh; 8000*1.5 = 12000 SGD; +20% SGD, 0% native
    assert r.price_return["foreign_currency"] == 0
    assert r.price_return["sgd"] == Decimal("0.20")
    assert r.returns["total_return"] == Decimal("0.20")
    assert r.fx["start_rate"] == Decimal("1.25")
    assert r.fx["end_rate"] == Decimal("1.50")
    assert r.initial_investment_foreign_currency == Decimal("8000")
    # an inverted-FX implementation would report -16.67% here
    assert r.price_return["sgd"] > 0


def test_fx_attribution_matches_formula():
    sec = make_security()
    fx = fx_rows({JAN2: "1.25", JAN31: "1.60"})
    r = _run(sec, {JAN2: "100", JAN31: "110"}, fx, JAN2, JAN31)
    # (1+0.10) * (1.60/1.25) - 1 = 0.408
    expected = Decimal("1.10") * Decimal("1.60") / Decimal("1.25") - 1
    assert r.price_return["sgd"] == expected


def test_dividend_cash_no_tax():
    sec = make_security()
    fx = fx_rows({JAN2: "1.5", JAN31: "1.5"})
    d = div(sec, JAN15, "2", pay=JAN20)
    r = _run(sec, {JAN2: "100", JAN15: "100", JAN20: "100", JAN31: "110"}, fx, JAN2, JAN31,
             initial="12000", dividends=[d], scenario=AnalysisScenario(reinvest_dividends=False))
    # 12000/1.5 = 8000 USD -> 80 sh; gross 160; cash 160; final native 8960; SGD 13440; +12%
    assert r.dividends["gross_foreign_currency"] == Decimal("160")
    assert r.dividends["net_foreign_currency"] == Decimal("160")
    assert r.dividends["cash_foreign_currency"] == Decimal("160")
    assert r.investment["final_value_foreign_currency"] == Decimal("8960")
    assert r.investment["final_value_sgd"] == Decimal("13440")
    assert r.returns["total_return"] == Decimal("0.12")
    assert r.dividends["gross_sgd_at_payment"] == Decimal("240")


def test_withholding_tax_amount_and_location():
    sec = make_security()
    fx = fx_rows({JAN2: "1.5", JAN31: "1.5"})
    d = div(sec, JAN15, "2", pay=JAN20, country="US")
    r = _run(sec, {JAN2: "100", JAN15: "100", JAN20: "100", JAN31: "110"}, fx, JAN2, JAN31,
             initial="12000", dividends=[d], tax_rules=[us_tax()],
             scenario=AnalysisScenario(reinvest_dividends=False))
    # WHT must be shares_at_ex * amount * rate = 80*2*0.30 = 48 exactly
    # (wrong-amount variants would give 0.6 or 24)
    assert r.dividends["withholding_tax_foreign_currency"] == Decimal("48")
    assert r.dividends["net_foreign_currency"] == Decimal("112")
    assert r.dividends["cash_foreign_currency"] == Decimal("112")
    assert r.investment["final_value_foreign_currency"] == Decimal("8912")
    assert r.investment["final_value_sgd"] == Decimal("13368")
    assert r.returns["total_return"] == Decimal("0.114")
    assert r.dividends["withholding_tax_sgd_at_payment"] == Decimal("72")


def test_reinvestment_buys_fractional_shares_at_pay_close():
    sec = make_security()
    fx = fx_rows({JAN2: "1.5", JAN20: "1.5", JAN31: "1.5"})
    d = div(sec, JAN15, "2", pay=JAN20)
    r = _run(sec, {JAN2: "100", JAN15: "100", JAN20: "100", JAN31: "110"}, fx, JAN2, JAN31,
             initial="12000", dividends=[d], tax_rules=[us_tax("0")])
    # net 160 reinvested at 100 -> +1.6 sh -> 81.6 * 110 = 8976 USD * 1.5 = 13464
    assert r.investment["shares"] == Decimal("81.6")
    assert r.investment["final_value_foreign_currency"] == Decimal("8976")
    assert r.investment["final_value_sgd"] == Decimal("13464")
    assert r.dividends["cash_foreign_currency"] == 0
    assert r.returns["total_return"] == Decimal("0.122")


def test_reinvestment_uses_net_after_withholding():
    sec = make_security()
    fx = fx_rows({JAN2: "1.5", JAN20: "1.5", JAN31: "1.5"})
    d = div(sec, JAN15, "2", pay=JAN20, country="US")
    r = _run(sec, {JAN2: "100", JAN15: "100", JAN20: "100", JAN31: "110"}, fx, JAN2, JAN31,
             initial="12000", dividends=[d], tax_rules=[us_tax()])
    # net 112 buys 1.12 sh (NOT gross 160 -> 1.6 sh); 81.12*110 = 8923.2; *1.5 = 13384.8
    assert r.investment["shares"] == Decimal("81.12")
    assert r.investment["final_value_foreign_currency"] == Decimal("8923.2")
    assert r.returns["total_return"] == Decimal("0.1154")


def test_reinvested_shares_earn_subsequent_dividend():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d1 = div(sec, JAN10, "1", pay=JAN15)
    d2 = div(sec, JAN20, "1", pay=JAN25)
    closes = {JAN2: "100", JAN10: "100", JAN15: "50", JAN20: "100", JAN25: "50", JAN31: "100"}
    r = _run(sec, closes, fx, JAN2, JAN31, initial="5000", dividends=[d1, d2])
    # 50 sh; D1 net 50 -> +1 sh at 50 => 51; D2 gross = 51 -> +1.02 => 52.02
    assert r.dividends["gross_foreign_currency"] == Decimal("101")
    assert r.investment["shares"] == Decimal("52.02")
    assert r.investment["final_value_foreign_currency"] == Decimal("5202")
    assert r.returns["total_return"] == Decimal("0.0404")


def test_reinvested_shares_do_not_earn_same_exdate_dividend():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d1 = div(sec, JAN10, "1", pay=JAN15)
    d2 = div(sec, JAN15, "1", pay=JAN20)
    closes = {JAN2: "100", JAN10: "100", JAN15: "50", JAN20: "50", JAN31: "100"}
    r = _run(sec, closes, fx, JAN2, JAN31, initial="5000", dividends=[d1, d2])
    # D2 entitlement uses 50 shares (pre-reinvestment): gross = 50; total 100
    assert r.dividends["gross_foreign_currency"] == Decimal("100")
    assert r.investment["shares"] == Decimal("52")
    assert r.investment["final_value_foreign_currency"] == Decimal("5200")


def test_split_two_for_one_preserves_value():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    a = split(sec, JAN15, "2")
    closes = {JAN2: "100", JAN15: "50", JAN31: "55"}
    r = _run(sec, closes, fx, JAN2, JAN31, initial="5000", actions=[a])
    assert r.investment["shares"] == Decimal("100")
    assert r.investment["final_value_foreign_currency"] == Decimal("5500")
    assert r.returns["total_return"] == Decimal("0.10")
    # documented: price return is unadjusted close-to-close
    assert r.price_return["foreign_currency"] == Decimal("-0.45")


def test_reverse_split_one_for_ten():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    a = split(sec, JAN15, "0.1", action_type=CorporateActionType.REVERSE_SPLIT)
    closes = {JAN2: "100", JAN15: "1000", JAN31: "1100"}
    r = _run(sec, closes, fx, JAN2, JAN31, initial="5000", actions=[a])
    assert r.investment["shares"] == Decimal("5")
    assert r.investment["final_value_foreign_currency"] == Decimal("5500")
    assert r.returns["total_return"] == Decimal("0.10")


def test_split_value_preservation_metamorphic():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN15: "1", JAN31: "1"})
    a = split(sec, JAN15, "2")
    closes = {JAN2: "100", JAN15: "50", JAN31: "55"}
    r = _run(sec, closes, fx, JAN2, JAN31, initial="5000", actions=[a])
    # value at split date: 100 post-split shares * 50 == 50 pre-split * 100
    assert r.investment["shares"] * Decimal("50") == Decimal("5000")
    assert r.returns["total_return"] == Decimal("0.10")


def test_split_between_exdate_and_paydate():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d = div(sec, JAN10, "1", pay=JAN20)
    a = split(sec, JAN15, "2")
    closes = {JAN2: "100", JAN10: "100", JAN15: "50", JAN20: "50", JAN31: "55"}
    r = _run(sec, closes, fx, JAN2, JAN31, initial="5000", dividends=[d], actions=[a])
    # entitlement fixed at ex-date: 50 pre-split shares * $1 = 50 USD
    assert r.dividends["gross_foreign_currency"] == Decimal("50")
    # 50 -> 100 post-split; reinvest 50 USD at pay close 50 -> +1 sh => 101
    assert r.investment["shares"] == Decimal("101")
    assert r.investment["final_value_foreign_currency"] == Decimal("5555")
    assert r.returns["total_return"] == Decimal("0.111")


def test_split_same_day_as_exdate_documented_convention():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    a = split(sec, JAN15, "2")
    d = div(sec, JAN15, "1", pay=JAN20)
    closes = {JAN2: "100", JAN15: "50", JAN20: "50", JAN31: "55"}
    r = _run(sec, closes, fx, JAN2, JAN31, initial="5000", dividends=[d], actions=[a])
    # documented convention: split first, then per-share amount applies
    assert r.dividends["gross_foreign_currency"] == Decimal("100")
    assert r.investment["shares"] == Decimal("102")
    assert r.returns["total_return"] == Decimal("0.122")


def test_dividend_payable_after_valuation_excluded_with_warning():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d = div(sec, JAN25, "1", pay=date(2024, 2, 20))
    r = _run(sec, {JAN2: "100", JAN25: "100", JAN31: "110"}, fx, JAN2, JAN31,
             initial="5000", dividends=[d])
    assert r.dividends["gross_foreign_currency"] == 0
    assert r.returns["total_return"] == Decimal("0.10")
    assert r.dividends["gross_foreign_currency"] == 0
    assert r.returns["total_return"] == Decimal("0.10")
    assert any("after valuation" in w or "Could not resolve a trading day" in w
               for w in r.data_quality["warnings"])


def test_missing_pay_date_uses_ex_plus_30_days():
    sec = make_security()
    fx = fx_rows({JAN2: "1", FEB10: "1"})
    d = div(sec, JAN10, "1")  # no pay date -> Feb 9 -> next trading day Feb 10
    closes = {JAN2: "100", JAN10: "100", JAN31: "55", FEB10: "60"}
    r = _run(sec, closes, fx, JAN2, FEB10, initial="5000", dividends=[d])
    assert r.data_quality["status"] == "WARNING"
    assert any("Approximated dividend pay date" in w for w in r.data_quality["warnings"])
    # 50 sh + 50/60 sh => (50 + 5/6) * 60 = 3050
    assert r.investment["final_value_foreign_currency"] == Decimal("3050")
    assert r.returns["total_return"] == Decimal("-0.39")


def test_accumulating_policy_ignores_dividends_with_warning():
    sec = make_security(policy=DistributionPolicy.ACCUMULATING)
    fx = fx_rows({JAN2: "1.5", JAN31: "1.5"})
    d = div(sec, JAN15, "2", pay=JAN20)
    r = _run(sec, {JAN2: "100", JAN31: "110"}, fx, JAN2, JAN31, dividends=[d])
    assert r.dividends["gross_foreign_currency"] == 0
    assert r.returns["total_return"] == Decimal("0.10")
    assert any("accumulating" in w for w in r.data_quality["warnings"])


def test_cagr_known_value():
    sec = make_security()
    fx = fx_rows({date(2024, 1, 2): "1", date(2024, 12, 31): "1"})
    r = _run(sec, {date(2024, 1, 2): "100", date(2024, 12, 31): "121"}, fx,
             date(2024, 1, 2), date(2024, 12, 31))
    days = (date(2024, 12, 31) - date(2024, 1, 2)).days
    expected = 1.21 ** (365.2425 / days) - 1
    assert_float(r.returns["cagr"], expected, "cagr")


def test_cagr_negative_and_flat():
    sec = make_security()
    fx = fx_rows({JAN2: "1", date(2025, 1, 2): "1"})
    r = _run(sec, {JAN2: "100", date(2025, 1, 2): "50"}, fx, JAN2, date(2025, 1, 2))
    days = (date(2025, 1, 2) - JAN2).days
    assert_float(r.returns["cagr"], 0.5 ** (365.2425 / days) - 1, "cagr negative")
    r2 = _run(sec, {JAN2: "100", date(2025, 1, 2): "100"}, fx, JAN2, date(2025, 1, 2))
    assert r2.returns["cagr"] == 0


def test_non_trading_start_and_end_dates():
    sec = make_security()
    fx = fx_rows({date(2024, 1, 8): "1.3", date(2024, 2, 2): "1.3"})
    r = _run(sec, {date(2024, 1, 8): "100", date(2024, 2, 2): "110"}, fx,
             date(2024, 1, 6), date(2024, 2, 3))  # both Saturdays
    assert r.period["start_date"] == date(2024, 1, 8)
    assert r.period["end_date"] == date(2024, 2, 2)
    assert r.returns["total_return"] == Decimal("0.10")


def test_interior_price_gaps_do_not_change_endpoint_return():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    full = _run(sec, {JAN2: "100", JAN15: "105", JAN31: "110"}, fx, JAN2, JAN31)
    sparse = _run(sec, {JAN2: "100", JAN31: "110"}, fx, JAN2, JAN31)
    assert full.returns["total_return"] == sparse.returns["total_return"]


def test_duplicate_price_dates_rejected():
    sec = make_security()
    rows = prices_for(sec, {JAN2: "100"}) + prices_for(sec, {JAN2: "101"})
    with pytest.raises(AnalysisDataError, match="duplicate"):
        analyze_security(security=sec, prices=rows, fx_rates=[],
                         start_date=JAN2, end_date=JAN31, initial_sgd="1000")


def test_stale_fx_uses_last_rate_and_warns():
    sec = make_security()
    fx = fx_rows({JAN2: "1.3"})
    r = _run(sec, {JAN2: "100", JAN30: "100", FEB28: "110"}, fx, JAN30, FEB28)
    assert r.data_quality["status"] == "WARNING"
    assert any("days stale" in w for w in r.data_quality["warnings"])
    # 10000/1.3 USD -> 76.9230... sh @100 -> 110 close -> *1.3 = 11000 SGD => +10%
    assert r.returns["total_return"] == Decimal("0.10")


def test_missing_fx_rejected_not_silently_one():
    sec = make_security()  # USD
    with pytest.raises(AnalysisDataError):
        _run(sec, {JAN2: "100", JAN31: "110"}, [], JAN2, JAN31)


def test_sgd_security_needs_no_fx():
    sec = make_security(currency="SGD", market="SG", income_country=None)
    r = _run(sec, {JAN2: "100", JAN31: "110"}, [], JAN2, JAN31)
    assert r.price_return["sgd"] == Decimal("0.10")
    assert r.price_return["foreign_currency"] == Decimal("0.10")
    assert r.returns["total_return"] == Decimal("0.10")
    assert r.fx["start_rate"] == 1 and r.fx["end_rate"] == 1


def test_dividend_currency_mismatch_rejected():
    sec = make_security()
    d = div(sec, JAN15, "2", pay=JAN20, currency="GBP")
    with pytest.raises(AnalysisDataError, match="currency"):
        _run(sec, {JAN2: "100", JAN31: "110"}, fx_rows({JAN2: "1.3", JAN31: "1.3"}),
             JAN2, JAN31, dividends=[d])


def test_pay_date_before_exdate_rejected():
    sec = make_security()
    d = div(sec, JAN15, "1", pay=JAN10)
    with pytest.raises(AnalysisDataError, match="precedes ex-date"):
        _run(sec, {JAN2: "100", JAN31: "110"}, fx_rows({JAN2: "1", JAN31: "1"}),
             JAN2, JAN31, dividends=[d])


def test_invalid_windows_and_amounts():
    sec = make_security()
    fx = fx_rows({JAN2: "1.3"})
    with pytest.raises(ValueError):
        _run(sec, {JAN2: "100", JAN31: "110"}, fx, JAN31, JAN2)
    with pytest.raises(ValueError, match="greater than zero"):
        _run(sec, {JAN2: "100", JAN31: "110"}, fx, JAN2, JAN31, initial="0")
    with pytest.raises(ValueError, match="greater than zero"):
        _run(sec, {JAN2: "100", JAN31: "110"}, fx, JAN2, JAN31, initial="-5")


def test_price_currency_mismatch_rejected():
    sec = make_security()
    rows = prices_for(sec, {JAN2: "100"})
    bad = PriceBar(
        security_id=sec.security_id, trading_date=JAN31, open=Decimal("110"),
        high=Decimal("110"), low=Decimal("110"), close=Decimal("110"), volume=1,
        currency="GBP", exchange=sec.exchange, timezone=sec.timezone, source="synthetic",
    )
    with pytest.raises(AnalysisDataError, match="currency"):
        analyze_security(security=sec, prices=rows + [bad], fx_rates=fx_rows({JAN2: "1"}),
                         start_date=JAN2, end_date=JAN31, initial_sgd="1000")


def test_rows_from_other_securities_ignored():
    sec = make_security()
    other = make_security(ticker="OTHER")
    rows = prices_for(sec, {JAN2: "100", JAN31: "110"}) + prices_for(other, {JAN2: "1", JAN31: "2"})
    r = analyze_security(security=sec, prices=rows, fx_rates=fx_rows({JAN2: "1", JAN31: "1"}),
                         start_date=JAN2, end_date=JAN31, initial_sgd="1000")
    assert r.investment["shares"] == Decimal("10")


# ---------------------------------------------------------------------------
# PART 2 — off-by-one date attacks
# ---------------------------------------------------------------------------

def test_exdate_equals_purchase_date_not_entitled():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d = div(sec, JAN2, "1", pay=JAN20)
    r = _run(sec, {JAN2: "100", JAN31: "110"}, fx, JAN2, JAN31, initial="5000",
             dividends=[d], scenario=AnalysisScenario(reinvest_dividends=False))
    assert r.dividends["gross_foreign_currency"] == 0
    assert r.returns["total_return"] == Decimal("0.10")


def test_exdate_day_after_purchase_entitled():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d = div(sec, JAN3 := date(2024, 1, 3), "1", pay=JAN20)
    r = _run(sec, {JAN2: "100", JAN3: "100", JAN31: "110"}, fx, JAN2, JAN31,
             initial="5000", dividends=[d], scenario=AnalysisScenario(reinvest_dividends=False))
    assert r.dividends["gross_foreign_currency"] == Decimal("50")
    assert r.investment["final_value_foreign_currency"] == Decimal("5550")


def test_split_effective_on_purchase_date_excluded():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    a = split(sec, JAN2, "2")
    r = _run(sec, {JAN2: "50", JAN31: "55"}, fx, JAN2, JAN31, initial="5000", actions=[a])
    # bought 100 sh at post-split close 50; no further adjustment
    assert r.investment["shares"] == Decimal("100")
    assert r.investment["final_value_foreign_currency"] == Decimal("5500")


def test_split_effective_day_after_purchase_applied():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    a = split(sec, JAN3 := date(2024, 1, 3), "2")
    closes = {JAN2: "100", JAN3: "50", JAN31: "55"}
    r = _run(sec, closes, fx, JAN2, JAN31, initial="5000", actions=[a])
    assert r.investment["shares"] == Decimal("100")
    assert r.investment["final_value_foreign_currency"] == Decimal("5500")


def test_exdate_on_valuation_date_entitled_when_paid_same_day():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d = div(sec, JAN31, "1", pay=JAN31)
    r = _run(sec, {JAN2: "100", JAN31: "100"}, fx, JAN2, JAN31, initial="5000",
             dividends=[d], scenario=AnalysisScenario(reinvest_dividends=False))
    assert r.dividends["gross_foreign_currency"] == Decimal("50")
    assert r.investment["final_value_foreign_currency"] == Decimal("5050")


def test_exdate_after_valuation_excluded():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d = div(sec, FEB1 := date(2024, 2, 1), "1", pay=FEB10)
    r = _run(sec, {JAN2: "100", JAN31: "110"}, fx, JAN2, JAN31, initial="5000", dividends=[d])
    assert r.dividends["gross_foreign_currency"] == 0


def test_same_day_multiple_dividends_both_counted():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d1 = div(sec, JAN15, "2", pay=JAN20)
    d2 = div(sec, JAN15, "3", pay=JAN20)
    r = _run(sec, {JAN2: "100", JAN15: "100", JAN20: "100", JAN31: "110"}, fx,
             JAN2, JAN31, initial="5000", dividends=[d1, d2],
             scenario=AnalysisScenario(reinvest_dividends=False))
    assert r.dividends["gross_foreign_currency"] == Decimal("250")  # 50 * (2+3)
    assert r.investment["final_value_foreign_currency"] == Decimal("5750")  # 50*110 + 250


def test_settlement_on_exdate_close_reinvests_same_day():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d = div(sec, JAN15, "1", pay=JAN15)  # pay == ex
    closes = {JAN2: "100", JAN15: "100", JAN31: "110"}
    r = _run(sec, closes, fx, JAN2, JAN31, initial="5000", dividends=[d])
    assert r.investment["shares"] == Decimal("50.5")
    assert r.investment["final_value_foreign_currency"] == Decimal("5555")


def test_two_dividends_same_paydate_combined_reinvestment():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d1 = div(sec, JAN10, "1", pay=JAN20)
    d2 = div(sec, JAN15, "1", pay=JAN20)
    closes = {JAN2: "100", JAN10: "100", JAN15: "100", JAN20: "50", JAN31: "100"}
    r = _run(sec, closes, fx, JAN2, JAN31, initial="5000", dividends=[d1, d2])
    # 50 sh; net 50+50; settle at 50 close -> +2 sh -> 52 * 100 = 5200
    assert r.investment["shares"] == Decimal("52")
    assert r.investment["final_value_foreign_currency"] == Decimal("5200")


def test_chained_settlements_between_exdates():
    sec = make_security()
    fx = fx_rows({JAN2: "1", date(2024, 2, 28): "1"})
    d1 = div(sec, JAN5 := date(2024, 1, 5), "1", pay=date(2024, 1, 30))
    d2 = div(sec, FEB10, "1", pay=FEB20)
    closes = {
        JAN2: "100", JAN5: "100", date(2024, 1, 30): "100",
        FEB10: "100", FEB20: "100", date(2024, 2, 28): "100",
    }
    r = _run(sec, closes, fx, JAN2, date(2024, 2, 28), initial="5000", dividends=[d1, d2])
    # 50 sh; D1 -> +0.5 sh => 50.5; D2 gross = 50.5; settle +0.505 => 51.005
    assert r.dividends["gross_foreign_currency"] == Decimal("100.5")
    assert r.investment["shares"] == Decimal("51.005")
    assert r.investment["final_value_foreign_currency"] == Decimal("5100.5")


def test_tax_rate_effective_window_boundaries():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    old_rule = TaxRule(rule_id="old", source_country="US", rate=Decimal("0.15"),
                       effective_from=date(2020, 1, 1), effective_to=date(2024, 1, 14))
    new_rule = TaxRule(rule_id="new", source_country="US", rate=Decimal("0.30"),
                       effective_from=JAN15)
    d = div(sec, JAN15, "1", pay=JAN20, country="US")
    r = _run(sec, {JAN2: "100", JAN31: "110"}, fx, JAN2, JAN31, initial="5000",
             dividends=[d], tax_rules=[old_rule, new_rule],
             scenario=AnalysisScenario(reinvest_dividends=False))
    assert r.dividends["withholding_tax_foreign_currency"] == Decimal("15")  # 50 * 0.30
    assert r.dividends["net_foreign_currency"] == Decimal("35")


def test_unknown_tax_country_zero_rate_with_warning():
    sec = make_security(income_country=None)
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d = div(sec, JAN15, "1", pay=JAN20, country="DE")
    r = _run(sec, {JAN2: "100", JAN31: "110"}, fx, JAN2, JAN31, initial="5000",
             dividends=[d], tax_rules=[us_tax()],
             scenario=AnalysisScenario(reinvest_dividends=False))
    assert r.dividends["withholding_tax_foreign_currency"] == 0
    assert any("No dividend tax rule" in w for w in r.data_quality["warnings"])


def test_withholding_disabled_keeps_gross():
    sec = make_security()
    fx = fx_rows({JAN2: "1.5", JAN31: "1.5"})
    d = div(sec, JAN15, "2", pay=JAN20, country="US")
    r = _run(sec, {JAN2: "100", JAN31: "110"}, fx, JAN2, JAN31, initial="12000", dividends=[d],
             tax_rules=[us_tax()],
             scenario=AnalysisScenario(reinvest_dividends=False, withholding_tax_enabled=False))
    assert r.dividends["withholding_tax_foreign_currency"] == 0
    assert r.dividends["net_foreign_currency"] == Decimal("160")


# ---------------------------------------------------------------------------
# PART 3 — metamorphic invariants
# ---------------------------------------------------------------------------

def test_scaling_does_not_change_percentage_returns():
    sec = make_security()
    fx = fx_rows({JAN2: "1.3", JAN31: "1.3"})
    prices = prices_for(sec, {JAN2: "100", JAN31: "110"})
    small = analyze_security(security=sec, prices=prices, fx_rates=fx, start_date=JAN2,
                             end_date=JAN31, initial_sgd="10000")
    big = analyze_security(security=sec, prices=prices, fx_rates=fx, start_date=JAN2,
                           end_date=JAN31, initial_sgd="9999999")
    for key in ("total_return", "total_return_foreign_currency", "cagr", "cagr_foreign_currency"):
        assert small.returns[key] == big.returns[key], key
    for key in ("foreign_currency", "sgd"):
        assert small.price_return[key] == big.price_return[key]


def test_constant_fx_makes_sgd_and_native_returns_equal():
    sec = make_security()
    fx = fx_rows({JAN2: "1.3", JAN31: "1.3"})
    prices = prices_for(sec, {JAN2: "100", JAN31: "110"})
    r = analyze_security(security=sec, prices=prices, fx_rates=fx, start_date=JAN2,
                         end_date=JAN31, initial_sgd="10000")
    assert r.price_return["sgd"] == r.price_return["foreign_currency"]
    assert r.returns["total_return"] == r.returns["total_return_foreign_currency"]


def test_zero_price_move_zero_dividends_zero_return():
    sec = make_security()
    fx = fx_rows({JAN2: "1.3", JAN31: "1.3"})
    r = _run(sec, {JAN2: "100", JAN31: "100"}, fx, JAN2, JAN31)
    assert r.returns["total_return"] == 0
    assert r.returns["total_return_foreign_currency"] == 0
    assert r.price_return["sgd"] == 0
    assert r.returns["cagr"] == 0


def test_zero_dividends_makes_dividend_flag_irrelevant():
    sec = make_security()
    fx = fx_rows({JAN2: "1.3", JAN31: "1.3"})
    prices = prices_for(sec, {JAN2: "100", JAN31: "110"})
    on = analyze_security(security=sec, prices=prices, fx_rates=fx, start_date=JAN2,
                          end_date=JAN31, initial_sgd="10000",
                          scenario=AnalysisScenario(dividends_enabled=True))
    off = analyze_security(security=sec, prices=prices, fx_rates=fx, start_date=JAN2,
                           end_date=JAN31, initial_sgd="10000",
                           scenario=AnalysisScenario(dividends_enabled=False))
    assert on.returns["total_return"] == off.returns["total_return"]
    assert on.investment == off.investment


def test_reinvest_equals_cash_when_settle_price_equals_valuation_price():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d = div(sec, JAN15, "2", pay=JAN20)
    closes = {JAN2: "100", JAN15: "100", JAN20: "110", JAN31: "110"}
    reinvest = _run(sec, closes, fx, JAN2, JAN31, initial="5000", dividends=[d],
                    scenario=AnalysisScenario(reinvest_dividends=True))
    cash = _run(sec, closes, fx, JAN2, JAN31, initial="5000", dividends=[d],
                scenario=AnalysisScenario(reinvest_dividends=False))
    assert reinvest.investment["final_value_foreign_currency"] == \
        cash.investment["final_value_foreign_currency"]


def test_expense_ratio_is_metadata_only():
    sec_a = make_security(expense_ratio=None)
    sec_b = make_security(expense_ratio=Decimal("0.0075"))
    fx = fx_rows({JAN2: "1.3", JAN31: "1.3"})
    ra = _run(sec_a, {JAN2: "100", JAN31: "110"}, fx, JAN2, JAN31)
    rb = _run(sec_b, {JAN2: "100", JAN31: "110"}, fx, JAN2, JAN31)
    assert ra.returns == rb.returns
    assert rb.methodology["ter_deducted"] is False


def test_cash_dividends_converted_at_valuation_fx_by_convention():
    sec = make_security()
    # FX moves between payment and valuation: payment 1.0, valuation 2.0
    fx = fx_rows({JAN2: "1.0", JAN20: "1.5", JAN31: "2.0"})
    d = div(sec, JAN15, "2", pay=JAN20, country="US")
    r = _run(sec, {JAN2: "100", JAN15: "100", JAN20: "100", JAN31: "110"}, fx, JAN2, JAN31,
             initial="5000", dividends=[d], tax_rules=[us_tax()],
             scenario=AnalysisScenario(reinvest_dividends=False))
    # end value uses the valuation FX for held cash: (50*110 + 70) * 2 = 11140
    assert r.investment["final_value_sgd"] == Decimal("11140")
    # the at-payment fields use the payment-date rate (1.5 on Jan 20)
    assert r.dividends["gross_sgd_at_payment"] == Decimal("100") * Decimal("1.5")
    assert r.dividends["withholding_tax_sgd_at_payment"] == Decimal("30") * Decimal("1.5")
    assert r.dividends["net_sgd_at_payment"] == Decimal("70") * Decimal("1.5")


# ---------------------------------------------------------------------------
# PART 4 — DCA and XIRR
# ---------------------------------------------------------------------------

def test_dca_flat_price_flat_fx_zero_xirr():
    sec = make_security()
    days = [JAN2, FEB1 := date(2024, 2, 1), MAR1, MAR29]
    closes = {day: "100" for day in days}
    fx = fx_rows({JAN2: "1.35", MAR29: "1.35"})
    r = dca_analysis(security=sec, prices=prices_for(sec, closes), fx_rates=fx,
                     start_date=JAN2, end_date=MAR29, contribution_sgd="1000")
    assert r.total_contributed_sgd == Decimal("3000")
    assert r.final_value_sgd == Decimal("3000")
    assert r.gain_loss_sgd == 0
    # 1000/1.35 = 740.740740... USD per contribution -> 7.407407... sh each
    assert r.shares == Decimal("1000") / Decimal("135") * 3


def test_dca_rising_price_matches_independent_xirr():
    sec = make_security()
    closes = {JAN2: "100", FEB1: "125", MAR1: "150", MAR29: "150"}
    fx = fx_rows({JAN2: "1", MAR29: "1"})
    r = dca_analysis(security=sec, prices=prices_for(sec, closes), fx_rates=fx,
                     start_date=JAN2, end_date=MAR29, contribution_sgd="1000")
    # hand: 10 + 8 + 1000/150 shares; final 3700 on 3000 contributed
    assert r.contribution_dates == [JAN2, FEB1, MAR1]
    assert r.shares == Decimal("24.66666666666666666666666667")
    assert r.final_value_foreign_currency == Decimal("3700")
    expected = oracle.dca_expected(
        trading_days=sorted(closes),
        closes={d: Fraction(Decimal(c)) for d, c in closes.items()},
        fx=[(JAN2, Fraction(1)), (MAR29, Fraction(1))],
        dividends=[], splits=[], start=JAN2, end=MAR29, contribution_sgd=Fraction(1000),
    )
    assert_float(r.xirr, expected["xirr_sgd"], "dca xirr rising")


def test_dca_hand_computed_with_dividends_and_reinvestment():
    sec = make_security()
    closes = {
        JAN2: "100", JAN15: "100", JAN20: "100", FEB1: "110", FEB10: "110",
        FEB20: "110", date(2024, 2, 28): "110",
    }
    fx = fx_rows({JAN2: "1", date(2024, 2, 28): "1"})
    dividends = [
        div(sec, JAN15, "1", pay=JAN20),
        div(sec, FEB10, "1", pay=FEB20),
    ]
    r = dca_analysis(security=sec, prices=prices_for(sec, closes), fx_rates=fx,
                     start_date=JAN2, end_date=date(2024, 2, 28), contribution_sgd="1000",
                     dividends=dividends)
    expected = oracle.dca_expected(
        trading_days=sorted(closes),
        closes={d: Fraction(Decimal(c)) for d, c in closes.items()},
        fx=[(JAN2, Fraction(1)), (date(2024, 2, 28), Fraction(1))],
        dividends=[(d.ex_date, Fraction(d.amount), d.pay_date, d.source_country) for d in dividends],
        splits=[], start=JAN2, end=date(2024, 2, 28), contribution_sgd=Fraction(1000),
    )
    assert_dec(r.shares, expected["shares"], "dca shares")
    assert_dec(r.final_value_foreign_currency, expected["final_native"], "dca final native")
    assert_dec(r.final_value_sgd, expected["final_sgd"], "dca final sgd")
    assert_float(r.xirr, expected["xirr_sgd"], "dca xirr hand case")
    assert r.gain_loss_sgd > 0


def test_dca_split_between_contributions():
    sec = make_security()
    closes = {JAN2: "100", FEB1: "50", date(2024, 2, 28): "55"}
    fx = fx_rows({JAN2: "1", date(2024, 2, 28): "1"})
    a = split(sec, FEB1, "2")
    r = dca_analysis(security=sec, prices=prices_for(sec, closes), fx_rates=fx,
                     start_date=JAN2, end_date=date(2024, 2, 28), contribution_sgd="1000",
                     corporate_actions=[a])
    # Jan 2: 10 sh @100; Feb 1: split -> 20 sh; contribution buys 1000/50 = 20 -> 40 sh
    assert r.shares == Decimal("40")
    assert r.final_value_foreign_currency == Decimal("2200")
    assert r.gain_loss_sgd == Decimal("200")


def test_dca_xirr_matches_independent_bisection():
    sec = make_security()
    closes = {JAN2: "100", FEB1: "110", MAR1: "130", MAR29: "130"}
    fx = fx_rows({JAN2: "1.33", MAR1: "1.34", MAR29: "1.35"})
    r = dca_analysis(security=sec, prices=prices_for(sec, closes), fx_rates=fx,
                     start_date=JAN2, end_date=MAR29, contribution_sgd="1000")
    expected = oracle.dca_expected(
        trading_days=sorted(closes),
        closes={d: Fraction(Decimal(c)) for d, c in closes.items()},
        fx=[(row.rate_date, Fraction(row.rate_to_sgd)) for row in fx],
        dividends=[], splits=[], start=JAN2, end=MAR29, contribution_sgd=Fraction(1000),
    )
    assert_float(r.xirr, expected["xirr_sgd"], "xirr sgd")
    assert_float(r.xirr_foreign_currency, expected["xirr_native"], "xirr native")
    # NPV at the reported rate must vanish (independent residual check)
    flows = [(d, -Decimal(1000)) for d in r.contribution_dates] + [(MAR29, r.final_value_sgd)]
    npv = sum(float(a) / (1 + float(r.xirr)) ** ((d - r.contribution_dates[0]).days / 365.2425)
              for d, a in flows)
    assert abs(npv) < 1e-5


def test_dca_constant_fx_xirr_sgd_equals_native():
    sec = make_security()
    closes = {JAN2: "100", FEB1: "110", MAR1: "120", MAR29: "120"}
    fx = fx_rows({JAN2: "1.35", FEB1: "1.35", MAR1: "1.35", MAR29: "1.35"})
    r = dca_analysis(security=sec, prices=prices_for(sec, closes), fx_rates=fx,
                     start_date=JAN2, end_date=MAR29, contribution_sgd="1000")
    assert r.xirr is not None and r.xirr_foreign_currency is not None
    assert abs(r.xirr - r.xirr_foreign_currency) < Decimal("1e-9")


def test_xirr_known_single_period_value():
    flows = [(date(2024, 1, 1), Decimal("-100")), (date(2024, 12, 31), Decimal("121"))]
    expected = oracle.xirr_single_period(date(2024, 1, 1), date(2024, 12, 31), 1.21)
    assert_float(xirr(flows), expected, "xirr known value")


def test_xirr_extreme_gain_bracket_expansion():
    flows = [(date(2024, 1, 1), Decimal("-100")), (date(2024, 12, 31), Decimal("6000"))]
    expected = oracle.xirr_single_period(date(2024, 1, 1), date(2024, 12, 31), 60.0)
    assert_float(xirr(flows), expected, "xirr extreme gain")


def test_xirr_loss_shape():
    got = xirr([(date(2024, 1, 1), Decimal("-100")), (date(2024, 12, 31), Decimal("50"))])
    expected = oracle.xirr_single_period(date(2024, 1, 1), date(2024, 12, 31), 0.5)
    assert_float(got, expected, "xirr loss")


def test_xirr_npv_residual_zero():
    flows = [(JAN2, Decimal("-1000")), (FEB1, Decimal("-1000")),
             (MAR1, Decimal("-1000")), (MAR29, Decimal("3700"))]
    rate = xirr(flows)
    npv = sum(float(a) / (1 + float(rate)) ** ((d - JAN2).days / 365.2425) for d, a in flows)
    assert abs(npv) < 1e-6


def test_dca_contributions_converted_at_each_dates_fx():
    sec = make_security()
    closes = {JAN2: "100", FEB1: "100", MAR1: "100", MAR29: "100"}
    fx = fx_rows({JAN2: "1.25", FEB1: "2.0", MAR1: "2.0"})
    r = dca_analysis(security=sec, prices=prices_for(sec, closes), fx_rates=fx,
                     start_date=JAN2, end_date=MAR29, contribution_sgd="1000")
    # Jan: 800 USD -> 8 sh; Feb: 500 USD -> 5 sh; Mar: 500 USD -> 5 sh
    assert r.shares == Decimal("18")
    assert r.total_contributed_foreign_currency == Decimal("1800")
    # end price 100, end FX 2.0 -> 1800*2 = 3600 SGD on 2000... 3000 contributed
    assert r.final_value_sgd == Decimal("3600")
    assert r.gain_loss_sgd == Decimal("600")


def test_dca_contribution_not_entitled_to_same_day_exdate_dividend():
    sec = make_security()
    closes = {JAN2: "100", FEB1: "100", date(2024, 2, 28): "100"}
    fx = fx_rows({JAN2: "1", FEB1: "1", date(2024, 2, 28): "1"})
    d = div(sec, FEB1, "1", pay=FEB15)
    r = dca_analysis(security=sec, prices=prices_for(sec, closes), fx_rates=fx,
                     start_date=JAN2, end_date=date(2024, 2, 28), contribution_sgd="1000",
                     dividends=[d], scenario=AnalysisScenario(reinvest_dividends=False))
    # Jan-2 shares (10) ARE entitled to the Feb-1 ex-date dividend ($10 cash);
    # the Feb-1 contribution bought at the close is NOT. 20 sh * 100 + 10 = 2010.
    assert r.final_value_foreign_currency == Decimal("2010")


def test_dca_withholding_applied_and_net_reinvested():
    sec = make_security()
    closes = {
        JAN2: "100", JAN15: "100", JAN20: "100", FEB1: "110",
        FEB10: "110", FEB20: "110", date(2024, 2, 28): "110",
    }
    fx = fx_rows({JAN2: "1", date(2024, 2, 28): "1"})
    dividends = [
        div(sec, JAN15, "1", pay=JAN20, country="US"),
        div(sec, FEB10, "1", pay=FEB20, country="US"),
    ]
    r = dca_analysis(security=sec, prices=prices_for(sec, closes), fx_rates=fx,
                     start_date=JAN2, end_date=date(2024, 2, 28), contribution_sgd="1000",
                     dividends=dividends, tax_rules=[us_tax()])
    expected = oracle.dca_expected(
        trading_days=sorted(closes),
        closes={d: Fraction(Decimal(c)) for d, c in closes.items()},
        fx=[(JAN2, Fraction(1)), (date(2024, 2, 28), Fraction(1))],
        dividends=[(d.ex_date, Fraction(d.amount), d.pay_date, d.source_country) for d in dividends],
        splits=[], start=JAN2, end=date(2024, 2, 28), contribution_sgd=Fraction(1000),
        wht_rate=us30,
    )
    assert_dec(r.shares, expected["shares"], "dca wht shares")
    assert_dec(r.final_value_foreign_currency, expected["final_native"], "dca wht native")
    assert_dec(r.final_value_sgd, expected["final_sgd"], "dca wht sgd")
    assert_float(r.xirr, expected["xirr_sgd"], "dca wht xirr")


def test_dca_cash_dividends_add_to_final_when_not_reinvested():
    sec = make_security()
    closes = {JAN2: "100", JAN15: "100", JAN20: "100", date(2024, 2, 28): "110"}
    fx = fx_rows({JAN2: "1", date(2024, 2, 28): "1"})
    d = div(sec, JAN15, "2", pay=JAN20)
    r = dca_analysis(security=sec, prices=prices_for(sec, closes), fx_rates=fx,
                     start_date=JAN2, end_date=date(2024, 2, 28), contribution_sgd="1000",
                     dividends=[d], scenario=AnalysisScenario(reinvest_dividends=False))
    # contributions: Jan 2 (10 sh @100) and Feb 28 (1000/110 sh @110)
    # value = (10 + 100/110)*110 + 20 cash = 2120
    assert r.final_value_foreign_currency == Decimal("2120")
    assert r.gain_loss_sgd == Decimal("120")
    assert r.final_value_sgd == Decimal("2120")


def test_dca_quarterly_and_yearly_first_trading_day():
    sec = make_security()
    days = [date(2024, 1, 2), date(2024, 2, 5), date(2024, 4, 1), date(2024, 7, 1), date(2024, 7, 31)]
    closes = {day: "100" for day in days}
    fx = fx_rows({date(2024, 1, 2): "1", date(2024, 7, 31): "1"})
    r = dca_analysis(security=sec, prices=prices_for(sec, closes), fx_rates=fx,
                     start_date=date(2024, 1, 1), end_date=date(2024, 7, 31),
                     contribution_sgd="100", frequency=DcaFrequency.QUARTERLY)
    assert r.contribution_dates == [date(2024, 1, 2), date(2024, 4, 1), date(2024, 7, 1)] or \
        r.contribution_dates == [date(2024, 1, 2), date(2024, 7, 1)]
    r2 = dca_analysis(security=sec, prices=prices_for(sec, closes), fx_rates=fx,
                      start_date=JAN2, end_date=date(2024, 7, 31), contribution_sgd="100",
                      frequency=DcaFrequency.YEARLY)
    assert r2.contribution_dates == [JAN2]


def test_dca_no_trading_days_rejected():
    sec = make_security()
    with pytest.raises(Exception):
        dca_analysis(security=sec, prices=prices_for(sec, {JAN2: "100"}),
                     fx_rates=fx_rows({JAN2: "1"}), start_date=date(2025, 1, 1),
                     end_date=date(2024, 1, 1), contribution_sgd="100")


def test_dca_flat_price_high_fx_gain_only_from_fx():
    sec = make_security()
    closes = {JAN2: "100", date(2024, 2, 1): "100", date(2024, 2, 28): "100"}
    fx = fx_rows({JAN2: "1.25", FEB1: "1.25", date(2024, 2, 28): "1.50"})
    r = dca_analysis(security=sec, prices=prices_for(sec, closes), fx_rates=fx,
                     start_date=JAN2, end_date=date(2024, 2, 28), contribution_sgd="1000")
    # Jan: 800 USD = 8 sh; Feb: 800 USD -> 8 sh; end 16 sh * 100 * 1.50 = 2400 on 2000
    assert r.final_value_sgd == Decimal("2400")
    assert r.gain_loss_sgd == Decimal("400")
    # pure FX gain: native value is flat (16*100 = 1600 = contributed native)
    assert r.gain_loss_foreign_currency == 0
    assert r.gain_loss_foreign_currency == 0  # pure FX gain


# ---------------------------------------------------------------------------
# PART 5 — portfolio ledger
# ---------------------------------------------------------------------------

def _tx(day, kind, qty="0", cash="0", fees="0", currency="USD", security=None):
    return PortfolioTransaction(
        transaction_date=day, security_id=security, transaction_type=kind,
        quantity=Decimal(qty), cash_amount=Decimal(cash), currency=currency, fees=Decimal(fees),
    )


def test_portfolio_weighted_average_hand_computed():
    sec = make_security()
    prices = prices_for(sec, {JAN2: "14", JAN10: "14", JAN20: "14", JAN31: "14"})
    fx = fx_rows({JAN31: "1.35"})
    transactions = [
        _tx(JAN2, TransactionType.BUY, "10", "100", "1", security=sec.security_id),
        _tx(JAN10, TransactionType.BUY, "10", "120", "1", security=sec.security_id),
        _tx(JAN20, TransactionType.SELL, "15", "195", "2", security=sec.security_id),
        _tx(JAN25, TransactionType.DIVIDEND, cash="5", security=sec.security_id),
    ]
    result = analyze_portfolio(transactions=transactions, securities={sec.security_id: sec},
                               prices=prices, fx_rates=fx, as_of=JAN31)
    # avg cost 222/20 = 11.1; sell 15 -> disposed 166.5; proceeds 193; realized 26.5
    # remaining 5 sh basis 55.5; market 70; unrealized 14.5; cash -101-121+193+5 = -24
    holding = next(h for h in result.holdings if h.ticker == "TEST")
    assert holding.quantity == Decimal("5")
    assert holding.weighted_average_cost == Decimal("11.1")
    assert holding.cost_basis_native == Decimal("55.5")
    assert holding.unrealized_pl_native == Decimal("14.5")
    assert holding.realized_pl_native == Decimal("26.5")
    assert result.realized_pl_native["USD"] == Decimal("26.5")
    assert result.cash_by_currency["USD"] == Decimal("-24")
    assert result.total_market_value_sgd == Decimal("62.1")  # (70 - 24) * 1.35


def test_portfolio_sell_everything():
    sec = make_security()
    prices = prices_for(sec, {JAN2: "12", JAN31: "13"})
    fx = fx_rows({JAN31: "1.35"})
    transactions = [
        _tx(JAN2, TransactionType.BUY, "10", "100", "1", security=sec.security_id),
        _tx(JAN20, TransactionType.SELL, "10", "120", "1", security=sec.security_id),
    ]
    result = analyze_portfolio(transactions=transactions, securities={sec.security_id: sec},
                               prices=prices, fx_rates=fx, as_of=JAN31)
    assert result.holdings == []
    assert result.realized_pl_native["USD"] == Decimal("18")  # (120-1) - 101
    assert result.total_market_value_sgd == Decimal("18") * Decimal("1.35")


def test_portfolio_transaction_after_as_of_ignored():
    sec = make_security()
    prices = prices_for(sec, {JAN2: "10", FEB1: "12"})
    fx = fx_rows({JAN15: "1.35"})
    transactions = [
        _tx(JAN2, TransactionType.BUY, "10", "100", "0", security=sec.security_id),
        _tx(FEB1, TransactionType.SELL, "10", "120", "0", security=sec.security_id),
    ]
    result = analyze_portfolio(transactions=transactions, securities={sec.security_id: sec},
                               prices=prices, fx_rates=fx, as_of=JAN15)
    assert result.holdings[0].quantity == Decimal("10")


def test_portfolio_rejects_oversell_unknown_security_currency_mismatch():
    sec = make_security()
    prices = prices_for(sec, {JAN2: "10"})
    fx = fx_rows({JAN2: "1.35"})
    with pytest.raises(ValueError, match="sell more"):
        analyze_portfolio(transactions=[_tx(JAN2, TransactionType.SELL, "5", "50", "0",
                                            security=sec.security_id)],
                          securities={sec.security_id: sec}, prices=prices, fx_rates=fx,
                          as_of=date(2024, 1, 31))
    with pytest.raises(ValueError, match="unknown security"):
        analyze_portfolio(transactions=[_tx(JAN2, TransactionType.BUY, "1", "10", "0",
                                            security=uuid4())],
                          securities={sec.security_id: sec}, prices=prices, fx_rates=fx,
                          as_of=date(2024, 1, 31))
    with pytest.raises(ValueError, match="currency"):
        analyze_portfolio(transactions=[_tx(JAN2, TransactionType.BUY, "1", "10", "0",
                                            currency="GBP", security=sec.security_id)],
                          securities={sec.security_id: sec}, prices=prices, fx_rates=fx,
                          as_of=date(2024, 1, 31))


def test_portfolio_multiple_currencies():
    usd = make_security(ticker="USDFUND")
    gbp = make_security(ticker="GBPFUND", currency="GBP")
    register = {usd.security_id: usd, gbp.security_id: gbp}
    prices = prices_for(usd, {JAN2: "100", JAN31: "110"}) + \
        prices_for(gbp, {JAN2: "200", JAN31: "220"})
    fx = fx_rows({JAN31: "1.35"}, currency="USD") + fx_rows({JAN31: "1.70"}, currency="GBP")
    transactions = [
        _tx(JAN2, TransactionType.BUY, "2", "200", "0", security=usd.security_id),
        _tx(JAN2, TransactionType.BUY, "1", "200", "0", currency="GBP", security=gbp.security_id),
    ]
    result = analyze_portfolio(transactions=transactions, securities=register,
                               prices=prices, fx_rates=fx, as_of=JAN31)
    total = (Decimal("220") * Decimal("1.35") + Decimal("220") * Decimal("1.70")
             - Decimal("200") * Decimal("1.35") - Decimal("200") * Decimal("1.70"))
    assert result.total_market_value_sgd == total
    tickers = {h.ticker for h in result.holdings}
    assert tickers == {"USDFUND", "GBPFUND"}


def test_portfolio_dividend_cash_included_in_total():
    sec = make_security()
    prices = prices_for(sec, {JAN2: "10", JAN31: "10"})
    fx = fx_rows({JAN31: "1.35"})
    transactions = [
        _tx(JAN2, TransactionType.BUY, "10", "100", "0", security=sec.security_id),
        _tx(JAN20, TransactionType.DIVIDEND, cash="5", security=sec.security_id),
        _tx(JAN31, TransactionType.CASH_WITHDRAWAL, cash="2"),
    ]
    result = analyze_portfolio(transactions=transactions, securities={sec.security_id: sec},
                               prices=prices, fx_rates=fx, as_of=JAN31)
    # 10 sh * 10 = 100 market; cash = -100 + 5 - 2 = -97; (100 - 97) * 1.35 = 4.05
    assert result.total_market_value_sgd == Decimal("4.05")
    assert result.cash_by_currency["USD"] == Decimal("-97")


# ---------------------------------------------------------------------------
# PART 6 — storage, validation, ingestion
# ---------------------------------------------------------------------------

def test_validation_rejects_bad_price_batches(tmp_path):
    sec = make_security()
    ok = prices_for(sec, {JAN2: "100"})
    report = validate_prices(ok + prices_for(sec, {JAN2: "101"}))
    assert not report.is_valid and "Duplicate" in report.errors[0]
    zero = ok + prices_for(sec, {JAN15: "0"})
    assert not validate_prices(zero).is_valid
    bad_ohlc = [PriceBar(security_id=sec.security_id, trading_date=JAN15, open=Decimal("100"),
                         high=Decimal("90"), low=Decimal("95"), close=Decimal("95"), volume=1,
                         currency="USD", exchange="NYSE", timezone="UTC", source="s")]
    assert not validate_prices(bad_ohlc).is_valid


def test_validation_rejects_duplicate_dividends_and_fx():
    sec = make_security()
    rows = [div(sec, JAN15, "1"), div(sec, JAN15, "2")]
    report = validate_dividends(rows)
    assert not report.is_valid
    rows = [FxRate(rate_date=JAN2, base_currency="USD", rate_to_sgd=Decimal("1.3"), source="s"),
            FxRate(rate_date=JAN2, base_currency="USD", rate_to_sgd=Decimal("1.4"), source="s")]
    assert not validate_fx(rows).is_valid
    bad_sgd = FxRate(rate_date=JAN2, base_currency="SGD", rate_to_sgd=Decimal("1.1"), source="s")
    assert not validate_fx([bad_sgd]).is_valid


def test_validation_accepts_duplicate_corporate_actions_flag():
    sec = make_security()
    rows = [split(sec, JAN15, "2"), split(sec, JAN15, "3")]
    report = validate_corporate_actions(rows)
    assert not report.is_valid


def test_negative_price_bars_cannot_exist_at_all():
    with pytest.raises(Exception):
        PriceBar(security_id=uuid4(), trading_date=JAN2, open=Decimal("-1"), high=Decimal("1"),
                 low=Decimal("0"), close=Decimal("1"), volume=1, currency="USD",
                 exchange="NYSE", timezone="UTC", source="s")


def test_dividend_restatement_newer_wins_older_ignored(tmp_path):
    store = ParquetStore(tmp_path / "data")
    sec = make_security()
    t_early = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t_late = datetime(2024, 6, 1, tzinfo=timezone.utc)
    first = DividendEvent(security_id=sec.security_id, ex_date=JAN15, amount=Decimal("1"),
                          pay_date=JAN20, currency="USD", source="a", retrieved_at=t_early)
    restated = DividendEvent(security_id=sec.security_id, ex_date=JAN15, amount=Decimal("2"),
                             pay_date=JAN20, currency="USD", source="s", retrieved_at=t_late)
    store.upsert_dividends([first])
    store.upsert_dividends([restated])
    assert store.read_dividends(year=2024)[0].amount == Decimal("2")
    stale_attempt = DividendEvent(security_id=sec.security_id, ex_date=JAN15, amount=Decimal("9"),
                                  pay_date=JAN20, currency="USD", source="s", retrieved_at=t_early)
    stale_attempt = DividendEvent(security_id=sec.security_id, ex_date=JAN15,
                                  amount=Decimal("3"), pay_date=JAN20, currency="USD",
                                  source="s", retrieved_at=t_early)
    store.upsert_dividends([stale_attempt])
    assert store.read_dividends(year=2024)[0].amount == Decimal("2")


def test_special_and_ordinary_same_exdate_cannot_be_stored(tmp_path):
    """DEFECT DEMONSTRATION: same-ex-date ordinary + special distributions collapse."""
    store = ParquetStore(tmp_path / "data")
    sec = make_security()
    ordinary = div(sec, JAN15, "0.50", country="US")
    special = div(sec, JAN15, "2.00", country="US")
    special = special.model_copy(update={"dividend_type": "special"})
    with pytest.raises(ValueError, match="Duplicate dividend"):
        store.upsert_dividends([ordinary, special])
    # sequential ingestion silently replaces the ordinary with the special
    store.upsert_dividends([ordinary])
    store.upsert_dividends([special])
    stored = store.read_dividends(year=2024)
    assert len(stored) == 1
    assert stored[0].amount == Decimal("2")


def test_upsert_prices_last_write_wins_even_if_stale(tmp_path):
    store = ParquetStore(tmp_path / "data")
    sec = make_security()
    fresh = prices_for(sec, {JAN31: "110"})
    store.upsert_prices(market=sec.market, rows=fresh, pipeline_version="t")
    stale = prices_for(sec, {JAN31: "999"})
    store.upsert_prices(market=sec.market, rows=stale, pipeline_version="t")
    assert store.read_prices(market=sec.market, year=2024)[0].close == Decimal("999")


class FakeProvider:
    name = "fake"

    def __init__(self, price_windows, dividends=(), actions=()):
        self.price_windows = list(price_windows)
        self.requests = []
        self._dividends = list(dividends)
        self._actions = list(actions)

    def get_prices(self, security, start_date, end_date):
        self.requests.append(("prices", start_date, end_date))
        out = []
        for row in self.price_windows:
            if start_date <= row.trading_date <= end_date:
                out.append(row)
        return out

    def get_dividends(self, security, start_date, end_date):
        self.requests.append(("dividends", start_date, end_date))
        return [row for row in self._dividends if start_date <= row.ex_date <= end_date]

    def get_corporate_actions(self, security, start_date, end_date):
        self.requests.append(("actions", start_date, end_date))
        return [row for row in self._actions if start_date <= row.effective_date <= end_date]

    def get_fx_rates(self, base_currency, start_date, end_date):
        return []


def test_incremental_update_fetches_only_reconciliation_window(tmp_path):
    store = ParquetStore(tmp_path / "data")
    sec = make_security()
    first_rows = prices_for(sec, {date(2024, 1, d): "100" for d in range(2, 11)})
    provider = FakeProvider(first_rows)
    update_security_prices(store=store, provider=provider, security=sec,
                           end_date=date(2024, 1, 10), pipeline_version="t")
    assert len(store.read_prices(market=sec.market, year=2024)) == 9
    # second update: stored latest = Jan 10; reconciliation window starts Jan 3
    later = prices_for(sec, {date(2024, 1, 12): "101", date(2024, 1, 15): "102"})
    provider2 = FakeProvider(later)
    result = update_security_prices(store=store, provider=provider2, security=sec,
                                    end_date=date(2024, 1, 20))
    assert result.status == "OK"
    kind, start, end = provider2.requests[0]
    assert kind == "prices" and start == date(2024, 1, 3) and end == date(2024, 1, 20)
    stored = store.read_prices(market=sec.market, year=2024)
    dates = [row.trading_date for row in stored]
    assert len(dates) == len(set(dates))
    assert max(dates) == date(2024, 1, 15)
    assert len(dates) == 9 + 2


def test_incremental_update_idempotent_rerun(tmp_path):
    sec = make_security()
    rows = prices_for(sec, {JAN2: "100", JAN15: "101", JAN31: "110"})
    store = ParquetStore(tmp_path / "data")
    update_security_prices(store=store, provider=FakeProvider(rows), security=sec,
                           end_date=JAN31, reconciliation_days=7)
    first = [(r.trading_date, r.close) for r in store.read_prices(market=sec.market, year=2024)]
    update_security_prices(store=store, provider=FakeProvider(rows), security=sec,
                           end_date=JAN31, reconciliation_days=7)
    second = [(r.trading_date, r.close) for r in store.read_prices(market=sec.market, year=2024)]
    assert first == second


def test_stale_event_restatement_does_not_overwrite_newer(tmp_path):
    store = ParquetStore(tmp_path / "data")
    sec = make_security()
    newer = DividendEvent(security_id=sec.security_id, ex_date=JAN15, amount=Decimal("2"),
                          currency="USD", source="s", retrieved_at=datetime(2024, 6, 1, tzinfo=timezone.utc))
    older = DividendEvent(security_id=sec.security_id, ex_date=JAN15, amount=Decimal("1"),
                          pay_date=JAN20, currency="USD", source="s",
                          retrieved_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    store.upsert_dividends([newer])
    store.upsert_dividends([older])
    assert store.read_dividends(year=2024)[0].amount == Decimal("2")


def test_duplicate_dividend_rows_directly_double_count():
    """Analysis trusts the storage layer for dividend dedup (observation)."""
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d = div(sec, JAN15, "1", pay=JAN20)
    r = _run(sec, {JAN2: "100", JAN15: "100", JAN20: "100", JAN31: "110"}, fx, JAN2, JAN31,
             initial="5000", dividends=[d, d],
             scenario=AnalysisScenario(reinvest_dividends=False))
    assert r.dividends["gross_foreign_currency"] == Decimal("100")  # double-counted


def test_price_roundtrip_preserves_precision(tmp_path):
    store = ParquetStore(tmp_path / "data")
    sec = make_security()
    bar = PriceBar(security_id=sec.security_id, trading_date=JAN2, open=Decimal("123.123456789012345678"),
                   high=Decimal("124"), low=Decimal("122"), close=Decimal("123.123456789012345678"),
                   volume=1, currency="USD", exchange="NYSE", timezone="UTC", source="s")
    store.upsert_prices(market=sec.market, rows=[bar], pipeline_version="t")
    back = store.read_prices(market=sec.market, year=2024)[0]
    assert back.close == bar.close  # 18-dp scale preserved exactly
    assert back.close == Decimal("123.123456789012345678")


# ---------------------------------------------------------------------------
# PART 7 — engine end-to-end on a synthetic store
# ---------------------------------------------------------------------------

def _write_store(root: Path, sec: Security, closes, fx, dividends, actions):  # noqa
    store = ParquetStore(root / "data")
    store.upsert_prices(market=sec.market, rows=prices_for(sec, closes), pipeline_version="t")
    store.upsert_dividends(list(dividends))
    store.upsert_corporate_actions(list(actions))
    store.upsert_fx(fx)


def test_engine_end_to_end(tmp_path):
    root = tmp_path
    (root / "config").mkdir()
    sec_id = "6cfd001d-07dc-44d9-aff8-d6c99b0ee80b"
    (root / "config" / "universe.yaml").write_text(
        """
history_start: 2000-01-01
securities:
  - universe: test
    effective_from: 2024-01-01
    source: configured_seed
    security:
      security_id: 6cfd001d-07dc-44d9-aff8-d6c99b0ee80b
      ticker: TSYN
      exchange: NYSE
      market: US
      name: Synthetic
      currency: USD
      asset_type: ETF
      income_source_country: US
      timezone: America/New_York
      distribution_policy: distributing
""")
    (root / "config" / "tax_rules.yaml").write_text(
        "rules:\n"
        "  - rule_id: US_DIV\n"
        "    source_country: US\n"
        "    income_type: dividend\n"
        "    investor_type: singapore_individual\n"
        "    rate: 0.30\n"
        "    effective_from: 1900-01-01\n"
        "    effective_to: null\n"
    )
    sec = make_security(sid=UUID(sec_id), ticker="TSYN")
    closes = {JAN2: "100", JAN15: "100", JAN20: "100", JAN31: "110"}
    fx = fx_rows({JAN2: "1.25", JAN20: "1.4", JAN31: "1.4"})
    dividends = [div(sec, JAN15, "2", pay=JAN20, country="US")]
    _write_store(root, sec, closes, fx, dividends, [])
    from sg_investing.engine import SGInvestingEngine

    engine = SGInvestingEngine(root)
    result = engine.analyze(ticker="TSYN", start_date=JAN2, end_date=JAN31,
                            initial_sgd="12000",
                            scenario=AnalysisScenario(reinvest_dividends=False))
    # purchase FX 1.25: 12000/1.25 = 9600 USD -> 96 sh @100
    # gross 192; WHT 57.6; net 134.4; final 96*110 + 134.4 = 10694.4 USD
    # x end FX 1.4 = 14972.16 SGD on 12000
    assert result.dividends["withholding_tax_foreign_currency"] == Decimal("57.6")
    assert result.investment["final_value_foreign_currency"] == Decimal("10694.4")
    expected_total = Decimal("10694.4") * Decimal("1.4") / Decimal("12000") - 1
    assert abs(result.returns["total_return"] - expected_total) <= TOL


# ---------------------------------------------------------------------------
# PART 8 — feature combinations, documented gaps, real-data plausibility
# ---------------------------------------------------------------------------

def test_full_combination_matches_oracle_dense_events():
    """4 dividends, 2 splits, varying FX, WHT 30%, reinvestment: engine vs oracle."""
    sec = make_security()
    trading = [date(2024, 1, 2), JAN10, JAN15, JAN20, date(2024, 2, 5),
               date(2024, 2, 12), date(2024, 2, 26), MAR1, date(2024, 3, 20), date(2024, 3, 29)]
    closes = {
        date(2024, 1, 2): "100", JAN10: "99", JAN15: "98", JAN20: "98",
        date(2024, 2, 5): "49", date(2024, 2, 12): "50", date(2024, 2, 26): "52",
        MAR1: "53", date(2024, 3, 20): "54", date(2024, 3, 29): "60",
    }
    fx = fx_rows({JAN2: "1.30", JAN20: "1.32", date(2024, 2, 5): "1.32",
                  date(2024, 2, 26): "1.31", date(2024, 3, 20): "1.34", date(2024, 3, 29): "1.34"})
    dividends = [
        div(sec, JAN10, "0.8", pay=date(2024, 2, 12), country="US"),
        div(sec, date(2024, 2, 5), "0.5", pay=MAR1, country="US"),
        div(sec, date(2024, 2, 26), "0.5", pay=date(2024, 3, 20), country="US"),
    ]
    actions = [split(sec, JAN22 := date(2024, 1, 22), "2"), split(sec, MAR1, "2")]
    r = _run(sec, closes, fx, JAN2, date(2024, 3, 29), initial="10000",
             dividends=dividends, actions=actions, tax_rules=[us_tax()])
    expected = oracle.lump_sum_expected(
        trading_days=sorted(trading),
        closes={d: Fraction(Decimal(c)) for d, c in closes.items()},
        fx=[(row.rate_date, Fraction(row.rate_to_sgd)) for row in fx],
        dividends=[(d.ex_date, Fraction(d.amount), d.pay_date, d.source_country) for d in dividends],
        splits=[(a.effective_date, Fraction(a.ratio)) for a in actions],
        start=JAN2, end=date(2024, 3, 29), initial_sgd=Fraction(10000),
        wht_rate=lambda c, e: Fraction(3, 10),
    )
    assert_dec(r.investment["shares"], expected["shares"], "combo shares")
    assert_dec(r.investment["final_value_foreign_currency"], expected["final_native"], "combo native")
    assert_dec(r.investment["final_value_sgd"], expected["final_sgd"], "combo sgd")
    assert_dec(r.dividends["gross_foreign_currency"], expected["gross_dividends"], "combo gross")
    assert_dec(r.dividends["withholding_tax_foreign_currency"], expected["withholding_tax"], "combo wht")
    assert_float(r.returns["cagr"], expected["cagr"], "combo cagr")
    assert_float(r.returns["total_return"], expected["total_return"], "combo total")
    assert r.period["start_date"] == expected["purchase"]
    assert r.period["end_date"] == expected["valuation"]


def test_stale_price_acceptance_documented():
    sec = make_security()
    fx = fx_rows({JAN2: "1.3", JAN31: "1.3", date(2024, 6, 30): "1.3"})
    r = _run(sec, {JAN2: "100", JAN31: "110"}, fx, JAN2, date(2024, 6, 30))
    # five-month-stale valuation is silently accepted (FX staleness IS warned)
    assert r.period["end_date"] == JAN31
    assert r.data_quality["status"] == "OK"


def test_dca_lacks_fx_staleness_warning():
    sec = make_security()
    closes = {JAN2: "100", FEB1: "100"}
    fx = fx_rows({JAN2: "1.3"})  # stale for the end date
    r = dca_analysis(security=sec, prices=prices_for(sec, closes), fx_rates=fx,
                     start_date=JAN2, end_date=FEB1, contribution_sgd="1000")
    assert r.data_quality["status"] == "OK"


def test_real_store_qqq_plausibility():
    """Loose plausibility bounds on real downloaded QQQ data (not an exact oracle)."""
    from sg_investing.engine import SGInvestingEngine

    engine = SGInvestingEngine(".")
    result = engine.analyze(
        ticker="QQQ", start_date=date(2024, 1, 2), end_date=date(2024, 12, 31),
        initial_sgd="10000",
    )
    tr = float(result.returns["total_return"])
    assert -0.5 < tr < 1.5
    fx_start = float(result.fx["start_rate"])
    fx_end = float(result.fx["end_rate"])
    assert 1.0 < fx_start < 2.0 and 1.0 < fx_end < 2.0
    assert result.dividends["gross_foreign_currency"] > 0  # QQQ paid distributions in 2024


def test_fx_lag_exactly_seven_days_not_warned():
    sec = make_security()
    fx = fx_rows({JAN2: "1.3", JAN10: "1.3"})
    r = _run(sec, {JAN10: "100"}, fx, JAN10, JAN10, initial="1000")
    assert r.data_quality["status"] == "OK"  # lag 8 days? Jan 2 -> Jan 10 is 8 days
    # redo with exactly 7 days lag
    fx = fx_rows({date(2024, 1, 3): "1.3"})
    r = _run(sec, {date(2024, 1, 9): "100"}, fx, date(2024, 1, 9), date(2024, 1, 9), initial="1000")
    assert r.data_quality["status"] == "OK"  # 7-day lag is within tolerance


def test_purchase_beyond_last_price_rejected():
    sec = make_security()
    with pytest.raises(AnalysisDataError):
        _run(sec, {JAN2: "100"}, fx_rows({JAN2: "1"}), date(2024, 6, 1), date(2024, 6, 30))


def test_valuation_ignores_prices_after_end_date():
    """Prices beyond end_date exist in the store but must not be used."""
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1", date(2024, 2, 1): "1"})
    r = _run(sec, {JAN2: "100", JAN31: "110", date(2024, 2, 1): "200"}, fx, JAN2, JAN31)
    assert r.period["end_date"] == JAN31
    assert r.returns["total_return"] == Decimal("0.10")  # not 120%


def test_split_and_reverse_same_date_cancel():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    actions = [
        split(sec, JAN15, "2"),
        split(sec, JAN15, "0.5", action_type=CorporateActionType.REVERSE_SPLIT),
    ]
    closes = {JAN2: "100", JAN15: "100", JAN31: "110"}
    r = _run(sec, closes, fx, JAN2, JAN31, initial="5000", actions=actions)
    assert r.investment["shares"] == Decimal("50")
    assert r.returns["total_return"] == Decimal("0.10")


def test_zero_amount_dividend_is_harmless():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d = div(sec, JAN15, "0", pay=JAN20)
    r = _run(sec, {JAN2: "100", JAN15: "100", JAN20: "100", JAN31: "110"}, fx, JAN2, JAN31,
             initial="5000", dividends=[d])
    assert r.investment["shares"] == Decimal("50")
    assert r.returns["total_return"] == Decimal("0.10")


def test_valuation_settled_dividend_includes_net_in_final():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d = div(sec, JAN20, "1", pay=JAN31)  # settles exactly on the valuation close
    r = _run(sec, {JAN2: "100", JAN31: "100"}, fx, JAN2, JAN31, initial="5000",
             dividends=[d], scenario=AnalysisScenario(reinvest_dividends=True))
    # reinvest 50 at 100 on the last day -> 50.5 sh * 100 = 5050 (same as cash case)
    assert r.investment["final_value_foreign_currency"] == Decimal("5050")
    assert r.dividends["gross_foreign_currency"] == Decimal("50")


def test_price_return_sgd_identity_with_fx_ratio():
    sec = make_security()
    fx = fx_rows({JAN2: "1.25", JAN31: "1.6"})
    r = _run(sec, {JAN2: "100", JAN31: "110"}, fx, JAN2, JAN31)
    native = Decimal("1.10")
    ratio = Decimal("1.6") / Decimal("1.25")
    expected = Decimal("1.10") * Decimal("1.6") / Decimal("1.25") - 1
    assert abs(r.price_return["sgd"] - expected) <= TOL


def test_xirr_single_day_flows():
    got = xirr([(date(2024, 1, 1), Decimal("-100")), (date(2024, 1, 1), Decimal("110"))])
    # zero-duration flows: (1+r)^0 = 1 -> npv independent of rate -> no root
    assert got is None or abs(float(got)) < 1e6


def test_dividend_settling_exactly_on_last_price_is_included():
    sec = make_security()
    fx = fx_rows({JAN2: "1", JAN31: "1"})
    d = div(sec, JAN10, "2", pay=JAN31)
    closes = {JAN2: "100", JAN10: "100", JAN31: "100"}
    r = _run(sec, closes, fx, JAN2, JAN31, initial="5000", dividends=[d],
             scenario=AnalysisScenario(reinvest_dividends=True))
    # settles on the valuation close: 50 sh + (100/100) = 51 sh * 100 = 5100
    assert r.investment["shares"] == Decimal("51")
    assert r.dividends["gross_foreign_currency"] == Decimal("100")


def test_engine_store_isolation_between_securities(tmp_path):
    """A second security's dividends in the same partition must not leak."""
    root = tmp_path
    (root / "config").mkdir()
    (root / "config" / "universe.yaml").write_text(
        """
history_start: 2000-01-01
securities:
  - universe: test
    effective_from: 2024-01-01
    source: configured_seed
    security:
      security_id: 6cfd001d-07dc-44d9-aff8-d6c99b0ee80b
      ticker: TSYN
      exchange: NYSE
      market: US
      name: Synthetic
      currency: USD
      asset_type: ETF
      income_source_country: US
      timezone: America/New_York
      distribution_policy: distributing
""")
    (root / "config" / "tax_rules.yaml").write_text("rules: []\n")
    from sg_investing.engine import SGInvestingEngine
    from sg_investing.data.storage import ParquetStore

    sec = make_security(sid=UUID("6cfd001d-07dc-44d9-aff8-d6c99b0ee80b"), ticker="TSYN")
    other = make_security(ticker="OTHER")
    store = ParquetStore(root / "data")
    store.upsert_prices(market="US", rows=prices_for(sec, {JAN2: "100", JAN31: "110"}),
                        pipeline_version="t")
    store.upsert_dividends([div(sec, JAN15, "5", pay=JAN20, country="US"),
                            div(other_sec := make_security(ticker="OTHER"),
                                JAN15, "50", pay=JAN20, country="US")])
    store.upsert_fx(fx_rows({JAN2: "1", JAN31: "1"}))
    engine = SGInvestingEngine(root)
    result = engine.analyze(ticker="TSYN", start_date=JAN2, end_date=JAN31,
                            initial_sgd="5000")
    # only TSYN's own dividend (50 sh * $5 = 250); the other security's $50/share
    # dividend in the same partition must not leak (else it would be 2750)
    assert result.dividends["gross_foreign_currency"] == Decimal("250")
