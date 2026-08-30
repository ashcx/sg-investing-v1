from __future__ import annotations

from datetime import date
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest import TestCase

from sg_investing.analysis import analyze_security
from sg_investing.data.storage import ParquetStore
from sg_investing.models import AssetType, FxRate, PriceBar, Security


class EndToEndTests(TestCase):
    def test_parquet_to_analysis_json_contract(self) -> None:
        security = Security(
            ticker="TEST",
            exchange="NYSE",
            market="US",
            name="Synthetic Security",
            currency="USD",
            asset_type=AssetType.EQUITY,
        )
        rows = []
        for trading_date, close in ((date(2024, 1, 2), "100"), (date(2025, 1, 2), "120")):
            amount = Decimal(close)
            rows.append(
                PriceBar(
                    security_id=security.security_id,
                    trading_date=trading_date,
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
            )
        fx = [
            FxRate(rate_date=date(2024, 1, 2), base_currency="USD", rate_to_sgd=Decimal("1.30"), source="synthetic"),
            FxRate(rate_date=date(2025, 1, 2), base_currency="USD", rate_to_sgd=Decimal("1.40"), source="synthetic"),
        ]
        with TemporaryDirectory() as temporary:
            store = ParquetStore(temporary)
            store.upsert_prices(market="US", rows=rows, pipeline_version="test")
            result = analyze_security(
                security=security,
                prices=store.read_prices(market="US", year=2024) + store.read_prices(market="US", year=2025),
                fx_rates=fx,
                start_date=date(2024, 1, 1),
                end_date=date(2025, 1, 2),
                initial_sgd=Decimal("1300"),
            )

        self.assertEqual(result.investment["final_value_sgd"], Decimal("1680"))
        self.assertEqual(result.model_dump(mode="json")["security"]["ticker"], "TEST")
