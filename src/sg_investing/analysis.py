"""Deterministic single-security return calculations.

The engine consumes already-normalized daily data. It deliberately does not
perform network calls, which makes its financial results reproducible and easy
to test independently from providers.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from decimal import Decimal, getcontext

from sg_investing.data.validation import validate_dividends
from sg_investing.models import (
    AnalysisResult,
    AnalysisScenario,
    CorporateAction,
    DataQualityStatus,
    DistributionPolicy,
    DividendEvent,
    DividendType,
    FxRate,
    PriceBar,
    Security,
    TaxRule,
)

getcontext().prec = 28

SGD = "SGD"
_ONE = Decimal(1)
_ZERO = Decimal(0)
_DAYS_PER_YEAR = Decimal("365.2425")
_MAX_FX_STALENESS_DAYS = 7


class AnalysisDataError(ValueError):
    """Raised when a requested analysis cannot be calculated faithfully."""


def _sorted_prices(prices: Iterable[PriceBar], security: Security) -> list[PriceBar]:
    rows = sorted((row for row in prices if row.security_id == security.security_id), key=lambda row: row.trading_date)
    if not rows:
        raise AnalysisDataError(f"No price history supplied for {security.ticker}.")
    if any(row.currency != security.currency for row in rows):
        raise AnalysisDataError("Price currency does not match the security master.")
    if len({row.trading_date for row in rows}) != len(rows):
        raise AnalysisDataError("Price history contains duplicate trading dates.")
    return rows


def _resolve_price(
    prices: Sequence[PriceBar], requested: date, *, rule: str
) -> PriceBar:
    dates = [row.trading_date for row in prices]
    if rule == "next_trading_day":
        index = bisect_left(dates, requested)
        if index == len(prices):
            raise AnalysisDataError(f"No price exists on or after {requested.isoformat()}.")
        return prices[index]
    if rule == "previous_trading_day":
        index = bisect_right(dates, requested) - 1
        if index < 0:
            raise AnalysisDataError(f"No price exists on or before {requested.isoformat()}.")
        return prices[index]
    raise AnalysisDataError(f"Unsupported date rule: {rule}.")


def _rate_for_date(
    currency: str,
    requested: date,
    fx_rates: Iterable[FxRate],
    *,
    rule: str = "previous_trading_day",
) -> Decimal:
    """Return SGD per one unit of `currency` using a deterministic date rule."""

    if currency == SGD:
        return _ONE
    rows = sorted(
        (row for row in fx_rates if row.base_currency == currency), key=lambda row: row.rate_date
    )
    if not rows:
        raise AnalysisDataError(f"No {currency}/SGD FX history supplied.")
    dates = [row.rate_date for row in rows]
    if rule == "next_trading_day":
        index = bisect_left(dates, requested)
        if index == len(rows):
            raise AnalysisDataError(f"No {currency}/SGD rate exists on or after {requested.isoformat()}.")
        return rows[index].rate_to_sgd
    index = bisect_right(dates, requested) - 1
    if index < 0:
        raise AnalysisDataError(f"No {currency}/SGD rate exists on or before {requested.isoformat()}.")
    return rows[index].rate_to_sgd


def _rate_for_date_with_staleness(
    currency: str,
    requested: date,
    fx_rates: Iterable[FxRate],
    *,
    rule: str = "previous_trading_day",
) -> tuple[Decimal, int]:
    """Return the rate and its calendar-day lag from the requested date."""

    if currency == SGD:
        return _ONE, 0
    rows = sorted(
        (row for row in fx_rates if row.base_currency == currency), key=lambda row: row.rate_date
    )
    if not rows:
        raise AnalysisDataError(f"No {currency}/SGD FX history supplied.")
    dates = [row.rate_date for row in rows]
    if rule == "next_trading_day":
        index = bisect_left(dates, requested)
        if index == len(rows):
            raise AnalysisDataError(f"No {currency}/SGD rate exists on or after {requested.isoformat()}.")
    elif rule == "previous_trading_day":
        index = bisect_right(dates, requested) - 1
        if index < 0:
            raise AnalysisDataError(f"No {currency}/SGD rate exists on or before {requested.isoformat()}.")
    else:
        raise AnalysisDataError(f"Unsupported date rule: {rule}.")
    return rows[index].rate_to_sgd, abs((requested - rows[index].rate_date).days)


def _warn_if_fx_is_stale(warnings: list[str], *, currency: str, requested: date, lag_days: int) -> None:
    if lag_days > _MAX_FX_STALENESS_DAYS:
        warnings.append(
            f"{currency}/SGD FX rate for {requested.isoformat()} is {lag_days} days stale."
        )


def _tax_rate_for(
    event: DividendEvent, security: Security, tax_rules: Iterable[TaxRule]
) -> Decimal | None:
    source_country = event.source_country or security.income_source_country
    if not source_country:
        return None
    matches = [
        rule
        for rule in tax_rules
        if rule.source_country.upper() == source_country.upper()
        and rule.income_type == "dividend"
        and rule.investor_type == "singapore_individual"
        and rule.applies_on(event.ex_date)
    ]
    if not matches:
        return None
    return max(matches, key=lambda rule: rule.effective_from).rate


def _cagr(initial: Decimal, final: Decimal, start: date, end: date) -> Decimal | None:
    elapsed_days = (end - start).days
    if elapsed_days <= 0 or initial == _ZERO or final < _ZERO:
        return None
    years = Decimal(elapsed_days) / _DAYS_PER_YEAR
    # Decimal has no portable fractional exponent, so the float conversion is
    # restricted to final presentation of this derived metric.
    return Decimal(str(float(final / initial) ** (1 / float(years)) - 1))


def analyze_security(
    *,
    security: Security,
    prices: Iterable[PriceBar],
    fx_rates: Iterable[FxRate],
    start_date: date,
    end_date: date,
    initial_sgd: Decimal | int | str,
    scenario: AnalysisScenario | None = None,
    dividends: Iterable[DividendEvent] = (),
    corporate_actions: Iterable[CorporateAction] = (),
    tax_rules: Iterable[TaxRule] = (),
) -> AnalysisResult:
    """Calculate an SGD return using close prices, cash dividends, splits, and FX.

    Prices are intentionally unadjusted. Split events modify held shares at the
    effective date, preserving the correct economics without obscuring raw
    provider prices. No brokerage, FX conversion cost, slippage, or TER
    deduction is applied in V1.
    """

    scenario = scenario or AnalysisScenario()
    investment_sgd = Decimal(str(initial_sgd))
    if investment_sgd <= _ZERO:
        raise ValueError("initial_sgd must be greater than zero.")
    if end_date < start_date:
        raise ValueError("end_date must not precede start_date.")

    price_rows = _sorted_prices(prices, security)
    purchase = _resolve_price(price_rows, start_date, rule=scenario.purchase_date_rule)
    valuation = _resolve_price(price_rows, end_date, rule=scenario.valuation_date_rule)
    if valuation.trading_date < purchase.trading_date:
        raise AnalysisDataError("Resolved valuation date precedes the purchase date.")

    start_fx, start_fx_lag = _rate_for_date_with_staleness(
        security.currency, purchase.trading_date, fx_rates
    )
    end_fx, end_fx_lag = _rate_for_date_with_staleness(
        security.currency, valuation.trading_date, fx_rates
    )
    initial_investment_native = investment_sgd / start_fx
    shares = initial_investment_native / purchase.close
    cash_dividends = _ZERO
    gross_dividends = _ZERO
    withholding_tax = _ZERO
    gross_dividends_sgd_at_payment = _ZERO
    withholding_tax_sgd_at_payment = _ZERO
    net_dividends_sgd_at_payment = _ZERO
    warnings: list[str] = []
    _warn_if_fx_is_stale(
        warnings, currency=security.currency, requested=purchase.trading_date, lag_days=start_fx_lag
    )
    _warn_if_fx_is_stale(
        warnings, currency=security.currency, requested=valuation.trading_date, lag_days=end_fx_lag
    )

    supplied_dividends = [event for event in dividends if event.security_id == security.security_id]
    dividend_validation = validate_dividends(supplied_dividends)
    if not dividend_validation.is_valid:
        raise AnalysisDataError(
            "Dividend input failed validation: " + "; ".join(dividend_validation.errors)
        )
    dividend_rows = sorted(
        (
            event
            for event in supplied_dividends
            if purchase.trading_date < event.ex_date <= valuation.trading_date
        ),
        key=lambda event: (event.ex_date, event.pay_date or date.max),
    )
    action_rows = sorted(
        (
            action
            for action in corporate_actions
            if action.security_id == security.security_id
            and purchase.trading_date < action.effective_date <= valuation.trading_date
        ),
        key=lambda action: action.effective_date,
    )

    if security.distribution_policy in {
        DistributionPolicy.ACCUMULATING,
        DistributionPolicy.NON_DISTRIBUTING,
    } and dividend_rows:
        policy_label = security.distribution_policy.value
        warnings.append(f"Dividend events ignored because this security is marked {policy_label}.")
        dividend_rows = []

    for event in dividend_rows:
        if event.dividend_type.value in {"unknown", "ordinary"}:
            warnings.append(
                f"Dividend type for {event.ex_date.isoformat()} is not fully classified; "
                "it is modeled as a cash distribution."
            )
        elif event.dividend_type.value == "return_of_capital":
            warnings.append(
                f"Return of capital on {event.ex_date.isoformat()} is modeled as a cash distribution; "
                "tax treatment is not inferred."
            )

    # Action, dividend-entitlement, and cash-availability processing is
    # chronological. A split takes effect before a same-day dividend per-share
    # amount. Reinvestment occurs only on the dividend's pay date, so it cannot
    # incorrectly earn another dividend before the cash was available.
    actions_by_date: dict[date, list[CorporateAction]] = {}
    for action in action_rows:
        actions_by_date.setdefault(action.effective_date, []).append(action)
    dividends_by_date: dict[date, list[DividendEvent]] = {}
    for event in dividend_rows:
        dividends_by_date.setdefault(event.ex_date, []).append(event)

    reinvestments_by_date: dict[date, list[Decimal]] = {}
    cash_by_date: dict[date, list[Decimal]] = {}

    timeline = sorted(set(actions_by_date) | set(dividends_by_date))
    cursor = 0
    while cursor < len(timeline):
        event_date = timeline[cursor]
        for action in actions_by_date.get(event_date, []):
            shares *= action.ratio

        if scenario.dividends_enabled:
            for event in dividends_by_date.get(event_date, []):
                gross_event_currency = shares * event.amount
                rate = _ZERO
                if event.dividend_type == DividendType.RETURN_OF_CAPITAL:
                    # Return of capital is a cash flow but is not treated as
                    # a dividend withholding event without an explicit tax
                    # rule for that product.
                    rate = _ZERO
                elif scenario.withholding_tax_enabled:
                    matched_rate = _tax_rate_for(event, security, tax_rules)
                    if matched_rate is None:
                        warnings.append(
                            f"No dividend tax rule for {event.source_country or security.income_source_country or 'unknown'} "
                            f"on {event.ex_date.isoformat()}; assumed 0%."
                        )
                    else:
                        rate = matched_rate
                tax_event_currency = gross_event_currency * rate
                net_event_currency = gross_event_currency - tax_event_currency
                availability_date = event.pay_date
                if availability_date is None:
                    availability_date = event.ex_date + timedelta(days=30)
                    warnings.append(
                        f"Approximated dividend pay date for {event.ex_date.isoformat()} as "
                        f"{availability_date.isoformat()}."
                    )
                elif availability_date < event.ex_date:
                    raise AnalysisDataError(
                        f"Dividend pay date precedes ex-date for {event.ex_date.isoformat()}."
                    )
                try:
                    availability_price = _resolve_price(
                        price_rows, availability_date, rule="next_trading_day"
                    )
                except AnalysisDataError:
                    warnings.append(
                        f"Could not resolve a trading day for dividend dated {event.ex_date.isoformat()}; "
                        "it is excluded from end-date value."
                    )
                    continue
                if availability_price.trading_date > valuation.trading_date:
                    warnings.append(
                        f"Dividend dated {event.ex_date.isoformat()} becomes available after valuation and "
                        "is excluded from end-date value."
                    )
                    continue
                security_payment_fx, security_fx_lag = _rate_for_date_with_staleness(
                    security.currency, availability_price.trading_date, fx_rates
                )
                event_payment_fx, event_fx_lag = _rate_for_date_with_staleness(
                    event.currency, availability_price.trading_date, fx_rates
                )
                _warn_if_fx_is_stale(
                    warnings,
                    currency=security.currency,
                    requested=availability_price.trading_date,
                    lag_days=security_fx_lag,
                )
                if event.currency != security.currency:
                    _warn_if_fx_is_stale(
                        warnings,
                        currency=event.currency,
                        requested=availability_price.trading_date,
                        lag_days=event_fx_lag,
                    )
                # Dividend cash is held in the security's native currency by
                # the engine.  Convert through SGD using the actual dividend
                # currency at payment, rather than assuming it matches the
                # security currency.
                event_to_security_fx = event_payment_fx / security_payment_fx
                gross = gross_event_currency * event_to_security_fx
                tax = tax_event_currency * event_to_security_fx
                net = net_event_currency * event_to_security_fx
                gross_dividends += gross
                withholding_tax += tax
                gross_dividends_sgd_at_payment += gross_event_currency * event_payment_fx
                withholding_tax_sgd_at_payment += tax_event_currency * event_payment_fx
                net_dividends_sgd_at_payment += net_event_currency * event_payment_fx
                target = reinvestments_by_date if scenario.reinvest_dividends else cash_by_date
                target.setdefault(availability_price.trading_date, []).append(net)
                if availability_price.trading_date > event_date and availability_price.trading_date not in timeline:
                    insort(timeline, availability_price.trading_date)

        # Pay-date transactions happen at the close and therefore after any
        # entitlement that occurs on that date.
        if cash_by_date.get(event_date):
            cash_dividends += sum(cash_by_date[event_date], start=_ZERO)
        if reinvestments_by_date.get(event_date):
            reinvestment_price = _resolve_price(price_rows, event_date, rule="next_trading_day")
            shares += sum(reinvestments_by_date[event_date], start=_ZERO) / reinvestment_price.close
        cursor += 1

    final_security_value = shares * valuation.close
    final_value_native = final_security_value + cash_dividends
    final_value_sgd = final_value_native * end_fx
    start_native_value = purchase.close
    end_native_value = valuation.close
    price_return_native = end_native_value / start_native_value - _ONE
    price_return_sgd = (end_native_value * end_fx) / (start_native_value * start_fx) - _ONE
    net_dividends = gross_dividends - withholding_tax
    quality = DataQualityStatus.WARNING if warnings else DataQualityStatus.OK

    return AnalysisResult(
        security=security,
        period={"start_date": purchase.trading_date, "end_date": valuation.trading_date},
        initial_investment_sgd=investment_sgd,
        initial_investment_foreign_currency=initial_investment_native,
        price_return={"foreign_currency": price_return_native, "sgd": price_return_sgd},
        dividends={
            "gross_foreign_currency": gross_dividends,
            "withholding_tax_foreign_currency": withholding_tax,
            "net_foreign_currency": net_dividends,
            "cash_foreign_currency": cash_dividends,
            "gross_sgd_at_payment": gross_dividends_sgd_at_payment,
            "withholding_tax_sgd_at_payment": withholding_tax_sgd_at_payment,
            "net_sgd_at_payment": net_dividends_sgd_at_payment,
        },
        investment={
            "shares": shares,
            "final_security_value_foreign_currency": final_security_value,
            "final_value_foreign_currency": final_value_native,
            "final_value_sgd": final_value_sgd,
        },
        returns={
            "total_return": final_value_sgd / investment_sgd - _ONE,
            "cagr": _cagr(investment_sgd, final_value_sgd, purchase.trading_date, valuation.trading_date),
            "total_return_foreign_currency": final_value_native / initial_investment_native - _ONE,
            "cagr_foreign_currency": _cagr(
                initial_investment_native, final_value_native, purchase.trading_date, valuation.trading_date
            ),
        },
        fx={"start_rate": start_fx, "end_rate": end_fx},
        methodology={
            "price": "daily_close",
            "price_return": "raw_unadjusted_close_to_close_not_split_adjusted",
            "purchase_date_rule": scenario.purchase_date_rule,
            "valuation_date_rule": scenario.valuation_date_rule,
            "dividend_reinvestment": "pay_date_close_with_30_day_ex_date_fallback",
            "fractional_shares": True,
            "withholding_tax": scenario.withholding_tax_enabled,
            "dividend_native_currency": security.currency,
            "dividend_sgd_translation": "payment_date_fx_rate_for_actual_dividend_currency",
            "dividend_type_handling": (
                "regular/special/unknown treated as cash; return_of_capital treated as cash "
                "without assumed withholding"
            ),
            "ter_deducted": False,
            "methodology_version": scenario.methodology_version,
        },
        data_quality={"status": quality, "warnings": warnings},
    )
