"""Generate golden parity fixtures for the portable browser engine (Sprint 3, S3.1).

Every fixture runs one scenario through the authoritative PYTHON engine and
records the resulting ``model_dump(mode="json")`` envelope as the golden
reference, alongside the equivalent slim input rows consumed by the JS engine
under ``frontend/engine/parity/parity.mjs``.

Fixture categories:

- ``usd-etf-real``      real catalog securities (QQQ 2024, SMH 2023 split) via
                        the committed local Parquet store — dividends, FX,
                        withholding, reinvestment, estimated pay dates and an
                        unresolvable pay date.
- ``usd-split-synthetic`` hand-built USD case with a 2:1 split between the
                        dividend ex-date and pay date.
- ``sgd-security``      hand-built SGD security; FX history is empty because
                        SGD needs no conversion.
- ``dividend-edge``     pay-before-ex rejection, estimated pay date,
                        accumulating fund, zero-dividend security.
- ``fx``                normal conversion, stale-rate warning, missing history.
- ``incomplete-data``   dividend available only after the valuation date.
- ``dca``               monthly (real data), quarterly, yearly, and a
                        no-reinvestment monthly case; XIRR fields included.
                        Sprint 4 adds: SGD-security monthly (no FX),
                        accumulating-fund monthly, zero-dividend monthly,
                        invalid date range / contribution amount error
                        envelopes, and real-data QQQ 2024 quarterly/yearly
                        goldens reused by
                        ``frontend/engine/dca-packs-integration.mjs``.
- ``portfolio``         mixed currencies, partial sells, dividends, cash-only
                        rows, zero holdings, missing as-of price.

No live network calls are made; only the committed local Parquet store is read.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel

from sg_investing import SGInvestingEngine
from sg_investing.analysis import AnalysisDataError, analyze_security
from sg_investing.calculations.dca import DcaFrequency, dca_analysis
from sg_investing.calculations.portfolio import analyze_portfolio
from sg_investing.models import (
    AnalysisScenario,
    CorporateAction,
    CorporateActionType,
    DividendEvent,
    FxRate,
    PortfolioTransaction,
    PriceBar,
    Security,
    TaxRule,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "frontend" / "engine" / "parity" / "fixtures"

US_TAX_RULE = TaxRule(
    rule_id="US_DIVIDEND_NONRESIDENT",
    source_country="US",
    income_type="dividend",
    investor_type="singapore_individual",
    rate=Decimal("0.30"),
    effective_from=date(1900, 1, 1),
    effective_to=None,
)

SYNTH_USD_ID = "10000000-0000-0000-0000-000000000001"
SYNTH_SGD_ID = "20000000-0000-0000-0000-000000000002"
SYNTH_GBP_ID = "30000000-0000-0000-0000-000000000003"
PORTFOLIO_USD_ID = "40000000-0000-0000-0000-000000000001"
PORTFOLIO_SGD_ID = "40000000-0000-0000-0000-000000000002"


def make_security(
    security_id: str,
    ticker: str,
    currency: str,
    *,
    policy: str = "distributing",
    source_country: str | None = "US",
    exchange: str = "XTEST",
    market: str = "US",
) -> Security:
    return Security(
        security_id=uuid.UUID(security_id),
        ticker=ticker,
        exchange=exchange,
        market=market,
        name=f"{ticker} parity fixture",
        currency=currency,
        asset_type="ETF",
        domicile=source_country,
        income_source_country=source_country,
        timezone="UTC",
        distribution_policy=policy,
        expense_ratio=None,
    )


def make_prices(security_id: str, currency: str, closes: dict[str, str]) -> list[PriceBar]:
    return [
        PriceBar(
            security_id=uuid.UUID(security_id),
            trading_date=date.fromisoformat(trading_date),
            open=Decimal(close),
            high=Decimal(close),
            low=Decimal(close),
            close=Decimal(close),
            volume=0,
            currency=currency,
            exchange="XTEST",
            timezone="UTC",
            source="parity_fixture",
        )
        for trading_date, close in closes.items()
    ]


def make_dividend(
    security_id: str,
    ex_date: str,
    amount: str,
    currency: str,
    *,
    pay_date: str | None = None,
    dividend_type: str = "regular",
    source_country: str = "US",
) -> DividendEvent:
    return DividendEvent(
        security_id=uuid.UUID(security_id),
        ex_date=date.fromisoformat(ex_date),
        amount=Decimal(amount),
        currency=currency,
        pay_date=date.fromisoformat(pay_date) if pay_date else None,
        dividend_type=dividend_type,
        source_country=source_country,
        source="parity_fixture",
    )


def make_action(security_id: str, effective_date: str, ratio: str) -> CorporateAction:
    return CorporateAction(
        security_id=uuid.UUID(security_id),
        effective_date=date.fromisoformat(effective_date),
        action_type=CorporateActionType.SPLIT,
        ratio=Decimal(ratio),
        source="parity_fixture",
    )


def make_fx(currency: str, rates: dict[str, str]) -> list[FxRate]:
    return [
        FxRate(
            rate_date=date.fromisoformat(rate_date),
            base_currency=currency,
            rate_to_sgd=Decimal(rate_to_sgd),
            source="parity_fixture",
        )
        for rate_date, rate_to_sgd in rates.items()
    ]


def make_transaction(
    transaction_id: str,
    transaction_date: str,
    transaction_type: str,
    currency: str,
    *,
    security_id: str | None = None,
    quantity: str = "0",
    cash_amount: str = "0",
    fees: str = "0",
) -> PortfolioTransaction:
    return PortfolioTransaction(
        transaction_id=uuid.UUID(transaction_id),
        transaction_date=date.fromisoformat(transaction_date),
        security_id=uuid.UUID(security_id) if security_id else None,
        transaction_type=transaction_type,
        quantity=Decimal(quantity),
        cash_amount=Decimal(cash_amount),
        currency=currency,
        fees=Decimal(fees),
    )


def slim_security(security: Security) -> dict:
    return security.model_dump(mode="json")


def slim_prices(prices: list[PriceBar]) -> list[dict]:
    return [
        {
            "security_id": str(row.security_id),
            "trading_date": row.trading_date.isoformat(),
            "close": str(row.close),
            "currency": row.currency,
        }
        for row in prices
    ]


def slim_dividends(dividends: list[DividendEvent]) -> list[dict]:
    return [
        {
            "security_id": str(row.security_id),
            "ex_date": row.ex_date.isoformat(),
            "amount": str(row.amount),
            "currency": row.currency,
            "pay_date": row.pay_date.isoformat() if row.pay_date else None,
            "dividend_type": row.dividend_type.value,
            "source_country": row.source_country,
        }
        for row in dividends
    ]


def slim_fx(rates: list[FxRate]) -> list[dict]:
    return [
        {
            "rate_date": row.rate_date.isoformat(),
            "base_currency": row.base_currency,
            "rate_to_sgd": str(row.rate_to_sgd),
        }
        for row in rates
    ]


def slim_actions(actions: list[CorporateAction]) -> list[dict]:
    return [
        {
            "security_id": str(row.security_id),
            "effective_date": row.effective_date.isoformat(),
            "action_type": row.action_type.value,
            "ratio": str(row.ratio),
        }
        for row in actions
    ]


def slim_tax_rules(rules: list[TaxRule]) -> list[dict]:
    return [rule.model_dump(mode="json") for rule in rules]


def slim_transactions(transactions: list[PortfolioTransaction]) -> list[dict]:
    return [
        {
            "transaction_id": str(row.transaction_id),
            "transaction_date": row.transaction_date.isoformat(),
            "security_id": str(row.security_id) if row.security_id else None,
            "transaction_type": row.transaction_type.value,
            "quantity": str(row.quantity),
            "cash_amount": str(row.cash_amount),
            "currency": row.currency,
            "fees": str(row.fees),
        }
        for row in transactions
    ]


def envelope_or_error(run: Callable[[], BaseModel]) -> dict:
    """Run the Python engine and capture either the envelope or the rejection."""

    try:
        return run().model_dump(mode="json")
    except AnalysisDataError as error:
        return {"error": {"type": "AnalysisDataError", "message": str(error)}}
    except ValueError as error:
        return {"error": {"type": "ValueError", "message": str(error)}}


def analysis_input(
    security: Security,
    prices: list[PriceBar],
    fx_rates: list[FxRate],
    *,
    start_date: str,
    end_date: str,
    initial_sgd: str,
    dividends: list[DividendEvent] | None = None,
    corporate_actions: list[CorporateAction] | None = None,
    tax_rules: list[TaxRule] | None = None,
    scenario: dict | None = None,
) -> tuple[dict, dict]:
    dividends = dividends or []
    corporate_actions = corporate_actions or []
    tax_rules = tax_rules or []
    request = {
        "start_date": start_date,
        "end_date": end_date,
        "initial_sgd": initial_sgd,
        "scenario": scenario or {
            "dividends_enabled": True,
            "reinvest_dividends": True,
            "withholding_tax_enabled": True,
        },
    }
    input_rows = {
        "security": slim_security(security),
        "prices": slim_prices(prices),
        "fx_rates": slim_fx(fx_rates),
        "dividends": slim_dividends(dividends),
        "corporate_actions": slim_actions(corporate_actions),
        "tax_rules": slim_tax_rules(tax_rules),
        "request": request,
    }
    golden = envelope_or_error(
        lambda: analyze_security(
            security=security,
            prices=prices,
            fx_rates=fx_rates,
            start_date=date.fromisoformat(request["start_date"]),
            end_date=date.fromisoformat(request["end_date"]),
            initial_sgd=request["initial_sgd"],
            scenario=AnalysisScenario(**request["scenario"]),
            dividends=dividends,
            corporate_actions=corporate_actions,
            tax_rules=tax_rules,
        )
    )
    return input_rows, golden


def dca_input(
    security: Security,
    prices: list[PriceBar],
    fx_rates: list[FxRate],
    *,
    start_date: str,
    end_date: str,
    contribution_sgd: str,
    frequency: str,
    dividends: list[DividendEvent] | None = None,
    corporate_actions: list[CorporateAction] | None = None,
    tax_rules: list[TaxRule] | None = None,
    scenario: dict | None = None,
) -> tuple[dict, dict]:
    dividends = dividends or []
    corporate_actions = corporate_actions or []
    tax_rules = tax_rules or []
    request = {
        "start_date": start_date,
        "end_date": end_date,
        "contribution_sgd": contribution_sgd,
        "frequency": frequency,
        "scenario": scenario or {
            "dividends_enabled": True,
            "reinvest_dividends": True,
            "withholding_tax_enabled": True,
        },
    }
    input_rows = {
        "security": slim_security(security),
        "prices": slim_prices(prices),
        "fx_rates": slim_fx(fx_rates),
        "dividends": slim_dividends(dividends),
        "corporate_actions": slim_actions(corporate_actions),
        "tax_rules": slim_tax_rules(tax_rules),
        "request": request,
    }
    golden = envelope_or_error(
        lambda: dca_analysis(
            security=security,
            prices=prices,
            fx_rates=fx_rates,
            start_date=date.fromisoformat(request["start_date"]),
            end_date=date.fromisoformat(request["end_date"]),
            contribution_sgd=request["contribution_sgd"],
            frequency=DcaFrequency(request["frequency"]),
            scenario=AnalysisScenario(**request["scenario"]),
            dividends=dividends,
            corporate_actions=corporate_actions,
            tax_rules=tax_rules,
        )
    )
    return input_rows, golden


def portfolio_input(
    securities: list[Security],
    prices: list[PriceBar],
    fx_rates: list[FxRate],
    transactions: list[PortfolioTransaction],
    *,
    as_of: str,
) -> tuple[dict, dict]:
    security_map = {security.security_id: security for security in securities}
    request = {"as_of": as_of, "transactions": slim_transactions(transactions)}
    input_rows = {
        "security": [slim_security(security) for security in securities],
        "prices": slim_prices(prices),
        "fx_rates": slim_fx(fx_rates),
        "dividends": [],
        "corporate_actions": [],
        "tax_rules": [],
        "request": request,
    }
    golden = envelope_or_error(
        lambda: analyze_portfolio(
            transactions=transactions,
            securities=security_map,
            prices=prices,
            fx_rates=fx_rates,
            as_of=date.fromisoformat(as_of),
        )
    )
    return input_rows, golden


def load_real_security_rows(engine: SGInvestingEngine, ticker: str, years: list[int]) -> tuple:
    """Load one catalog security's committed local Parquet rows for the years."""

    security = engine.catalog.security_by_ticker(ticker)
    prices = [
        row
        for year in years
        for row in engine.store.read_prices(market=security.market, year=year)
        if row.security_id == security.security_id
    ]
    dividends = [
        row for year in years for row in engine.store.read_dividends(year=year)
        if row.security_id == security.security_id
    ]
    actions = [
        row for year in years for row in engine.store.read_corporate_actions(year=year)
        if row.security_id == security.security_id
    ]
    fx = [
        row
        for year in years
        for row in engine.store.read_fx(base_currency=security.currency, year=year)
    ]
    return security, prices, dividends, actions, fx


