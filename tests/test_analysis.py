from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest import TestCase

from sg_investing.analysis import AnalysisDataError, analyze_security
from sg_investing.models import (
    CorporateAction,
    CorporateActionType,
    DividendEvent,
    DividendType,
    FxRate,
    PriceBar,
    Security,
    TaxRule,
)


def decimal(value: str) -> Decimal:
    return Decimal(value)


class SecurityAnalysisTests(TestCase):
    def setUp(self) -> None:
        self.security = Security(
            ticker="TEST",
            exchange="NYSE",
            market="US",
            name="Synthetic US Equity",
            currency="USD",
            asset_type="equity",
            income_source_country="US",
            timezone="America/New_York",
        )

    def prices(self, rows: list[tuple[date, str]]) -> list[PriceBar]:
        return [
            PriceBar(
                security_id=self.security.security_id,
                trading_date=trading_date,
                open=decimal(close),
                high=decimal(close),
                low=decimal(close),
                close=decimal(close),
                volume=100,
                currency="USD",
                exchange="NYSE",
                timezone="America/New_York",
                source="synthetic",
            )
            for trading_date, close in rows
        ]

    def fx(self, rows: list[tuple[date, str]]) -> list[FxRate]:
        return [
            FxRate(
                rate_date=rate_date,
                base_currency="USD",
                rate_to_sgd=decimal(rate),
                source="synthetic",
            )
            for rate_date, rate in rows
        ]

    def tax_rules(self) -> list[TaxRule]:
        return [
            TaxRule(
                rule_id="US_DIVIDEND_NONRESIDENT",
                source_country="US",
                rate=decimal("0.30"),
                effective_from=date(1900, 1, 1),
            )
        ]

    def test_reinvestment_applies_tax_and_uses_pay_date_close(self) -> None:
        result = analyze_security(
            security=self.security,
            prices=self.prices(
                [
                    (date(2024, 1, 2), "100"),
                    (date(2024, 6, 3), "105"),
                    (date(2024, 7, 1), "110"),
                    (date(2025, 1, 2), "120"),
                ]
            ),
            fx_rates=self.fx([(date(2024, 1, 2), "1.30"), (date(2025, 1, 2), "1.40")]),
            start_date=date(2024, 1, 1),
            end_date=date(2025, 1, 3),
            initial_sgd="1300",
            dividends=[
                DividendEvent(
                    security_id=self.security.security_id,
                    ex_date=date(2024, 6, 1),
                    pay_date=date(2024, 7, 1),
                    amount=decimal("2"),
                    currency="USD",
                    source_country="US",
                    source="synthetic",
                )
            ],
            tax_rules=self.tax_rules(),
        )

        # S$1,300 / 1.30 / US$100 = 10 shares. The US$20 dividend is taxed at
        # 30%, so US$14 buys 0.127272... shares at US$110 on the pay date.
        self.assertEqual(result.dividends["gross_foreign_currency"], decimal("20"))
        self.assertEqual(result.dividends["withholding_tax_foreign_currency"], decimal("6.00"))
        self.assertEqual(result.initial_investment_foreign_currency, decimal("1000"))
        # No July FX observation is supplied, so the documented prior-date
        # rate resolution uses the 1.30 rate from the purchase date.
        self.assertEqual(result.dividends["gross_sgd_at_payment"], decimal("26.00"))
        self.assertEqual(result.dividends["withholding_tax_sgd_at_payment"], decimal("7.8000"))
        self.assertEqual(result.investment["shares"], decimal("10") + decimal("14") / decimal("110"))
        self.assertEqual(
            result.investment["final_value_sgd"],
            (decimal("10") + decimal("14") / decimal("110")) * decimal("120") * decimal("1.40"),
        )
        self.assertFalse(result.methodology["ter_deducted"])

    def test_reinvestment_does_not_receive_a_dividend_before_its_pay_date(self) -> None:
        result = analyze_security(
            security=self.security,
            prices=self.prices(
                [
                    (date(2024, 1, 2), "100"),
                    (date(2024, 2, 1), "100"),
                    (date(2024, 3, 1), "100"),
                    (date(2024, 4, 1), "100"),
                ]
            ),
            fx_rates=self.fx([(date(2024, 1, 2), "1.30"), (date(2024, 4, 1), "1.30")]),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 4, 1),
            initial_sgd="1300",
            dividends=[
                DividendEvent(
                    security_id=self.security.security_id,
                    ex_date=date(2024, 2, 1),
                    pay_date=date(2024, 4, 1),
                    amount=decimal("1"),
                    currency="USD",
                    source_country="US",
                    source="synthetic",
                ),
                DividendEvent(
                    security_id=self.security.security_id,
                    ex_date=date(2024, 3, 1),
                    pay_date=date(2024, 4, 1),
                    amount=decimal("1"),
                    currency="USD",
                    source_country="US",
                    source="synthetic",
                ),
            ],
            tax_rules=[
                TaxRule(
                    rule_id="NONE",
                    source_country="US",
                    rate=decimal("0"),
                    effective_from=date(1900, 1, 1),
                )
            ],
        )

        # The first dividend is not reinvested until April, so it cannot earn
        # the March dividend. Both US$10 dividends are reinvested together.
        self.assertEqual(result.dividends["gross_foreign_currency"], decimal("20"))
        self.assertEqual(result.investment["shares"], decimal("10.2"))

    def test_split_adjusts_held_shares_against_unadjusted_prices(self) -> None:
        result = analyze_security(
            security=self.security,
            prices=self.prices([(date(2024, 1, 2), "100"), (date(2024, 7, 1), "55")]),
            fx_rates=self.fx([(date(2024, 1, 2), "1.30"), (date(2024, 7, 1), "1.30")]),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 7, 1),
            initial_sgd="1300",
            corporate_actions=[
                CorporateAction(
                    security_id=self.security.security_id,
                    effective_date=date(2024, 6, 1),
                    action_type=CorporateActionType.SPLIT,
                    ratio=decimal("2"),
                    source="synthetic",
                )
            ],
        )

        self.assertEqual(result.investment["shares"], decimal("20"))
        self.assertEqual(result.investment["final_value_sgd"], decimal("1430"))

    def test_missing_pay_date_uses_approved_30_day_fallback(self) -> None:
        result = analyze_security(
            security=self.security,
            prices=self.prices(
                [(date(2024, 1, 2), "100"), (date(2024, 2, 1), "100"), (date(2024, 3, 4), "100")]
            ),
            fx_rates=self.fx([(date(2024, 1, 2), "1.30"), (date(2024, 3, 4), "1.30")]),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 3, 4),
            initial_sgd="1300",
            dividends=[
                DividendEvent(
                    security_id=self.security.security_id,
                    ex_date=date(2024, 2, 1),
                    amount=decimal("1"),
                    currency="USD",
                    source_country="US",
                    source="synthetic",
                )
            ],
            tax_rules=self.tax_rules(),
        )

        self.assertEqual(result.investment["shares"], decimal("10.07"))
        self.assertTrue(any("Approximated dividend pay date" in warning for warning in result.data_quality["warnings"]))

    def test_fx_direction_uses_foreign_currency_times_sgd_rate(self) -> None:
        result = analyze_security(
            security=self.security,
            prices=self.prices([(date(2024, 1, 2), "100"), (date(2025, 1, 2), "100")]),
            fx_rates=self.fx([(date(2024, 1, 2), "1.30"), (date(2025, 1, 2), "1.40")]),
            start_date=date(2024, 1, 2),
            end_date=date(2025, 1, 2),
            initial_sgd="1300",
        )

        self.assertEqual(result.investment["final_value_sgd"], decimal("1400"))
        self.assertEqual(result.investment["final_value_foreign_currency"], decimal("1000"))
        self.assertEqual(result.returns["total_return_foreign_currency"], decimal("0"))
        self.assertEqual(result.returns["cagr_foreign_currency"], decimal("0"))
        self.assertEqual(result.price_return["sgd"], decimal("1.40") / decimal("1.30") - decimal("1"))

    def test_dividend_currency_is_converted_through_sgd_at_payment(self) -> None:
        result = analyze_security(
            security=self.security,
            prices=self.prices(
                [
                    (date(2024, 1, 2), "100"),
                    (date(2024, 2, 1), "100"),
                    (date(2024, 3, 1), "100"),
                ]
            ),
            fx_rates=self.fx([(date(2024, 1, 2), "2"), (date(2024, 3, 1), "2")])
            + [
                FxRate(
                    rate_date=date(2024, 3, 1),
                    base_currency="JPY",
                    rate_to_sgd=decimal("0.02"),
                    source="synthetic",
                )
            ],
            start_date=date(2024, 1, 2),
            end_date=date(2024, 3, 1),
            initial_sgd="200",
            dividends=[
                DividendEvent(
                    security_id=self.security.security_id,
                    ex_date=date(2024, 2, 1),
                    pay_date=date(2024, 3, 1),
                    amount=decimal("100"),
                    currency="JPY",
                    source="synthetic",
                )
            ],
        )

        # JPY100 is S$2 at payment, or US$1 at the USD/SGD rate of 2.
        self.assertEqual(result.dividends["gross_foreign_currency"], decimal("1"))
        self.assertEqual(result.dividends["gross_sgd_at_payment"], decimal("2"))
        self.assertEqual(result.investment["final_value_sgd"], decimal("202"))

    def test_return_of_capital_is_cash_but_not_assumed_dividend_withholding(self) -> None:
        result = analyze_security(
            security=self.security,
            prices=self.prices(
                [
                    (date(2024, 1, 2), "100"),
                    (date(2024, 2, 1), "100"),
                    (date(2024, 3, 1), "100"),
                ]
            ),
            fx_rates=self.fx([(date(2024, 1, 2), "1"), (date(2024, 3, 1), "1")]),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 3, 1),
            initial_sgd="1000",
            dividends=[
                DividendEvent(
                    security_id=self.security.security_id,
                    ex_date=date(2024, 2, 1),
                    pay_date=date(2024, 3, 1),
                    amount=decimal("1"),
                    currency="USD",
                    dividend_type=DividendType.RETURN_OF_CAPITAL,
                    source_country="US",
                    source="synthetic",
                )
            ],
            tax_rules=self.tax_rules(),
        )

        self.assertEqual(result.dividends["gross_foreign_currency"], decimal("10"))
        self.assertEqual(result.dividends["withholding_tax_foreign_currency"], decimal("0"))
        self.assertTrue(any("Return of capital" in warning for warning in result.data_quality["warnings"]))

    def test_analysis_rejects_unvalidated_duplicate_dividend_events(self) -> None:
        event = DividendEvent(
            security_id=self.security.security_id,
            ex_date=date(2024, 2, 1),
            amount=decimal("1"),
            currency="USD",
            source="synthetic",
        )
        with self.assertRaisesRegex(AnalysisDataError, "failed validation"):
            analyze_security(
                security=self.security,
                prices=self.prices([(date(2024, 1, 2), "100"), (date(2024, 3, 1), "100")]),
                fx_rates=self.fx([(date(2024, 1, 2), "1"), (date(2024, 3, 1), "1")]),
                start_date=date(2024, 1, 2),
                end_date=date(2024, 3, 1),
                initial_sgd="1000",
                dividends=[event, event],
            )
