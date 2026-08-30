from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest import TestCase

from sg_investing.calculations.dca import DcaFrequency, dca_analysis
from sg_investing.models import AssetType, DividendEvent, FxRate, PriceBar, Security, TaxRule


class DcaTests(TestCase):
    def setUp(self) -> None:
        self.security = Security(
            ticker="TEST",
            exchange="NYSE",
            market="US",
            name="Synthetic Security",
            currency="USD",
            asset_type=AssetType.EQUITY,
            income_source_country="US",
        )

    def price(self, day: date, close: str) -> PriceBar:
        amount = Decimal(close)
        return PriceBar(
            security_id=self.security.security_id,
            trading_date=day,
            open=amount,
            high=amount,
            low=amount,
            close=amount,
            volume=1,
            currency="USD",
            exchange="NYSE",
            timezone="America/New_York",
            source="synthetic",
        )

    def test_monthly_dca_uses_first_available_trading_day_and_xirr(self) -> None:
        prices = [
            self.price(date(2024, 1, 2), "100"),
            self.price(date(2024, 2, 1), "100"),
            self.price(date(2024, 3, 1), "110"),
        ]
        fx = [FxRate(rate_date=row.trading_date, base_currency="USD", rate_to_sgd=Decimal("1"), source="synthetic") for row in prices]
        result = dca_analysis(
            security=self.security,
            prices=prices,
            fx_rates=fx,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 1),
            contribution_sgd=Decimal("100"),
            frequency=DcaFrequency.MONTHLY,
        )

        self.assertEqual(result.contribution_dates, [date(2024, 1, 2), date(2024, 2, 1), date(2024, 3, 1)])
        self.assertEqual(result.total_contributed_sgd, Decimal("300"))
        self.assertEqual(result.total_contributed_foreign_currency, Decimal("300"))
        self.assertEqual(result.shares, Decimal("2") + Decimal("100") / Decimal("110"))
        self.assertEqual(result.final_value_sgd, Decimal("320"))
        self.assertEqual(result.final_value_foreign_currency, Decimal("320"))
        self.assertEqual(result.gain_loss_foreign_currency, Decimal("20"))
        self.assertEqual(result.xirr_foreign_currency, result.xirr)
        self.assertIsNotNone(result.xirr)

    def test_dca_reinvests_dividend_only_on_pay_date(self) -> None:
        prices = [
            self.price(date(2024, 1, 2), "100"),
            self.price(date(2024, 2, 1), "100"),
            self.price(date(2024, 3, 1), "110"),
        ]
        fx = [FxRate(rate_date=row.trading_date, base_currency="USD", rate_to_sgd=Decimal("1"), source="synthetic") for row in prices]
        result = dca_analysis(
            security=self.security,
            prices=prices,
            fx_rates=fx,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 1),
            contribution_sgd=Decimal("100"),
            frequency=DcaFrequency.MONTHLY,
            dividends=[
                DividendEvent(
                    security_id=self.security.security_id,
                    ex_date=date(2024, 2, 1),
                    pay_date=date(2024, 3, 1),
                    amount=Decimal("10"),
                    currency="USD",
                    source_country="US",
                    source="synthetic",
                )
            ],
            tax_rules=[TaxRule(rule_id="gross", source_country="US", rate=Decimal("0"), effective_from=date(1900, 1, 1))],
        )

        # The February contribution is made after the February ex-date; only
        # the January share receives the US$10 dividend. It is reinvested in
        # March at US$110 alongside the March contribution.
        self.assertEqual(result.shares, Decimal("3"))
        self.assertEqual(result.final_value_sgd, Decimal("330"))

    def test_dca_reports_native_currency_results_when_fx_changes(self) -> None:
        prices = [
            self.price(date(2024, 1, 2), "100"),
            self.price(date(2024, 2, 1), "100"),
            self.price(date(2024, 3, 1), "100"),
        ]
        fx = [
            FxRate(rate_date=date(2024, 1, 2), base_currency="USD", rate_to_sgd=Decimal("1"), source="synthetic"),
            FxRate(rate_date=date(2024, 2, 1), base_currency="USD", rate_to_sgd=Decimal("2"), source="synthetic"),
            FxRate(rate_date=date(2024, 3, 1), base_currency="USD", rate_to_sgd=Decimal("2"), source="synthetic"),
        ]

        result = dca_analysis(
            security=self.security,
            prices=prices,
            fx_rates=fx,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 1),
            contribution_sgd=Decimal("100"),
            frequency=DcaFrequency.MONTHLY,
        )

        # S$100 purchases US$100, US$50, then US$50. With an unchanged
        # US$100 price, USD performance is flat even though the SGD end value
        # reflects the stronger USD/SGD rate.
        self.assertEqual(result.total_contributed_foreign_currency, Decimal("200"))
        self.assertEqual(result.final_value_foreign_currency, Decimal("200"))
        self.assertEqual(result.gain_loss_foreign_currency, Decimal("0"))
        self.assertEqual(result.final_value_sgd, Decimal("400"))
        self.assertAlmostEqual(float(result.xirr_foreign_currency or Decimal("0")), 0.0, places=9)

    def test_dca_converts_a_dividend_currency_through_sgd(self) -> None:
        prices = [
            self.price(date(2024, 1, 2), "100"),
            self.price(date(2024, 2, 1), "100"),
            self.price(date(2024, 3, 1), "100"),
        ]
        fx = [
            FxRate(rate_date=date(2024, 1, 2), base_currency="USD", rate_to_sgd=Decimal("1"), source="synthetic"),
            FxRate(rate_date=date(2024, 2, 1), base_currency="USD", rate_to_sgd=Decimal("1"), source="synthetic"),
            FxRate(rate_date=date(2024, 3, 1), base_currency="USD", rate_to_sgd=Decimal("1"), source="synthetic"),
            FxRate(rate_date=date(2024, 3, 1), base_currency="JPY", rate_to_sgd=Decimal("0.01"), source="synthetic"),
        ]
        result = dca_analysis(
            security=self.security,
            prices=prices,
            fx_rates=fx,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 1),
            contribution_sgd=Decimal("100"),
            frequency=DcaFrequency.MONTHLY,
            dividends=[
                DividendEvent(
                    security_id=self.security.security_id,
                    ex_date=date(2024, 2, 1),
                    pay_date=date(2024, 3, 1),
                    amount=Decimal("100"),
                    currency="JPY",
                    source="synthetic",
                )
            ],
        )

        # JPY100 is S$1, which is USD1 at the payment-date FX rates.
        self.assertEqual(result.shares, Decimal("3.01"))
        self.assertEqual(result.final_value_foreign_currency, Decimal("301"))
        self.assertEqual(result.final_value_sgd, Decimal("301"))
