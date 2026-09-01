"""Generate Python-golden portfolio fixtures for Sprint 5 (S5.7).

Every fixture runs one ledger through the authoritative PYTHON engine
(``sg_investing.calculations.portfolio.analyze_portfolio``) and records the
resulting ``model_dump(mode="json")`` envelope as the golden reference,
alongside the slim input rows consumed by the JS verification runner
(``frontend/engine/portfolio-packs-integration.mjs``).

Fixtures are written to ``frontend/engine/parity/fixtures/portfolio-fixtures/``
— a dedicated subdirectory so the Sprint 3 parity runner
(``frontend/engine/parity/parity.mjs``, frozen at 20 top-level fixtures)
is unaffected.

Fixture cases (sprint task S5.7):

- ``portfolio-pack-qqq-buy-hold``        real QQQ data-pack inputs, single buy,
                                          as-of previous-close valuation.
- ``portfolio-pack-qqq-partial-sell``    real QQQ data-pack inputs, buy +
                                          partial sell (realised/unrealised).
- ``portfolio-synthetic-mixed-currency`` USD + SGD holdings, partial sell,
                                          dividends, cash deposit/withdrawal.
- ``portfolio-synthetic-dividends``      DIVIDEND rows feed cash only.
- ``portfolio-synthetic-cash-only``      deposits + withdrawal, no holdings.
- ``portfolio-synthetic-zero-holding``   buy then full sell, zero remaining.
- ``portfolio-synthetic-missing-as-of-price`` error golden (AnalysisDataError).

Two QQQ fixtures derive their inputs directly from the committed data packs
(``frontend/data/packs/``) — exactly the rows ``frontend/engine/pack-loader.js``
assembles in the browser — so the runner proves pack -> engine parity.
No live network calls are made.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from sg_investing.analysis import AnalysisDataError
from sg_investing.calculations.portfolio import analyze_portfolio
from sg_investing.models import (
    AssetType,
    DistributionPolicy,
    FxRate,
    PortfolioTransaction,
    PriceBar,
    Security,
    TransactionType,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "frontend" / "engine" / "parity" / "fixtures" / "portfolio-fixtures"
PACKS_DIR = REPO_ROOT / "frontend" / "data" / "packs"

QQQ_SECURITY_ID = "6cfd001d-07dc-44d9-aff8-d6c99b0ee80b"

FIXTURE_USD_ID = "50000000-0000-0000-0000-000000000001"
FIXTURE_SGD_ID = "50000000-0000-0000-0000-000000000002"


def make_security(
    security_id: str,
    ticker: str,
    currency: str,
    *,
    exchange: str = "XTEST",
    market: str = "US",
) -> Security:
    return Security(
        security_id=uuid.UUID(security_id),
        ticker=ticker,
        exchange=exchange,
        market=market,
        name=f"{ticker} portfolio fixture",
        currency=currency,
        asset_type=AssetType.ETF,
        domicile="US" if currency == "USD" else "SG",
        income_source_country="US" if currency == "USD" else "SG",
        isin=None,
        cusip=None,
        timezone="UTC",
        distribution_policy=DistributionPolicy.DISTRIBUTING,
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
            source="portfolio_fixture",
        )
        for trading_date, close in closes.items()
    ]


def make_fx(currency: str, rates: dict[str, str]) -> list[FxRate]:
    return [
        FxRate(
            rate_date=date.fromisoformat(rate_date),
            base_currency=currency,
            rate_to_sgd=Decimal(rate_to_sgd),
            source="portfolio_fixture",
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
        transaction_type=TransactionType(transaction_type),
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


def slim_fx(rates: list[FxRate]) -> list[dict]:
    return [
        {
            "rate_date": row.rate_date.isoformat(),
            "base_currency": row.base_currency,
            "rate_to_sgd": str(row.rate_to_sgd),
        }
        for row in rates
    ]


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


def golden_envelope(callable_result) -> dict:
    try:
        return callable_result().model_dump(mode="json")
    except AnalysisDataError as error:
        return {"error": {"type": "AnalysisDataError", "message": str(error)}}
    except ValueError as error:
        return {"error": {"type": "ValueError", "message": str(error)}}


def portfolio_fixture(
    name: str,
    securities: list[Security],
    prices: list[PriceBar],
    fx_rates: list[FxRate],
    transactions: list[PortfolioTransaction],
    *,
    as_of: str,
    meta: dict | None = None,
) -> dict:
    security_map = {security.security_id: security for security in securities}
    golden = golden_envelope(
        lambda: analyze_portfolio(
            transactions=transactions,
            securities=security_map,
            prices=prices,
            fx_rates=fx_rates,
            as_of=date.fromisoformat(as_of),
        )
    )
    return {
        "name": name,
        "category": "portfolio",
        "kind": "portfolio",
        "meta": meta or {"pack_derived": False},
        "input_rows": {
            "security": [slim_security(security) for security in securities],
            "prices": slim_prices(prices),
            "fx_rates": slim_fx(fx_rates),
            "dividends": [],
            "corporate_actions": [],
            "tax_rules": [],
            "request": {"as_of": as_of, "transactions": slim_transactions(transactions)},
        },
        "golden_envelope": golden,
    }


def pack_inputs(security_id: str, start_date: str, end_date: str) -> tuple[Security, list[PriceBar], list[FxRate]]:
    """Derive engine inputs from committed data packs exactly like pack-loader.js."""

    first_year = int(start_date[:4])
    last_year = int(end_date[:4])
    packs = [
        json.loads((PACKS_DIR / f"security={security_id}" / f"year={year}.json").read_text(encoding="utf-8"))
        for year in range(first_year, last_year + 1)
    ]
    pack_security = packs[0]["security"]
    security = Security(
        security_id=uuid.UUID(pack_security["security_id"]),
        ticker=pack_security["ticker"],
        exchange=pack_security["exchange"],
        market=pack_security["market"],
        name=pack_security["name"],
        currency=pack_security["currency"],
        asset_type=AssetType(pack_security["asset_type"]),
        domicile=pack_security["domicile"],
        income_source_country=pack_security["income_source_country"],
        isin=pack_security["isin"],
        cusip=pack_security["cusip"],
        timezone=pack_security["timezone"],
        active=pack_security["active"],
        distribution_policy=DistributionPolicy(pack_security["distribution_policy"]),
        expense_ratio=None,
    )
    prices: list[PriceBar] = []
    fx_rates: list[FxRate] = []
    for pack in packs:
        price_block = pack["prices"]
        for index, trading_date in enumerate(price_block["dates"]):
            close = Decimal(str(price_block["close"][index]))
            prices.append(
                PriceBar(
                    security_id=uuid.UUID(security_id),
                    trading_date=date.fromisoformat(trading_date),
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=0,
                    currency=security.currency,
                    exchange=security.exchange,
                    timezone=security.timezone,
                    source="data_pack",
                )
            )
        fx_block = pack["fx"]
        for index, rate_date in enumerate(fx_block["dates"]):
            fx_rates.append(
                FxRate(
                    rate_date=date.fromisoformat(rate_date),
                    base_currency=fx_block["base_currency"],
                    rate_to_sgd=Decimal(str(fx_block["rates"][index])),
                    source="data_pack",
                )
            )
    return security, prices, fx_rates


def build_fixtures() -> list[dict]:
    fixtures: list[dict] = []

    # --- (a) real QQQ data-pack inputs: buy and hold -------------------------
    qqq, qqq_prices, qqq_fx = pack_inputs(QQQ_SECURITY_ID, "2024-01-02", "2025-01-02")
    buy_hold = [
        make_transaction(
            "00000000-0000-0000-0000-e10000000001",
            "2024-01-02",
            "BUY",
            "USD",
            security_id=QQQ_SECURITY_ID,
            quantity="10",
            cash_amount="4000",
            fees="0",
        ),
    ]
    fixtures.append(
        portfolio_fixture(
            "portfolio-pack-qqq-buy-hold",
            [qqq],
            qqq_prices,
            qqq_fx,
            buy_hold,
            as_of="2025-01-02",
            meta={
                "pack_derived": True,
                "security_ticker": "QQQ",
                "input_start": "2024-01-02",
                "input_end": "2025-01-02",
            },
        )
    )

    # --- (b) real QQQ data-pack inputs: buy + partial sell -------------------
    partial_sell = [
        make_transaction(
            "00000000-0000-0000-0000-e20000000001",
            "2024-01-02",
            "BUY",
            "USD",
            security_id=QQQ_SECURITY_ID,
            quantity="10",
            cash_amount="4000",
            fees="5",
        ),
        make_transaction(
            "00000000-0000-0000-0000-e20000000002",
            "2024-05-20",
            "SELL",
            "USD",
            security_id=QQQ_SECURITY_ID,
            quantity="4",
            cash_amount="1700",
            fees="4",
        ),
    ]
    fixtures.append(
        portfolio_fixture(
            "portfolio-pack-qqq-partial-sell",
            [qqq],
            qqq_prices,
            qqq_fx,
            partial_sell,
            as_of="2025-01-02",
            meta={
                "pack_derived": True,
                "security_ticker": "QQQ",
                "input_start": "2024-01-02",
                "input_end": "2025-01-02",
            },
        )
    )

    # --- synthetic: multiple currencies, partial sell, dividends, cash rows --
    usd_security = make_security(FIXTURE_USD_ID, "USDETF", "USD")
    sgd_security = make_security(FIXTURE_SGD_ID, "SGDETF", "SGD", market="SG")
    synthetic_prices = [
        *make_prices(FIXTURE_USD_ID, "USD", {"2024-01-15": "100.00", "2024-05-20": "105.00", "2024-06-28": "112.00"}),
        *make_prices(FIXTURE_SGD_ID, "SGD", {"2024-02-15": "3.20", "2024-06-28": "3.40"}),
    ]
    synthetic_fx = make_fx("USD", {"2024-01-15": "1.3400", "2024-06-28": "1.3500"})
    mixed = [
        make_transaction(
            "00000000-0000-0000-0000-e30000000001", "2024-01-15", "CASH_DEPOSIT", "USD", cash_amount="10000"
        ),
        make_transaction(
            "00000000-0000-0000-0000-e30000000002",
            "2024-01-15",
            "BUY",
            "USD",
            security_id=FIXTURE_USD_ID,
            quantity="50",
            cash_amount="5000",
            fees="5",
        ),
        make_transaction(
            "00000000-0000-0000-0000-e30000000003", "2024-02-15", "CASH_DEPOSIT", "SGD", cash_amount="5000"
        ),
        make_transaction(
            "00000000-0000-0000-0000-e30000000004",
            "2024-02-15",
            "BUY",
            "SGD",
            security_id=FIXTURE_SGD_ID,
            quantity="1000",
            cash_amount="3200",
            fees="5",
        ),
        make_transaction(
            "00000000-0000-0000-0000-e30000000005",
            "2024-04-10",
            "DIVIDEND",
            "SGD",
            security_id=FIXTURE_SGD_ID,
            cash_amount="55",
        ),
        make_transaction(
            "00000000-0000-0000-0000-e30000000006",
            "2024-05-20",
            "SELL",
            "USD",
            security_id=FIXTURE_USD_ID,
            quantity="10",
            cash_amount="1050",
            fees="4",
        ),
        make_transaction(
            "00000000-0000-0000-0000-e30000000007", "2024-06-10", "CASH_WITHDRAWAL", "SGD", cash_amount="1000"
        ),
    ]
    fixtures.append(
        portfolio_fixture(
            "portfolio-synthetic-mixed-currency",
            [usd_security, sgd_security],
            synthetic_prices,
            synthetic_fx,
            mixed,
            as_of="2024-06-28",
            meta={"pack_derived": False, "covers": ["buys", "partial_sell", "multiple_currencies", "dividends", "cash_rows"]},
        )
    )

    # --- synthetic: dividends feed cash only ---------------------------------
    dividend_transactions = [
        make_transaction(
            "00000000-0000-0000-0000-e40000000001",
            "2024-01-15",
            "BUY",
            "USD",
            security_id=FIXTURE_USD_ID,
            quantity="10",
            cash_amount="1000",
        ),
        make_transaction(
            "00000000-0000-0000-0000-e40000000002",
            "2024-03-18",
            "DIVIDEND",
            "USD",
            security_id=FIXTURE_USD_ID,
            cash_amount="6.20",
            fees="0.10",
        ),
        make_transaction(
            "00000000-0000-0000-0000-e40000000003",
            "2024-06-10",
            "DIVIDEND",
            "USD",
            security_id=FIXTURE_USD_ID,
            cash_amount="7.00",
        ),
    ]
    fixtures.append(
        portfolio_fixture(
            "portfolio-synthetic-dividends",
            [usd_security],
            synthetic_prices,
            synthetic_fx,
            dividend_transactions,
            as_of="2024-06-28",
            meta={"pack_derived": False, "covers": ["buys", "dividends"]},
        )
    )

    # --- synthetic: cash-only rows, no holdings ------------------------------
    cash_only = [
        make_transaction("00000000-0000-0000-0000-e50000000001", "2024-01-15", "CASH_DEPOSIT", "SGD", cash_amount="10000"),
        make_transaction("00000000-0000-0000-0000-e50000000002", "2024-02-15", "CASH_DEPOSIT", "USD", cash_amount="2000"),
        make_transaction("00000000-0000-0000-0000-e50000000003", "2024-03-15", "CASH_WITHDRAWAL", "USD", cash_amount="2500"),
    ]
    fixtures.append(
        portfolio_fixture(
            "portfolio-synthetic-cash-only",
            [usd_security],
            synthetic_prices,
            synthetic_fx,
            cash_only,
            as_of="2024-06-28",
            meta={"pack_derived": False, "covers": ["cash_only_rows"]},
        )
    )

    # --- synthetic: full exit leaves zero holdings ---------------------------
    zero_transactions = [
        make_transaction(
            "00000000-0000-0000-0000-e60000000001",
            "2024-01-15",
            "BUY",
            "USD",
            security_id=FIXTURE_USD_ID,
            quantity="5",
            cash_amount="500",
            fees="2",
        ),
        make_transaction(
            "00000000-0000-0000-0000-e60000000002",
            "2024-03-01",
            "SELL",
            "USD",
            security_id=FIXTURE_USD_ID,
            quantity="5",
            cash_amount="550",
            fees="3",
        ),
    ]
    fixtures.append(
        portfolio_fixture(
            "portfolio-synthetic-zero-holding",
            [usd_security],
            synthetic_prices,
            synthetic_fx,
            zero_transactions,
            as_of="2024-06-28",
            meta={"pack_derived": False, "covers": ["zero_holdings", "realised_pl"]},
        )
    )

    # --- synthetic: no price on or before as-of -> Python error golden -------
    missing_price_prices = make_prices(FIXTURE_USD_ID, "USD", {"2024-02-01": "105.00"})
    missing_price_transactions = [
        make_transaction(
            "00000000-0000-0000-0000-e70000000001",
            "2024-01-15",
            "BUY",
            "USD",
            security_id=FIXTURE_USD_ID,
            quantity="10",
            cash_amount="1000",
        ),
    ]
    fixtures.append(
        portfolio_fixture(
            "portfolio-synthetic-missing-as-of-price",
            [usd_security],
            missing_price_prices,
            synthetic_fx,
            missing_price_transactions,
            as_of="2024-01-20",
            meta={"pack_derived": False, "covers": ["missing_as_of_price"]},
        )
    )

    return fixtures


def main() -> None:
    fixtures = build_fixtures()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.json"):
        stale.unlink()
    total_bytes = 0
    for fixture in fixtures:
        payload = json.dumps(fixture, indent=2)
        (OUT_DIR / f"{fixture['name']}.json").write_text(payload + "\n", encoding="utf-8")
        total_bytes += len(payload.encode("utf-8"))
    print(f"Wrote {len(fixtures)} portfolio fixtures ({total_bytes} bytes) to {OUT_DIR.relative_to(REPO_ROOT)}")
    for fixture in fixtures:
        status = "error-golden" if "error" in fixture["golden_envelope"] else "result-golden"
        print(f"  {fixture['name']}: {status}")


if __name__ == "__main__":
    main()
