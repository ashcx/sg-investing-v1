"""Independent expected-value oracles for the falsification audit.

This module implements the documented financial specification (README
"Financial methodology") with exact rational arithmetic.  It deliberately
imports NOTHING from sg_investing.analysis or sg_investing.calculations, so
expected values cannot be correlated with implementation bugs.  The
sg_investing.models classes are used only to *declare* input data, never to
compute expected results.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, timedelta
from fractions import Fraction

DAYS_PER_YEAR = 365.2425


# ---------------------------------------------------------------------------
# Generic helpers (all independent implementations)
# ---------------------------------------------------------------------------

def next_trading_day(dates: Sequence[date], requested: date) -> date:
    for candidate in dates:
        if candidate >= requested:
            return candidate
    raise ValueError(f"no trading day on/after {requested}")


def previous_trading_day(dates: Sequence[date], requested: date) -> date:
    result = None
    for candidate in dates:
        if candidate <= requested:
            result = candidate
        else:
            break
    if result is None:
        raise ValueError(f"no trading day on/before {requested}")
    return result


def fx_at(fx_rows: Sequence[tuple[date, Fraction]], requested: date) -> Fraction:
    """SGD per one unit of the currency, previous-observation rule."""
    eligible = [rate for rate_date, rate in fx_rows if rate_date <= requested]
    if not eligible:
        raise ValueError(f"no FX on/before {requested}")
    return eligible[-1]


class _Engine:
    """Shared chronological engine for lump-sum and DCA simulations.

    Implements the documented conventions:
    * splits multiply shares by ratio on effective dates inside the window
    * dividend entitled when window_start < ex_date <= valuation_date
    * entitlement cash = shares_at_ex_date * per_share_amount (fixed at ex-date)
    * cash available on pay_date (or ex_date + 30 days) at the next trading day
    * dividends available after valuation contribute nothing to end value
    * withholding tax = gross * rate(country, ex_date); investor keeps net
    * settlement (reinvest or cash) happens at the availability close, AFTER
      same-date entitlements (shares bought at the close of the ex-date do not
      earn that date's dividend)
    * contributions convert at the contribution-date FX and buy at that close
    """

    def __init__(
        self,
        *,
        trading_days: Sequence[date],
        closes: dict[date, Fraction],
        fx: Sequence[tuple[date, Fraction]],
        window_start: date,
        valuation: date,
        wht_rate: Callable[[str | None, date], Fraction],
        dividends_enabled: bool = True,
        reinvest: bool = True,
    ) -> None:
        self.days = list(trading_days)
        self.closes = closes
        self.fx = fx
        self.window_start = window_start
        self.valuation = valuation
        self.wht_rate = wht_rate
        self.dividends_enabled = dividends_enabled
        self.reinvest = reinvest
        self.shares = Fraction(0)
        self.cash = Fraction(0)
        self.gross = Fraction(0)
        self.tax = Fraction(0)
        self.dropped_after_valuation = False
        self.approximated_pay_date = False
        self.pending: dict[date, list[Fraction]] = {}  # settle date -> nets
        self.ex_events: dict[date, list[tuple[Fraction, str | None]]] = {}
        self.split_events: dict[date, Fraction] = {}
        self.contributions: dict[date, Fraction] = {}
        self.settle_of: dict[date, date] = {}  # ex-date -> settle date

    def add_dividends(self, dividends: Sequence[tuple[date, Fraction, date | None, str | None]]) -> None:
        for ex, amount, pay, country in dividends:
            if not (self.window_start < ex <= self.valuation):
                continue
            availability = pay
            if availability is None:
                availability = ex + timedelta(days=30)
                self.approximated_pay_date = True
            try:
                settle = next_trading_day(self.days, availability)
            except ValueError:
                settle = None
            if settle is None or settle > self.valuation:
                self.dropped_after_valuation = True
                continue
            self.ex_events.setdefault(ex, []).append((amount, country))
            self.pending.setdefault(settle, [])  # settlement slot at the pay close
            self.settle_of[ex] = settle

    def add_splits(self, splits: Sequence[tuple[date, Fraction]]) -> None:
        for effective, ratio in splits:
            if self.window_start < effective <= self.valuation:
                self.split_events[effective] = self.split_events.get(effective, Fraction(1)) * Fraction(ratio)

    def add_contributions(self, dates: Sequence[date], amount_sgd: Fraction) -> None:
        for day in dates:
            self.contributions[day] = amount_sgd

    def run(self) -> None:
        events = sorted(
            set(self.split_events) | set(self.ex_events) | set(self.pending) | set(self.contributions)
        )
        for event_date in events:
            # 1. corporate actions first (split takes effect at the open of its date)
            ratio = self.split_events.get(event_date)
            if ratio is not None:
                self.shares *= ratio
            # 2. same-date dividend entitlements: shares held at the ex-date,
            #    before any same-date settlement (shares bought at the close of
            #    the ex-date do not earn that date's dividend)
            if self.dividends_enabled:
                for amount, country in self.ex_events.get(event_date, ()):
                    gross = self.shares * amount
                    rate = self.wht_rate(country, event_date)
                    tax = gross * rate
                    net = gross - tax
                    self.gross += gross
                    self.tax += tax
                    self.pending[self.settle_of[event_date]].append(net)
            # 3. settlements at this date's close
            if self.reinvest:
                if event_date in self.pending and self.pending[event_date]:
                    self.shares += sum(self.pending[event_date], Fraction(0)) / self.closes[event_date]
            else:
                self.cash += sum(self.pending.get(event_date, ()), Fraction(0))
            # 4. contributions at this date's close
            if event_date in self.contributions:
                amount = self.contributions[event_date]
                rate = fx_at(self.fx, event_date)
                self.shares += (amount / rate) / self.closes[event_date]

    def finalise(self) -> tuple[Fraction, Fraction]:
        return self.shares, self.cash


# ---------------------------------------------------------------------------
# Independent lump-sum simulator (exact Fraction arithmetic)
# ---------------------------------------------------------------------------

def lump_sum_expected(
    *,
    trading_days: Sequence[date],
    closes: dict[date, Fraction],
    fx: Sequence[tuple[date, Fraction]],
    dividends: Sequence[tuple[date, Fraction, date | None, str | None]],  # ex, amount, pay, country
    splits: Sequence[tuple[date, Fraction]],  # effective date, ratio
    start: date,
    end: date,
    initial_sgd: Fraction,
    wht_rate: Callable[[str | None, date], Fraction] = lambda country, ex: Fraction(0),
    dividends_enabled: bool = True,
    reinvest: bool = True,
) -> dict[str, Fraction | None]:
    """Expected values per the documented V1 methodology (independent math)."""
    purchase = next_trading_day(trading_days, start)
    valuation = previous_trading_day(trading_days, end)
    if valuation < purchase:
        raise ValueError("valuation precedes purchase")
    start_rate = fx_at(fx, purchase)
    end_rate = fx_at(fx, valuation)
    initial_native = initial_sgd / start_rate

    engine = _Engine(
        trading_days=trading_days,
        closes=closes,
        fx=fx,
        window_start=purchase,
        valuation=valuation,
        wht_rate=wht_rate,
        dividends_enabled=dividends_enabled,
        reinvest=reinvest,
    )
    engine.shares = initial_native / closes[purchase]
    engine.add_dividends(dividends)
    engine.add_splits(splits)
    engine.run()
    shares, cash_total = engine.shares, engine.cash

    final_native = shares * closes[valuation] + cash_total
    final_sgd = final_native * end_rate
    price_return_native = Fraction(closes[valuation], closes[purchase]) - 1
    price_return_sgd = (closes[valuation] * end_rate) / (closes[purchase] * start_rate) - 1
    total_return = final_sgd / initial_sgd - 1
    total_return_native = final_native / initial_native - 1
    return {
        "purchase": purchase,
        "valuation": valuation,
        "shares": shares,
        "initial_native": initial_native,
        "final_native": final_native,
        "final_sgd": final_sgd,
        "gross_dividends": engine.gross,
        "withholding_tax": engine.tax,
        "net_dividends": engine.gross - engine.tax,
        "cash_dividends": cash_total,
        "price_return_native": price_return_native,
        "price_return_sgd": price_return_sgd,
        "total_return": total_return,
        "total_return_native": total_return_native,
        "cagr": _cagr(initial_sgd, final_sgd, purchase, valuation),
        "cagr_native": _cagr(initial_native, final_native, purchase, valuation),
        "start_fx": start_rate,
        "end_fx": end_rate,
        "dropped_after_valuation": engine.dropped_after_valuation,
        "approximated_pay_date": engine.approximated_pay_date,
    }


def _cagr(initial: Fraction, final: Fraction, start: date, end: date) -> float | None:
    days = (end - start).days
    if days <= 0 or initial == 0:
        return None
    years = days / DAYS_PER_YEAR
    return (float(final / initial)) ** (1.0 / years) - 1.0


# ---------------------------------------------------------------------------
# Independent XIRR (own bracketing + bisection, float domain)
# ---------------------------------------------------------------------------

def xirr_expected(flows: Sequence[tuple[date, float]]) -> float | None:
    if len(flows) < 2:
        return None
    flows = sorted(flows)
    origin = flows[0][0]
    if not any(a < 0 for _, a in flows) or not any(a > 0 for _, a in flows):
        return None

    def npv(rate: float) -> float:
        return sum(
            amount / (1.0 + rate) ** ((when - origin).days / DAYS_PER_YEAR)
            for when, amount in flows
        )

    low, high = -0.999999, 1.0
    if npv(low) * npv(high) > 0:
        high = 1e9
    if npv(low) * npv(high) > 0:
        return None
    for _ in range(500):
        mid = (low + high) / 2
        value = npv(mid)
        if abs(value) < 1e-12:
            return mid
        if npv(low) * value <= 0:
            high = mid
        else:
            low = mid
    return (low + high) / 2


def npv_expected(flows: Sequence[tuple[date, Fraction]], rate: float) -> float:
    flows = sorted(flows)
    origin = flows[0][0]
    return sum(
        float(amount) / (1.0 + rate) ** ((when - origin).days / DAYS_PER_YEAR)
        for when, amount in flows
    )


# ---------------------------------------------------------------------------
# Independent DCA simulator (exact Fraction arithmetic)
# ---------------------------------------------------------------------------

def dca_expected(
    *,
    trading_days: Sequence[date],
    closes: dict[date, Fraction],
    fx: Sequence[tuple[date, Fraction]],
    dividends: Sequence[tuple[date, Fraction, date | None, str | None]],
    splits: Sequence[tuple[date, Fraction]],
    start: date,
    end: date,
    contribution_sgd: Fraction,
    frequency: str = "monthly",  # monthly | quarterly | yearly
    wht_rate: Callable[[str | None, date], Fraction] = lambda country, ex: Fraction(0),
    dividends_enabled: bool = True,
    reinvest: bool = True,
) -> dict[str, Fraction | None]:
    def period_key(value: date) -> tuple[int, int]:
        if frequency == "monthly":
            return (value.year, value.month)
        if frequency == "quarterly":
            return (value.year, (value.month - 1) // 3 + 1)
        return (value.year, 1)

    selected: dict[tuple[int, int], date] = {}
    for day in sorted(trading_days):
        if start <= day <= end:
            selected.setdefault(period_key(day), day)
    contributions = list(selected.values())
    if not contributions:
        raise ValueError("no contribution dates")
    valuation = previous_trading_day(trading_days, end)

    engine = _Engine(
        trading_days=trading_days,
        closes=closes,
        fx=fx,
        window_start=contributions[0],
        valuation=valuation,
        wht_rate=wht_rate,
        dividends_enabled=dividends_enabled,
        reinvest=reinvest,
    )
    engine.add_dividends(dividends)
    engine.add_splits(splits)
    engine.add_contributions(contributions, contribution_sgd)
    engine.run()

    contributed_sgd = contribution_sgd * len(contributions)
    contributed_native = sum(
        contribution_sgd / fx_at(fx, day) for day in contributions
    )
    end_rate = fx_at(fx, valuation)
    final_native = engine.shares * closes[valuation] + engine.cash
    final_sgd = final_native * end_rate
    flows_sgd = [(day, -float(contribution_sgd)) for day in contributions] + [
        (valuation, float(final_sgd))
    ]
    flows_native = [
        (day, -float(contribution_sgd / fx_at(fx, day))) for day in contributions
    ] + [(valuation, float(final_native))]
    return {
        "contribution_dates": contributions,
        "total_contributed_sgd": contributed_sgd,
        "total_contributed_native": contributed_native,
        "shares": engine.shares,
        "final_native": final_native,
        "final_sgd": final_sgd,
        "gain_sgd": final_sgd - contributed_sgd,
        "gain_native": final_native - contributed_native,
        "gross_dividends": engine.gross,
        "withholding_tax": engine.tax,
        "cash_dividends": engine.cash,
        "xirr_sgd": xirr_expected(flows_sgd),
        "xirr_native": xirr_expected(flows_native),
        "valuation": valuation,
        "dropped_after_valuation": engine.dropped_after_valuation,
    }


# ---------------------------------------------------------------------------
# Independent weighted-average portfolio simulator
# ---------------------------------------------------------------------------

_CURRENCY_OF: dict[str, str] = {}


def register_currency(key: str, currency: str) -> None:
    _CURRENCY_OF[key] = currency


def portfolio_expected(
    *,
    transactions: Sequence[dict],
    as_of: date,
    closes: dict[str, Fraction],  # security key -> last close on/before as_of
    fx: dict[str, Fraction],  # currency -> rate at as_of
) -> dict[str, object]:
    quantity: dict[str, Fraction] = {}
    basis: dict[str, Fraction] = {}
    realized: dict[str, Fraction] = {}
    cash: dict[str, Fraction] = {}

    for tx in sorted(transactions, key=lambda item: item["date"]):
        if tx["date"] > as_of:
            continue
        key = tx.get("security")
        kind = tx["type"]
        if kind == "BUY":
            quantity[key] = quantity.get(key, Fraction(0)) + tx["qty"]
            basis[key] = basis.get(key, Fraction(0)) + tx["cash"] + tx["fees"]
            cash[tx["currency"]] = cash.get(tx["currency"], Fraction(0)) - tx["cash"] - tx["fees"]
        elif kind == "SELL":
            average = basis[key] / quantity[key]
            disposed = average * tx["qty"]
            proceeds = tx["cash"] - tx["fees"]
            realized[key] = realized.get(key, Fraction(0)) + proceeds - disposed
            quantity[key] -= tx["qty"]
            basis[key] -= disposed
            cash[tx["currency"]] = cash.get(tx["currency"], Fraction(0)) + proceeds
        elif kind == "DIVIDEND":
            cash[tx["currency"]] = cash.get(tx["currency"], Fraction(0)) + tx["cash"] - tx["fees"]
        elif kind == "DEPOSIT":
            cash[tx["currency"]] = cash.get(tx["currency"], Fraction(0)) + tx["cash"]
        elif kind == "WITHDRAWAL":
            cash[tx["currency"]] = cash.get(tx["currency"], Fraction(0)) - tx["cash"]

    holdings = {}
    total_sgd = Fraction(0)
    for key, qty in quantity.items():
        if qty == 0:
            continue
        market = qty * closes[key]
        market_sgd = market * fx[_CURRENCY_OF[key]]
        total_sgd += market_sgd
        holdings[key] = {
            "quantity": qty,
            "average_cost": basis[key] / qty,
            "cost_basis": basis[key],
            "market_value": market,
            "market_value_sgd": market_sgd,
            "unrealized": market - basis[key],
            "realized": realized.get(key, Fraction(0)),
        }
    for currency, amount in cash.items():
        total_sgd += amount * fx[currency]
    realized_by_currency: dict[str, Fraction] = {}
    for key, amount in realized.items():
        currency = _CURRENCY_OF[key]
        realized_by_currency[currency] = realized_by_currency.get(currency, Fraction(0)) + amount
    return {
        "holdings": holdings,
        "cash": cash,
        "realized": realized_by_currency,
        "total_sgd": total_sgd,
    }


# ---------------------------------------------------------------------------
# XIRR known closed forms
# ---------------------------------------------------------------------------

def xirr_single_period(start: date, end: date, multiple: float) -> float:
    """Exact XIRR for one outflow at start and multiple*inflow at end."""
    days = (end - start).days
    return multiple ** (DAYS_PER_YEAR / days) - 1.0