SYNTH_USD_PRICES = make_prices(
    SYNTH_USD_ID,
    "USD",
    {
        "2024-01-02": "50.00",
        "2024-01-03": "51.25",
        "2024-01-04": "52.00",
        "2024-01-05": "52.50",
        "2024-01-08": "26.80",
        "2024-01-09": "27.10",
        "2024-01-10": "27.40",
        "2024-01-16": "27.00",
        "2024-01-17": "27.35",
        "2024-01-18": "27.60",
    },
)
SYNTH_USD_FX = make_fx(
    "USD",
    {"2024-01-02": "1.3450", "2024-01-08": "1.3480", "2024-01-09": "1.3470", "2024-01-18": "1.3520"},
)
SYNTH_USD_ACTIONS = [make_action(SYNTH_USD_ID, "2024-01-08", "2")]
SYNTH_USD_DIVIDENDS = [
    make_dividend(SYNTH_USD_ID, "2024-01-05", "0.50", "USD", pay_date="2024-01-09"),
    make_dividend(SYNTH_USD_ID, "2024-01-16", "0.25", "USD", pay_date="2024-01-18"),
]

ESTIMATED_PRICES = make_prices(
    SYNTH_USD_ID,
    "USD",
    {
        "2024-01-02": "50.00",
        "2024-01-03": "50.40",
        "2024-01-04": "50.80",
        "2024-01-05": "51.10",
        "2024-01-08": "51.30",
        "2024-02-05": "52.10",
    },
)

