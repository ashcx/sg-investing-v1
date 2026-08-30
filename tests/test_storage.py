from __future__ import annotations

from datetime import date
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest import TestCase

from sg_investing.data.storage import ParquetStore
from sg_investing.models import AssetType, DividendEvent, FxRate, PriceBar, Security


class ParquetStoreTests(TestCase):
    def setUp(self) -> None:
        self.security = Security(
            ticker="TEST",
            exchange="NYSE",
            market="US",
            name="Synthetic Security",
            currency="USD",
            asset_type=AssetType.EQUITY,
        )

    def price(self, trading_date: date, close: str) -> PriceBar:
        value = Decimal(close)
        return PriceBar(
            security_id=self.security.security_id,
            trading_date=trading_date,
            open=value,
            high=value,
            low=value,
            close=value,
            volume=1,
            currency="USD",
            exchange="NYSE",
            timezone="America/New_York",
            source="synthetic",
        )

    def test_upsert_is_partitioned_and_replaces_matching_observation(self) -> None:
        with TemporaryDirectory() as temporary:
            store = ParquetStore(temporary)
            manifest = store.upsert_prices(
                market="US",
                rows=[self.price(date(2024, 1, 2), "100")],
                pipeline_version="test",
            )[0]
            store.upsert_prices(
                market="US",
                rows=[self.price(date(2024, 1, 2), "101"), self.price(date(2024, 1, 3), "102")],
                pipeline_version="test",
            )

            stored = store.read_prices(market="US", year=2024)
            self.assertEqual(manifest.row_count, 1)
            self.assertEqual([row.close for row in stored], [Decimal("101.0000000000"), Decimal("102.0000000000")])

    def test_invalid_replacement_cannot_destroy_valid_partition(self) -> None:
        with TemporaryDirectory() as temporary:
            store = ParquetStore(temporary)
            original = self.price(date(2024, 1, 2), "100")
            store.upsert_prices(market="US", rows=[original], pipeline_version="test")
            invalid = PriceBar(
                security_id=self.security.security_id,
                trading_date=date(2024, 1, 3),
                open=Decimal("100"),
                high=Decimal("90"),
                low=Decimal("95"),
                close=Decimal("100"),
                volume=1,
                currency="USD",
                exchange="NYSE",
                timezone="America/New_York",
                source="synthetic",
            )

            with self.assertRaises(ValueError):
                store.upsert_prices(market="US", rows=[invalid], pipeline_version="test")

            stored = store.read_prices(market="US", year=2024)
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0].close, Decimal("100.0000000000"))

    def test_dividends_and_fx_are_deduplicated_by_their_canonical_keys(self) -> None:
        with TemporaryDirectory() as temporary:
            store = ParquetStore(temporary)
            dividend = DividendEvent(
                security_id=self.security.security_id,
                ex_date=date(2024, 6, 1),
                amount=Decimal("1.25"),
                currency="USD",
                source="synthetic",
            )
            rate = FxRate(
                rate_date=date(2024, 6, 1),
                base_currency="USD",
                rate_to_sgd=Decimal("1.35"),
                source="synthetic",
            )
            store.upsert_dividends([dividend])
            store.upsert_dividends([dividend])
            store.upsert_fx([rate])

            dividend_path = store.root / "dividends" / "year=2024.parquet"
            fx_path = store.root / "fx" / "pair=USD_SGD" / "year=2024.parquet"
            self.assertTrue(dividend_path.exists())
            self.assertTrue(fx_path.exists())
            self.assertEqual(store.read_dividends(year=2024), [dividend])
            self.assertEqual(store.read_fx(base_currency="USD", year=2024), [rate])
