"""Recurring-investment analysis with money-weighted (XIRR) returns."""

from __future__ import annotations

from bisect import insort
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from math import isfinite

from pydantic import BaseModel, ConfigDict

from sg_investing.analysis import (
    _ONE,
    _ZERO,
    AnalysisDataError,
    _rate_for_date,
    _resolve_price,
    _sorted_prices,
    _tax_rate_for,
)
from sg_investing.data.validation import validate_dividends
from sg_investing.models import (
    AnalysisScenario,
    CorporateAction,
    DataQualityStatus,
    DistributionPolicy,
    DividendEvent,
    DividendType,
    FxRate,
    Security,
    TaxRule,
)


class DcaFrequency(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class DcaResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    security: Security
    contribution_dates: list[date]
    total_contributed_sgd: Decimal
    total_contributed_foreign_currency: Decimal
    final_value_sgd: Decimal
    final_value_foreign_currency: Decimal
    gain_loss_sgd: Decimal
    gain_loss_foreign_currency: Decimal
    xirr: Decimal | None
    xirr_foreign_currency: Decimal | None
    shares: Decimal
    methodology: dict[str, str | bool]
    data_quality: dict[str, DataQualityStatus | list[str]]


def _period_key(value: date, frequency: DcaFrequency) -> tuple[int, int]:
    if frequency == DcaFrequency.MONTHLY:
        return (value.year, value.month)
    if frequency == DcaFrequency.QUARTERLY:
        return (value.year, (value.month - 1) // 3 + 1)
    return (value.year, 1)


def _contribution_dates(prices, start_date: date, end_date: date, frequency: DcaFrequency) -> list[date]:
    selected: dict[tuple[int, int], date] = {}
    for row in prices:
        if start_date <= row.trading_date <= end_date:
            selected.setdefault(_period_key(row.trading_date, frequency), row.trading_date)
    return list(selected.values())


def xirr(cash_flows: Iterable[tuple[date, Decimal]]) -> Decimal | None:
    """Solve annual money-weighted return with a bracketed bisection method."""

    flows = sorted(cash_flows, key=lambda flow: flow[0])
    if len(flows) < 2 or not any(amount < _ZERO for _, amount in flows) or not any(
        amount > _ZERO for _, amount in flows
    ):
        return None
    origin = flows[0][0]

    def npv(rate: float) -> float:
        return sum(float(amount) / (1.0 + rate) ** ((flow_date - origin).days / 365.2425) for flow_date, amount in flows)

    low, high = -0.9999, 10.0
    low_value, high_value = npv(low), npv(high)
    while low_value * high_value > 0 and high < 1_000_000:
        high *= 2
        high_value = npv(high)
    if not isfinite(low_value) or not isfinite(high_value) or low_value * high_value > 0:
        return None
    for _ in range(200):
        midpoint = (low + high) / 2
        value = npv(midpoint)
        if abs(value) < 1e-10:
            return Decimal(str(midpoint))
        if low_value * value <= 0:
            high, high_value = midpoint, value
        else:
            low, low_value = midpoint, value
    return Decimal(str((low + high) / 2))


def dca_analysis(
    *,
    security: Security,
    prices,
    fx_rates: Iterable[FxRate],
    start_date: date,
    end_date: date,
    contribution_sgd: Decimal | int | str,
    frequency: DcaFrequency = DcaFrequency.MONTHLY,
    scenario: AnalysisScenario | None = None,
    dividends: Iterable[DividendEvent] = (),
    corporate_actions: Iterable[CorporateAction] = (),
    tax_rules: Iterable[TaxRule] = (),
) -> DcaResult:
    """Invest a fixed SGD amount on each period's first available trading day."""

    scenario = scenario or AnalysisScenario()
    contribution = Decimal(str(contribution_sgd))
    if contribution <= _ZERO:
        raise ValueError("contribution_sgd must be greater than zero.")
    if end_date < start_date:
        raise ValueError("end_date must not precede start_date.")
    price_rows = _sorted_prices(prices, security)
    purchase_dates = _contribution_dates(price_rows, start_date, end_date, frequency)
    if not purchase_dates:
        raise AnalysisDataError("No trading dates exist in the requested DCA period.")
    valuation = next((row for row in reversed(price_rows) if row.trading_date <= end_date), None)
    if valuation is None:
        raise AnalysisDataError("No valuation price exists on or before the requested end date.")

    contributions_by_date = {item: contribution for item in purchase_dates}
    warnings: list[str] = []
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
            if purchase_dates[0] < event.ex_date <= valuation.trading_date
        ),
        key=lambda event: event.ex_date,
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
    actions_by_date: dict[date, list[CorporateAction]] = {}
    for action in corporate_actions:
        if action.security_id == security.security_id and purchase_dates[0] < action.effective_date <= valuation.trading_date:
            actions_by_date.setdefault(action.effective_date, []).append(action)
    dividends_by_date: dict[date, list[DividendEvent]] = {}
    for event in dividend_rows:
        dividends_by_date.setdefault(event.ex_date, []).append(event)

    timeline = sorted(set(contributions_by_date) | set(actions_by_date) | set(dividends_by_date))
    cash_by_date: dict[date, list[Decimal]] = {}
    reinvestments_by_date: dict[date, list[Decimal]] = {}
    shares = _ZERO
    cash_dividends = _ZERO
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
                    rate = _ZERO
                elif scenario.withholding_tax_enabled:
                    rate = _tax_rate_for(event, security, tax_rules) or _ZERO
                    if rate == _ZERO and _tax_rate_for(event, security, tax_rules) is None:
                        warnings.append(f"No dividend tax rule for {event.ex_date.isoformat()}; assumed 0%.")
                net_event_currency = gross_event_currency * (_ONE - rate)
                availability = event.pay_date or event.ex_date + timedelta(days=30)
                if event.pay_date is None:
                    warnings.append(f"Approximated dividend pay date for {event.ex_date.isoformat()} as {availability.isoformat()}.")
                elif availability < event.ex_date:
                    raise AnalysisDataError(
                        f"Dividend pay date precedes ex-date for {event.ex_date.isoformat()}."
                    )
                try:
                    pay_price = _resolve_price(price_rows, availability, rule="next_trading_day")
                except AnalysisDataError:
                    warnings.append(
                        f"Could not resolve a trading day for dividend dated {event.ex_date.isoformat()}; "
                        "it is excluded from end-date value."
                    )
                    continue
                if pay_price.trading_date > valuation.trading_date:
                    warnings.append(f"Dividend dated {event.ex_date.isoformat()} becomes available after valuation.")
                    continue
                event_fx = _rate_for_date(event.currency, pay_price.trading_date, fx_rates)
                security_fx = _rate_for_date(security.currency, pay_price.trading_date, fx_rates)
                net = net_event_currency * event_fx / security_fx
                target = reinvestments_by_date if scenario.reinvest_dividends else cash_by_date
                target.setdefault(pay_price.trading_date, []).append(net)
                if pay_price.trading_date > event_date and pay_price.trading_date not in timeline:
                    insort(timeline, pay_price.trading_date)
        if cash_by_date.get(event_date):
            cash_dividends += sum(cash_by_date[event_date], start=_ZERO)
        if reinvestments_by_date.get(event_date):
            pay_price = next(row for row in price_rows if row.trading_date >= event_date)
            shares += sum(reinvestments_by_date[event_date], start=_ZERO) / pay_price.close
        if event_date in contributions_by_date:
            buy_price = next(row for row in price_rows if row.trading_date == event_date)
            fx_rate = _rate_for_date(security.currency, event_date, fx_rates)
            shares += contributions_by_date[event_date] / fx_rate / buy_price.close
        cursor += 1

    end_fx = _rate_for_date(security.currency, valuation.trading_date, fx_rates)
    final_value_foreign_currency = shares * valuation.close + cash_dividends
    final_value = final_value_foreign_currency * end_fx
    total = contribution * len(purchase_dates)
    contributions_foreign_currency = [
        contribution / _rate_for_date(security.currency, purchase_date, fx_rates)
        for purchase_date in purchase_dates
    ]
    total_foreign_currency = sum(contributions_foreign_currency, start=_ZERO)
    return DcaResult(
        security=security,
        contribution_dates=purchase_dates,
        total_contributed_sgd=total,
        total_contributed_foreign_currency=total_foreign_currency,
        final_value_sgd=final_value,
        final_value_foreign_currency=final_value_foreign_currency,
        gain_loss_sgd=final_value - total,
        gain_loss_foreign_currency=final_value_foreign_currency - total_foreign_currency,
        xirr=xirr([(day, -contribution) for day in purchase_dates] + [(valuation.trading_date, final_value)]),
        xirr_foreign_currency=xirr(
            list(zip(purchase_dates, (-amount for amount in contributions_foreign_currency), strict=True))
            + [(valuation.trading_date, final_value_foreign_currency)]
        ),
        shares=shares,
        methodology={
            "contribution_timing": "first_available_trading_day_of_period",
            "cost_basis": "weighted_average_not_applicable_to_dca_return",
            "dividend_reinvestment": scenario.reinvest_dividends,
            "dividend_type_handling": (
                "regular/special/unknown treated as cash; return_of_capital treated as cash "
                "without assumed withholding"
            ),
            "ter_deducted": False,
        },
        data_quality={"status": DataQualityStatus.WARNING if warnings else DataQualityStatus.OK, "warnings": warnings},
    )