AFTER_VALUATION_PRICES = make_prices(
    SYNTH_USD_ID,
    "USD",
    {
        "2024-01-02": "50.00",
        "2024-01-03": "50.40",
        "2024-01-04": "50.80",
        "2024-01-05": "51.10",
        "2024-01-08": "51.30",
        "2024-01-09": "51.20",
        "2024-01-10": "51.40",
        "2024-01-11": "51.55",
        "2024-01-12": "51.60",
        "2024-02-20": "52.30",
    },
)

STALE_PRICES = make_prices(
    SYNTH_USD_ID,
    "USD",
    {
        "2024-01-02": "50.00",
        "2024-01-03": "50.40",
        "2024-01-04": "50.80",
        "2024-01-05": "51.10",
        "2024-01-08": "51.30",
        "2024-01-09": "51.20",
        "2024-01-10": "51.40",
        "2024-01-11": "51.55",
        "2024-01-12": "51.60",
    },
)

SGD_PRICES = make_prices(
    SYNTH_SGD_ID,
    "SGD",
    {
        "2024-01-02": "3.10",
        "2024-01-03": "3.12",
        "2024-02-01": "3.20",
        "2024-03-01": "3.15",
        "2024-03-15": "3.18",
        "2024-04-01": "3.30",
        "2024-05-02": "3.25",
        "2024-05-17": "3.28",
        "2024-06-03": "3.40",
        "2024-06-28": "3.45",
    },
)
SGD_DIVIDENDS = [
    make_dividend(SYNTH_SGD_ID, "2024-03-01", "0.05", "SGD", pay_date="2024-03-15", source_country="SG"),
    make_dividend(SYNTH_SGD_ID, "2024-05-02", "0.055", "SGD", pay_date="2024-05-17", source_country="SG"),
]

