from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest import TestCase

from sg_investing.calculations.portfolio import analyze_portfolio
from sg_investing.models import (
    AssetType,
    FxRate,
    PortfolioTransaction,
    PriceBar,
    Security,
    TransactionType,
)


class PortfolioTests(TestCase):
    def setUp(self) -> None:
        self.security = Security(
            ticker="TEST",
            exchange="NYSE",
            market="US",
            name="Synthetic Security",
            currency="USD",
            asset_type=AssetType.EQUITY,
        )

    def test_weighted_average_cost_basis_and_realized_pl(self) -> None:
        result = analyze_portfolio(
            transactions=[
                PortfolioTransaction(
                    transaction_date=date(2024, 1, 2),
                    transaction_type=TransactionType.CASH_DEPOSIT,
                    cash_amount=Decimal("2500"),
                    currency="USD",
                ),
                PortfolioTransaction(
                    transaction_date=date(2024, 1, 2),
                    security_id=self.security.security_id,
                    transaction_type=TransactionType.BUY,
                    quantity=Decimal("10"),
                    cash_amount=Decimal("1000"),
                    currency="USD",
                ),
                PortfolioTransaction(
                    transaction_date=date(2024, 2, 2),
                    security_id=self.security.security_id,
                    transaction_type=TransactionType.BUY,
                    quantity=Decimal("10"),
                    cash_amount=Decimal("1200"),
                    currency="USD",
                ),
                PortfolioTransaction(
                    transaction_date=date(2024, 3, 2),
                    security_id=self.security.security_id,
                    transaction_type=TransactionType.SELL,
                    quantity=Decimal("5"),
                    cash_amount=Decimal("650"),
                    currency="USD",
                ),
            ],
            securities={self.security.security_id: self.security},
            prices=[
                PriceBar(
                    security_id=self.security.security_id,
                    trading_date=date(2024, 3, 4),
                    open=Decimal("140"),
                    high=Decimal("140"),
                    low=Decimal("140"),
                    close=Decimal("140"),
                    volume=10,
                    currency="USD",
                    exchange="NYSE",
                    timezone="America/New_York",
                    source="synthetic",
                )
            ],
            fx_rates=[
                FxRate(rate_date=date(2024, 3, 4), base_currency="USD", rate_to_sgd=Decimal("1.30"), source="synthetic")
            ],
            as_of=date(2024, 3, 4),
        )

        holding = result.holdings[0]
        self.assertEqual(holding.quantity, Decimal("15"))
        self.assertEqual(holding.weighted_average_cost, Decimal("110"))
        self.assertEqual(holding.cost_basis_native, Decimal("1650"))
        self.assertEqual(holding.realized_pl_native, Decimal("100"))
        self.assertEqual(result.cash_by_currency["USD"], Decimal("950"))
        self.assertEqual(result.total_market_value_sgd, Decimal("3050") * Decimal("1.30"))
