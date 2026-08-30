from __future__ import annotations

from datetime import date
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest import TestCase

from sg_investing.data.ingestion import update_security_prices
from sg_investing.data.storage import ParquetStore
from sg_investing.models import AssetType, DataQualityStatus, DividendEvent, FxRate, PriceBar, Security


class FakeProvider:
    name = "fake"

    def __init__(self, rows: list[PriceBar] | None = None, error: Exception | None = None) -> None:
        self.rows = rows or []
        self.error = error
        self.calls: list[tuple[date, date]] = []
        self.dividend_calls: list[tuple[date, date]] = []

    def get_prices(self, security: Security, start_date: date, end_date: date) -> list[PriceBar]:
        self.calls.append((start_date, end_date))
        if self.error:
            raise self.error
        return self.rows

    def get_dividends(self, security: Security, start_date: date, end_date: date) -> list[DividendEvent]:
        self.dividend_calls.append((start_date, end_date))
        return []

    def get_corporate_actions(self, security: Security, start_date: date, end_date: date) -> list[object]:
        return []

    def get_fx_rates(self, base_currency: str, start_date: date, end_date: date) -> list[FxRate]:
        return []


class IngestionTests(TestCase):
    def setUp(self) -> None:
        self.security = Security(
            ticker="TEST",
            exchange="NYSE",
            market="US",
            name="Synthetic Security",
            currency="USD",
            asset_type=AssetType.EQUITY,
        )

    def price(self, day: date, close: str = "100") -> PriceBar:
        amount = Decimal(close)
        return PriceBar(
            security_id=self.security.security_id,
            trading_date=day,
            open=amount,
            high=amount,
            low=amount,
            close=amount,
            volume=10,
            currency="USD",
            exchange="NYSE",
            timezone="America/New_York",
            source="fake",
        )

    def test_incremental_update_rechecks_recent_window(self) -> None:
        with TemporaryDirectory() as temporary:
            store = ParquetStore(temporary)
            initial = FakeProvider([self.price(date(2024, 1, 10))])
            first = update_security_prices(
                store=store,
                provider=initial,
                security=self.security,
                end_date=date(2024, 1, 10),
            )
            revised = FakeProvider([self.price(date(2024, 1, 10), "101"), self.price(date(2024, 1, 11), "102")])
            second = update_security_prices(
                store=store,
                provider=revised,
                security=self.security,
                end_date=date(2024, 1, 11),
                reconciliation_days=3,
            )

            self.assertEqual(first.status, DataQualityStatus.OK)
            self.assertEqual(second.status, DataQualityStatus.OK)
            self.assertEqual(revised.calls, [(date(2024, 1, 7), date(2024, 1, 11))])
            self.assertEqual([row.close for row in store.read_prices(market="US", year=2024)], [Decimal("101.0000000000"), Decimal("102.0000000000")])

    def test_provider_failure_leaves_existing_data_unchanged(self) -> None:
        with TemporaryDirectory() as temporary:
            store = ParquetStore(temporary)
            store.upsert_prices(market="US", rows=[self.price(date(2024, 1, 10))], pipeline_version="test")

            result = update_security_prices(
                store=store,
                provider=FakeProvider(error=TimeoutError("simulated timeout")),
                security=self.security,
                end_date=date(2024, 1, 11),
            )

            self.assertEqual(result.status, DataQualityStatus.FAILED)
            self.assertEqual(len(store.read_prices(market="US", year=2024)), 1)

    def test_event_ingestion_uses_an_independent_history_cursor(self) -> None:
        with TemporaryDirectory() as temporary:
            store = ParquetStore(temporary)
            store.upsert_prices(market="US", rows=[self.price(date(2024, 1, 10))], pipeline_version="test")
            provider = FakeProvider([self.price(date(2024, 1, 11))])

            update_security_prices(
                store=store,
                provider=provider,
                security=self.security,
                end_date=date(2024, 1, 11),
                start_floor=date(2000, 1, 1),
            )

            self.assertEqual(provider.calls[0][0], date(2024, 1, 3))
            self.assertEqual(provider.dividend_calls[0][0], date(2000, 1, 1))