DCA_PRICES = make_prices(
    SYNTH_USD_ID,
    "USD",
    {
        "2024-01-02": "100.00",
        "2024-02-01": "101.50",
        "2024-03-01": "100.20",
        "2024-03-15": "101.00",
        "2024-04-01": "103.00",
        "2024-05-01": "104.20",
        "2024-06-03": "105.10",
        "2024-07-01": "106.00",
        "2024-08-01": "105.40",
        "2024-09-02": "107.00",
        "2024-09-16": "107.60",
        "2024-10-01": "108.20",
        "2024-11-01": "109.00",
        "2024-12-02": "110.50",
    },
)
DCA_FX = make_fx("USD", {"2024-01-01": "1.35"})
DCA_DIVIDENDS = [
    make_dividend(SYNTH_USD_ID, "2024-03-01", "0.40", "USD", pay_date="2024-03-15"),
    make_dividend(SYNTH_USD_ID, "2024-09-02", "0.45", "USD", pay_date="2024-09-16"),
]

PORTFOLIO_USD_SECURITY = make_security(PORTFOLIO_USD_ID, "USAETF", "USD")
PORTFOLIO_SGD_SECURITY = make_security(
    PORTFOLIO_SGD_ID, "SGREIT", "SGD", source_country="SG", market="SG", exchange="SGX"
)
PORTFOLIO_PRICES = make_prices(
    PORTFOLIO_USD_ID,
    "USD",
    {"2024-01-15": "100.00", "2024-05-20": "105.00", "2024-06-28": "112.00"},
) + make_prices(
    PORTFOLIO_SGD_ID,
    "SGD",
    {"2024-02-15": "3.20", "2024-06-28": "3.40"},
)
PORTFOLIO_FX = make_fx("USD", {"2024-01-15": "1.3400", "2024-06-28": "1.3500"})


def build_fixtures() -> list[dict]:
    engine = SGInvestingEngine(REPO_ROOT)
    fixtures: list[dict] = []

    def add(name: str, category: str, kind: str, input_rows: dict, golden: dict) -> None:
        fixtures.append(
            {"name": name, "category": category, "kind": kind, "input_rows": input_rows, "golden_envelope": golden}
        )

    # --- (a) USD ETF, real catalog securities via the committed Parquet store ---
    qqq, qqq_prices, qqq_dividends, _qqq_actions, qqq_fx = load_real_security_rows(engine, "QQQ", [2024])
    input_rows, golden = analysis_input(
        qqq,
        qqq_prices,
        qqq_fx,
        start_date="2024-01-02",
        end_date="2024-12-31",
        initial_sgd="10000",
        dividends=qqq_dividends,
        tax_rules=engine.tax_rules,
    )
    add("qqq-2024-analysis-reinvest", "usd-etf-real", "analysis", input_rows, golden)

    input_rows, golden = dca_input(
        qqq,
        qqq_prices,
        qqq_fx,
        start_date="2024-01-02",
        end_date="2024-12-31",
        contribution_sgd="1000",
        frequency="monthly",
        dividends=qqq_dividends,
        tax_rules=engine.tax_rules,
    )
    add("qqq-2024-dca-monthly", "dca", "dca", input_rows, golden)

    smh, smh_prices, smh_dividends, smh_actions, smh_fx = load_real_security_rows(engine, "SMH", [2023])
    input_rows, golden = analysis_input(
        smh,
        smh_prices,
        smh_fx,
        start_date="2023-01-03",
        end_date="2023-12-29",
        initial_sgd="5000",
        dividends=smh_dividends,
        corporate_actions=smh_actions,
        tax_rules=engine.tax_rules,
    )
    add("smh-2023-real-split", "usd-etf-real", "analysis", input_rows, golden)

    # --- (a) synthetic USD case with a split ---
    security = make_security(SYNTH_USD_ID, "SYNSPLIT", "USD")
    input_rows, golden = analysis_input(
        security,
        SYNTH_USD_PRICES,
        SYNTH_USD_FX,
        start_date="2024-01-02",
        end_date="2024-01-18",
        initial_sgd="1000",
        dividends=SYNTH_USD_DIVIDENDS,
        corporate_actions=SYNTH_USD_ACTIONS,
        tax_rules=[US_TAX_RULE],
    )
    add("synthetic-usd-split-reinvest", "usd-split-synthetic", "analysis", input_rows, golden)

    # --- (b) SGD security: no FX history, dividends without FX conversion ---
    sgd_security = make_security(
        SYNTH_SGD_ID, "SGDPARITY", "SGD", source_country="SG", market="SG", exchange="SGX"
    )
    input_rows, golden = analysis_input(
        sgd_security,
        SGD_PRICES,
        [],
        start_date="2024-01-02",
        end_date="2024-06-28",
        initial_sgd="3000",
        dividends=SGD_DIVIDENDS,
        tax_rules=[],
    )
    add("sgd-security-dividends-reinvest", "sgd-security", "analysis", input_rows, golden)

    # --- (c) dividend edge cases ---
    security = make_security(SYNTH_USD_ID, "SYNUSD", "USD")
    input_rows, golden = analysis_input(
        security,
        make_prices(
            SYNTH_USD_ID,
            "USD",
            {"2024-01-02": "50.00", "2024-01-03": "50.40", "2024-01-04": "50.80", "2024-01-05": "51.10"},
        ),
        make_fx("USD", {"2024-01-02": "1.35"}),
        start_date="2024-01-02",
        end_date="2024-01-05",
        initial_sgd="1000",
        dividends=[make_dividend(SYNTH_USD_ID, "2024-01-04", "0.50", "USD", pay_date="2024-01-03")],
        tax_rules=[US_TAX_RULE],
    )
    add("dividend-pay-before-ex-rejected", "dividend-edge", "analysis", input_rows, golden)

    input_rows, golden = analysis_input(
        security,
        ESTIMATED_PRICES,
        make_fx("USD", {"2024-01-02": "1.35", "2024-02-05": "1.34"}),
        start_date="2024-01-02",
        end_date="2024-02-05",
        initial_sgd="1000",
        dividends=[make_dividend(SYNTH_USD_ID, "2024-01-04", "0.50", "USD", pay_date=None)],
        tax_rules=[US_TAX_RULE],
    )
    add("dividend-estimated-pay-date", "dividend-edge", "analysis", input_rows, golden)

    accumulating = make_security(SYNTH_USD_ID, "SYNACC", "USD", policy="accumulating")
    input_rows, golden = analysis_input(
        accumulating,
        SYNTH_USD_PRICES,
        SYNTH_USD_FX,
        start_date="2024-01-02",
        end_date="2024-01-18",
        initial_sgd="1000",
        dividends=SYNTH_USD_DIVIDENDS,
        tax_rules=[US_TAX_RULE],
    )
    add("dividend-accumulating-ignored", "dividend-edge", "analysis", input_rows, golden)

    input_rows, golden = analysis_input(
        security,
        SYNTH_USD_PRICES,
        SYNTH_USD_FX,
        start_date="2024-01-02",
        end_date="2024-01-18",
        initial_sgd="1000",
        tax_rules=[US_TAX_RULE],
    )
    add("dividend-zero-dividend-security", "dividend-edge", "analysis", input_rows, golden)

    # --- (d) FX cases ---
    conversion_prices = make_prices(
        SYNTH_USD_ID,
        "USD",
        {"2024-01-02": "100.00", "2024-06-28": "110.00"},
    )
    input_rows, golden = analysis_input(
        security,
        conversion_prices,
        make_fx("USD", {"2024-01-02": "1.3500", "2024-06-28": "1.3100"}),
        start_date="2024-01-02",
        end_date="2024-06-28",
        initial_sgd="5000",
        tax_rules=[US_TAX_RULE],
    )
    add("fx-normal-conversion", "fx", "analysis", input_rows, golden)

    input_rows, golden = analysis_input(
        security,
        STALE_PRICES,
        make_fx("USD", {"2024-01-02": "1.3500"}),
        start_date="2024-01-02",
        end_date="2024-01-12",
        initial_sgd="1000",
        tax_rules=[US_TAX_RULE],
    )
    add("fx-stale-rate-warning", "fx", "analysis", input_rows, golden)

    gbp_security = make_security(SYNTH_GBP_ID, "SYNGBP", "GBP", source_country="GB", exchange="LSE", market="GB")
    input_rows, golden = analysis_input(
        gbp_security,
        make_prices(SYNTH_GBP_ID, "GBP", {"2024-01-02": "10.00", "2024-01-05": "10.50"}),
        [],
        start_date="2024-01-02",
        end_date="2024-01-05",
        initial_sgd="1000",
        tax_rules=[US_TAX_RULE],
    )
    add("fx-missing-history-rejected", "fx", "analysis", input_rows, golden)

    # --- (d) incomplete-data warnings ---
    input_rows, golden = analysis_input(
        security,
        AFTER_VALUATION_PRICES,
        make_fx("USD", {"2024-01-02": "1.35", "2024-02-20": "1.34"}),
        start_date="2024-01-02",
        end_date="2024-01-10",
        initial_sgd="500",
        dividends=[make_dividend(SYNTH_USD_ID, "2024-01-04", "0.50", "USD", pay_date="2024-02-20")],
        tax_rules=[US_TAX_RULE],
    )
    add("dividend-after-valuation-excluded", "incomplete-data", "analysis", input_rows, golden)

    # --- (e) DCA schedules (XIRR fields) ---
    input_rows, golden = dca_input(
        security,
        DCA_PRICES,
        DCA_FX,
        start_date="2024-01-01",
        end_date="2024-12-31",
        contribution_sgd="500",
        frequency="quarterly",
        tax_rules=[US_TAX_RULE],
    )
    add("dca-quarterly-synthetic", "dca", "dca", input_rows, golden)

    input_rows, golden = dca_input(
        security,
        DCA_PRICES,
        DCA_FX,
        start_date="2024-01-01",
        end_date="2024-12-31",
        contribution_sgd="1200",
        frequency="yearly",
        tax_rules=[US_TAX_RULE],
    )
    add("dca-yearly-synthetic", "dca", "dca", input_rows, golden)

    input_rows, golden = dca_input(
        security,
        DCA_PRICES,
        DCA_FX,
        start_date="2024-01-01",
        end_date="2024-12-31",
        contribution_sgd="200",
        frequency="monthly",
        dividends=DCA_DIVIDENDS,
        tax_rules=[US_TAX_RULE],
        scenario={
            "dividends_enabled": True,
            "reinvest_dividends": False,
            "withholding_tax_enabled": True,
        },
    )
    add("dca-monthly-synthetic-cash-dividends", "dca", "dca", input_rows, golden)

    # --- (e2) Sprint 4 DCA static-site fixtures ---
    # SGD security DCA: in-memory rows, no FX history at all.
    sgd_dca_security = make_security(
        SYNTH_SGD_ID, "SGDDCA", "SGD", source_country="SG", market="SG", exchange="SGX"
    )
    input_rows, golden = dca_input(
        sgd_dca_security,
        SGD_PRICES,
        [],
        start_date="2024-01-02",
        end_date="2024-06-28",
        contribution_sgd="400",
        frequency="monthly",
        dividends=SGD_DIVIDENDS,
        tax_rules=[],
    )
    add("dca-sgd-security-monthly", "dca", "dca", input_rows, golden)

    # Accumulating fund: dividend rows exist in the input but must be ignored,
    # with the policy warning preserved.
    accumulating_dca = make_security(SYNTH_USD_ID, "SYNACCDCA", "USD", policy="accumulating")
    input_rows, golden = dca_input(
        accumulating_dca,
        DCA_PRICES,
        DCA_FX,
        start_date="2024-01-01",
        end_date="2024-12-31",
        contribution_sgd="250",
        frequency="monthly",
        dividends=DCA_DIVIDENDS,
        tax_rules=[US_TAX_RULE],
    )
    add("dca-accumulating-fund-monthly", "dca", "dca", input_rows, golden)

    # Zero-dividend security: pure price + contributions path.
    input_rows, golden = dca_input(
        security,
        DCA_PRICES,
        DCA_FX,
        start_date="2024-01-01",
        end_date="2024-12-31",
        contribution_sgd="300",
        frequency="monthly",
        tax_rules=[US_TAX_RULE],
    )
    add("dca-zero-dividend-monthly", "dca", "dca", input_rows, golden)

    # Invalid inputs: error envelopes (inverted range, non-positive amount).
    input_rows, golden = dca_input(
        security,
        [],
        [],
        start_date="2024-06-01",
        end_date="2024-01-01",
        contribution_sgd="100",
        frequency="monthly",
        tax_rules=[US_TAX_RULE],
    )
    add("dca-invalid-date-range", "dca", "dca", input_rows, golden)

    input_rows, golden = dca_input(
        security,
        [],
        [],
        start_date="2024-01-01",
        end_date="2024-12-31",
        contribution_sgd="0",
        frequency="monthly",
        tax_rules=[US_TAX_RULE],
    )
    add("dca-invalid-amount", "dca", "dca", input_rows, golden)

    # Real-data QQQ 2024 quarterly/yearly goldens: consumed by the parity
    # suite and by frontend/engine/dca-packs-integration.mjs (packs → loader →
    # engine must reproduce these exactly).
    input_rows, golden = dca_input(
        qqq,
        qqq_prices,
        qqq_fx,
        start_date="2024-01-02",
        end_date="2024-12-31",
        contribution_sgd="1500",
        frequency="quarterly",
        dividends=qqq_dividends,
        tax_rules=engine.tax_rules,
    )
    add("dca-qqq-2024-quarterly", "dca", "dca", input_rows, golden)

    input_rows, golden = dca_input(
        qqq,
        qqq_prices,
        qqq_fx,
        start_date="2024-01-02",
        end_date="2024-12-31",
        contribution_sgd="6000",
        frequency="yearly",
        dividends=qqq_dividends,
        tax_rules=engine.tax_rules,
    )
    add("dca-qqq-2024-yearly", "dca", "dca", input_rows, golden)

    # --- (f) portfolio cases ---
    transactions = [
        make_transaction("00000000-0000-0000-0000-a00000000001", "2024-01-15", "CASH_DEPOSIT", "USD", cash_amount="10000"),
        make_transaction(
            "00000000-0000-0000-0000-a00000000002",
            "2024-01-15",
            "BUY",
            "USD",
            security_id=PORTFOLIO_USD_ID,
            quantity="50",
            cash_amount="5000",
            fees="5",
        ),
        make_transaction("00000000-0000-0000-0000-a00000000003", "2024-02-15", "CASH_DEPOSIT", "SGD", cash_amount="5000"),
        make_transaction(
            "00000000-0000-0000-0000-a00000000004",
            "2024-02-15",
            "BUY",
            "SGD",
            security_id=PORTFOLIO_SGD_ID,
            quantity="1000",
            cash_amount="3200",
            fees="5",
        ),
        make_transaction(
            "00000000-0000-0000-0000-a00000000005",
            "2024-04-10",
            "DIVIDEND",
            "SGD",
            security_id=PORTFOLIO_SGD_ID,
            cash_amount="55",
        ),
        make_transaction(
            "00000000-0000-0000-0000-a00000000006",
            "2024-05-20",
            "SELL",
            "USD",
            security_id=PORTFOLIO_USD_ID,
            quantity="10",
            cash_amount="1050",
            fees="4",
        ),
        make_transaction(
            "00000000-0000-0000-0000-a00000000007",
            "2024-06-10",
            "CASH_WITHDRAWAL",
            "SGD",
            cash_amount="1000",
        ),
    ]
    input_rows, golden = portfolio_input(
        [PORTFOLIO_USD_SECURITY, PORTFOLIO_SGD_SECURITY],
        PORTFOLIO_PRICES,
        PORTFOLIO_FX,
        transactions,
        as_of="2024-06-28",
    )
    add("portfolio-mixed-currency", "portfolio", "portfolio", input_rows, golden)

    zero_transactions = [
        make_transaction("00000000-0000-0000-0000-b00000000001", "2024-01-15", "CASH_DEPOSIT", "USD", cash_amount="6000"),
        make_transaction(
            "00000000-0000-0000-0000-b00000000002",
            "2024-01-15",
            "BUY",
            "USD",
            security_id=PORTFOLIO_USD_ID,
            quantity="5",
            cash_amount="500",
            fees="2",
        ),
        make_transaction(
            "00000000-0000-0000-0000-b00000000003",
            "2024-03-01",
            "SELL",
            "USD",
            security_id=PORTFOLIO_USD_ID,
            quantity="5",
            cash_amount="550",
            fees="3",
        ),
    ]
    input_rows, golden = portfolio_input(
        [PORTFOLIO_USD_SECURITY],
        PORTFOLIO_PRICES,
        PORTFOLIO_FX,
        zero_transactions,
        as_of="2024-06-28",
    )
    add("portfolio-zero-holding", "portfolio", "portfolio", input_rows, golden)

    cash_only_transactions = [
        make_transaction("00000000-0000-0000-0000-c00000000001", "2024-01-15", "CASH_DEPOSIT", "SGD", cash_amount="10000"),
        make_transaction("00000000-0000-0000-0000-c00000000002", "2024-02-15", "CASH_DEPOSIT", "USD", cash_amount="2000"),
        make_transaction("00000000-0000-0000-0000-c00000000003", "2024-03-15", "CASH_WITHDRAWAL", "USD", cash_amount="2500"),
    ]
    input_rows, golden = portfolio_input(
        [PORTFOLIO_USD_SECURITY, PORTFOLIO_SGD_SECURITY],
        PORTFOLIO_PRICES,
        PORTFOLIO_FX,
        cash_only_transactions,
        as_of="2024-06-28",
    )
    add("portfolio-cash-only", "portfolio", "portfolio", input_rows, golden)

    missing_price_transactions = [
        make_transaction(
            "00000000-0000-0000-0000-d00000000001",
            "2024-01-15",
            "BUY",
            "USD",
            security_id=PORTFOLIO_USD_ID,
            quantity="10",
            cash_amount="1000",
        ),
    ]
    input_rows, golden = portfolio_input(
        [PORTFOLIO_USD_SECURITY],
        make_prices(PORTFOLIO_USD_ID, "USD", {"2024-02-01": "105.00"}),
        PORTFOLIO_FX,
        missing_price_transactions,
        as_of="2024-01-20",
    )
    add("portfolio-missing-as-of-price", "portfolio", "portfolio", input_rows, golden)

    return fixtures


def main() -> None:
    fixtures = build_fixtures()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.json"):
        stale.unlink()
    total_bytes = 0
    for fixture in fixtures:
        path = OUT_DIR / f"{fixture['name']}.json"
        payload = json.dumps(fixture, indent=2)
        total_bytes += len(payload.encode("utf-8"))
        path.write_text(payload + "\n", encoding="utf-8")
    categories: dict[str, int] = {}
    for fixture in fixtures:
        categories[fixture["category"]] = categories.get(fixture["category"], 0) + 1
    print(f"Wrote {len(fixtures)} fixtures ({total_bytes} bytes) to {OUT_DIR.relative_to(REPO_ROOT)}")
    for category, count in sorted(categories.items()):
        print(f"  {category}: {count}")


if __name__ == "__main__":
    main()
