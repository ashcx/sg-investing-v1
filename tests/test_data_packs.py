from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from sg_investing.data.packs import (
    METHODOLOGY_VERSION,
    STATUS_FULLY_SUPPORTED,
    STATUS_INCOMPLETE,
    STATUS_UNAVAILABLE,
    build_data_packs,
    classify_range,
    compute_data_snapshot_id,
    pack_path,
)
from sg_investing.data.storage import ParquetStore
from sg_investing.models import (
    AssetType,
    CorporateAction,
    CorporateActionType,
    DistributionPolicy,
    DividendEvent,
    FxRate,
    PriceBar,
    Security,
)
from sg_investing.universe.catalog import ConfiguredSecurity, UniverseCatalog, save_catalog


def _security(ticker: str, currency: str, market: str) -> Security:
    return Security(
        ticker=ticker,
        exchange="NYSE" if market == "US" else "SGX",
        market=market,
        name=f"Synthetic {ticker}",
        currency=currency,
        asset_type=AssetType.ETF,
        distribution_policy=DistributionPolicy.DISTRIBUTING,
    )


def _price(security: Security, trading_date: date, close: str) -> PriceBar:
    value = Decimal(close)
    return PriceBar(
        security_id=security.security_id,
        trading_date=trading_date,
        open=value,
        high=value,
        low=value,
        close=value,
        volume=100,
        currency=security.currency,
        exchange=security.exchange,
        timezone="America/New_York",
        source="synthetic",
    )


def _fx(rate_date: date, rate: str = "1.350000000000000") -> FxRate:
    return FxRate(
        rate_date=rate_date,
        base_currency="USD",
        rate_to_sgd=Decimal(rate),
        source="synthetic",
    )


def _dividend(security: Security, ex_date: date) -> DividendEvent:
    return DividendEvent(
        security_id=security.security_id,
        ex_date=ex_date,
        amount=Decimal("0.500000000000000"),
        currency=security.currency,
        pay_date=ex_date,
        dividend_type="regular",
        source="synthetic",
    )


class DataPacksTestCase(TestCase):
    """Shared synthetic store: two catalog securities plus one without data."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = ParquetStore(self.root / "data")
        self.usd = _security("TEST", "USD", "US")
        self.sgd = _security("SGDFUND", "SGD", "SG")
        self.ghost = _security("GHOST", "USD", "US")
        self._save_catalog()
        self.output = self.root / "frontend" / "data" / "packs"

    def _save_catalog(self) -> None:
        entries = [
            ConfiguredSecurity(
                universe="major_global_etfs",
                effective_from=date(1999, 1, 1),
                source="configured_seed",
                security=security,
            )
            for security in (self.usd, self.sgd, self.ghost)
        ]
        catalog = UniverseCatalog(history_start=date(2000, 1, 1), securities=entries)
        target = self.root / "data" / "universe" / "current_catalog.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        save_catalog(catalog, target)
        (target.parent / "summary.json").write_text(
            json.dumps({"as_of": "2026-08-30", "unique_securities": 3}), encoding="utf-8"
        )

    def _write_usd_prices(self) -> None:
        self.store.upsert_prices(
            market="US",
            rows=[
                _price(self.usd, date(2023, 1, 3), "100"),
                _price(self.usd, date(2023, 1, 4), "101"),
                _price(self.usd, date(2024, 1, 2), "110"),
            ],
            pipeline_version="test",
        )
        self.store.upsert_fx(
            rows=[
                _fx(date(2022, 12, 30)),
                _fx(date(2023, 1, 3), "1.340000000000000"),
                _fx(date(2023, 1, 4), "1.350000000000000"),
                _fx(date(2024, 1, 2), "1.360000000000000"),
            ]
        )

    def _build(self) -> dict:
        return build_data_packs(self.root, self.output)

    def _manifest(self) -> dict:
        return json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))

    def _pack(self, security: Security, year: int) -> dict:
        relative = pack_path(str(security.security_id), year)
        return json.loads((self.output / relative).read_text(encoding="utf-8"))

    def _entry(self, ticker: str) -> dict:
        return next(entry for entry in self._manifest()["securities"] if entry["ticker"] == ticker)


class DataPackBuildTests(DataPacksTestCase):
    def test_packs_are_partitioned_per_security_and_year(self) -> None:
        self._write_usd_prices()
        self.store.upsert_prices(
            market="SG",
            rows=[
                _price(self.sgd, date(2023, 6, 1), "2"),
                _price(self.sgd, date(2023, 6, 2), "2.1"),
            ],
            pipeline_version="test",
        )
        summary = self._build()

        self.assertEqual(summary["pack_count"], 3)
        usd_id = str(self.usd.security_id)
        sgd_id = str(self.sgd.security_id)
        for relative in (pack_path(usd_id, 2023), pack_path(usd_id, 2024), pack_path(sgd_id, 2023)):
            self.assertTrue((self.output / relative).exists(), relative)
        self.assertFalse((self.output / pack_path(usd_id, 2022)).exists())
        self.assertFalse((self.output / pack_path(str(self.ghost.security_id), 2023)).exists())

    def test_pack_carries_prices_fx_dividends_and_provenance(self) -> None:
        self._write_usd_prices()
        self.store.upsert_dividends([_dividend(self.usd, date(2023, 1, 3))])
        self.store.upsert_corporate_actions(
            [
                CorporateAction(
                    security_id=self.usd.security_id,
                    effective_date=date(2023, 1, 4),
                    action_type=CorporateActionType.SPLIT,
                    ratio=Decimal(2),
                    source="synthetic",
                )
            ]
        )
        self._build()

        payload = self._pack(self.usd, 2023)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["pack_type"], "security_year")
        self.assertEqual(payload["methodology_version"], METHODOLOGY_VERSION)
        self.assertTrue(payload["data_snapshot_id"].startswith("sha256-"))
        self.assertTrue(payload["catalog_version"].startswith("sha256-"))
        self.assertEqual(payload["catalog_as_of"], "2026-08-30")
        self.assertEqual(payload["coverage"]["row_count"], 2)
        self.assertEqual(payload["coverage"]["native_currency"], "USD")
        self.assertEqual(payload["coverage"]["first_date"], "2023-01-03")
        self.assertEqual(payload["coverage"]["last_date"], "2023-01-04")
        self.assertEqual(payload["provenance"]["source"], "synthetic")
        self.assertEqual(payload["provenance"]["pipeline_version"], "test")
        self.assertEqual(payload["provenance"]["partition_manifest"], "manifests/prices/market=US/year=2023.json")
        self.assertEqual(payload["prices"]["dates"], ["2023-01-03", "2023-01-04"])
        self.assertEqual(payload["prices"]["close"], ["100", "101"])
        self.assertEqual(payload["fx"]["dates"][:2], ["2022-12-30", "2023-01-03"])
        self.assertEqual(payload["fx"]["rates"][0], "1.35")
        self.assertEqual(payload["dividends"][0]["ex_date"], "2023-01-03")
        self.assertEqual(payload["dividends"][0]["amount"], "0.5")
        self.assertEqual(payload["corporate_actions"][0]["ratio"], "2")
        self.assertEqual(payload["security"]["ticker"], "TEST")

    def test_sgd_security_needs_no_fx_and_stays_fully_supported(self) -> None:
        self.store.upsert_prices(
            market="SG", rows=[_price(self.sgd, date(2023, 6, 1), "2")], pipeline_version="test"
        )
        self._build()

        entry = self._entry("SGDFUND")
        self.assertEqual(entry["native_currency"], "SGD")
        self.assertEqual(entry["years"]["2023"]["status"], STATUS_FULLY_SUPPORTED)
        self.assertIsNone(self._pack(self.sgd, 2023)["fx"])


class ManifestTests(DataPacksTestCase):
    def test_manifest_answers_support_for_every_catalog_security(self) -> None:
        self._write_usd_prices()
        self.store.upsert_prices(
            market="SG", rows=[_price(self.sgd, date(2023, 6, 1), "2")], pipeline_version="test"
        )
        summary = self._build()
        manifest = self._manifest()

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["manifest_version"], 1)
        self.assertEqual(manifest["methodology_version"], METHODOLOGY_VERSION)
        self.assertEqual(manifest["data_snapshot_id"], summary["data_snapshot_id"])
        self.assertEqual(manifest["data_snapshot_id"], compute_data_snapshot_id(self.root / "data"))
        self.assertTrue(manifest["catalog_version"].startswith("sha256-"))
        self.assertEqual(manifest["catalog_as_of"], "2026-08-30")
        self.assertEqual(manifest["history_start"], "2000-01-01")
        self.assertEqual(manifest["source"], "synthetic")
        self.assertEqual(
            manifest["support"]["counts"],
            {STATUS_FULLY_SUPPORTED: 2, STATUS_INCOMPLETE: 0, STATUS_UNAVAILABLE: 1},
        )
        ghost = self._entry("GHOST")
        self.assertEqual(ghost["status"], STATUS_UNAVAILABLE)
        self.assertEqual(ghost["years"], {})
        test_entry = self._entry("TEST")
        self.assertEqual(test_entry["row_count"], 3)
        self.assertEqual(test_entry["first_date"], "2023-01-03")
        self.assertEqual(test_entry["last_date"], "2024-01-02")
        self.assertEqual(
            test_entry["years"]["2024"]["pack"],
            pack_path(str(self.usd.security_id), 2024),
        )

    def test_manifest_warnings_cover_catalog_and_dividend_gaps(self) -> None:
        self._write_usd_prices()
        self.store.upsert_prices(
            market="SG", rows=[_price(self.sgd, date(2023, 6, 1), "2")], pipeline_version="test"
        )
        self._build()

        joined = " ".join(self._manifest()["warnings"])
        self.assertIn("1 catalog securities have no price data", joined)
        flagged = {
            entry["ticker"]
            for entry in self._manifest()["securities"]
            if entry["status"] != STATUS_UNAVAILABLE
            and "no dividend events recorded for a distributing security" in entry["warnings"]
        }
        self.assertEqual(flagged, {"TEST", "SGDFUND"})


class SupportClassificationTests(DataPacksTestCase):
    def test_missing_fx_history_makes_year_incomplete(self) -> None:
        self.store.upsert_prices(
            market="US",
            rows=[_price(self.usd, date(2023, 1, 3), "100")],
            pipeline_version="test",
        )
        # FX only exists from 2024: the 2023 price date is unresolvable.
        self.store.upsert_fx(rows=[_fx(date(2024, 1, 2))])
        self._build()

        entry = self._entry("TEST")
        self.assertEqual(entry["status"], STATUS_INCOMPLETE)
        year = entry["years"]["2023"]
        self.assertEqual(year["status"], STATUS_INCOMPLETE)
        self.assertEqual(year["missing_fx_dates"], 1)
        self.assertIn("no USD/SGD rate", year["warnings"][0])
        verdict = classify_range(entry, "2023-01-01", "2023-12-31")
        self.assertEqual(verdict["status"], STATUS_INCOMPLETE)

    def test_calendar_gap_flags_incomplete_but_calendar_author_stays_supported(self) -> None:
        self._write_usd_prices()
        gapped = _security("GAPPED", "SGD", "US")
        self.store.upsert_prices(
            market="US",
            rows=[_price(gapped, date(2023, 1, 3), "50"), _price(gapped, date(2023, 1, 5), "51")],
            pipeline_version="test",
        )
        catalog_target = self.root / "data" / "universe" / "current_catalog.json"
        existing = json.loads(catalog_target.read_text(encoding="utf-8"))
        existing["securities"].append(
            {
                "universe": "major_global_etfs",
                "effective_from": "1999-01-01",
                "source": "configured_seed",
                "security": gapped.model_dump(mode="json"),
            }
        )
        catalog_target.write_text(json.dumps(existing), encoding="utf-8")
        self._build()

        by_ticker = {entry["ticker"]: entry for entry in self._manifest()["securities"]}
        self.assertEqual(
            by_ticker["TEST"]["years"]["2023"]["status"], STATUS_FULLY_SUPPORTED
        )
        gapped_entry = by_ticker["GAPPED"]
        self.assertEqual(gapped_entry["status"], STATUS_INCOMPLETE)
        year = gapped_entry["years"]["2023"]
        self.assertEqual(year["missing_calendar_dates"], 1)
        self.assertIn("market-calendar dates lack price bars", year["warnings"][0])

    def test_unavailable_security_and_out_of_range_queries(self) -> None:
        self._write_usd_prices()
        self._build()

        ghost = self._entry("GHOST")
        self.assertEqual(ghost["status"], STATUS_UNAVAILABLE)
        verdict = classify_range(ghost, "2020-01-01", "2024-01-01")
        self.assertEqual(verdict["status"], STATUS_UNAVAILABLE)
        self.assertEqual(verdict["reasons"], ["security has no price data in this snapshot"])
        test_entry = self._entry("TEST")
        verdict = classify_range(test_entry, "2010-01-01", "2015-12-31")
        self.assertEqual(verdict["status"], STATUS_UNAVAILABLE)
        self.assertIn("does not overlap", verdict["reasons"][0])

    def test_range_classification_follows_frozen_rules(self) -> None:
        self._write_usd_prices()
        self._build()

        entry = self._entry("TEST")
        self.assertEqual(entry["status"], STATUS_FULLY_SUPPORTED)
        verdict = classify_range(entry, "2023-01-01", "2024-12-31")
        self.assertEqual(verdict["status"], STATUS_FULLY_SUPPORTED)
        self.assertEqual(
            verdict["packs"],
            [
                pack_path(str(self.usd.security_id), 2023),
                pack_path(str(self.usd.security_id), 2024),
            ],
        )
        # Edges outside the price window are tolerated and surfaced as reasons.
        verdict = classify_range(entry, "2022-06-01", "2025-06-30")
        self.assertEqual(verdict["status"], STATUS_FULLY_SUPPORTED)
        self.assertEqual(len(verdict["reasons"]), 2)

    def test_range_with_mid_window_hole_is_incomplete(self) -> None:
        self.store.upsert_prices(
            market="SG",
            rows=[
                _price(self.sgd, date(2023, 6, 1), "2"),
                _price(self.sgd, date(2025, 6, 1), "3"),
            ],
            pipeline_version="test",
        )
        self._build()

        entry = self._entry("SGDFUND")
        self.assertEqual(entry["status"], STATUS_INCOMPLETE)
        spanning = classify_range(entry, "2023-01-01", "2025-12-31")
        self.assertEqual(spanning["status"], STATUS_INCOMPLETE)
        self.assertEqual(spanning["years"]["2024"], STATUS_UNAVAILABLE)
        inside_hole = classify_range(entry, "2024-01-01", "2024-12-31")
        self.assertEqual(inside_hole["status"], STATUS_UNAVAILABLE)


class MergeAndVersioningTests(DataPacksTestCase):
    def test_rebuild_from_unchanged_store_reproduces_snapshot_id(self) -> None:
        self._write_usd_prices()
        first = self._build()
        manifest = self._manifest()
        pack_bytes = (self.output / pack_path(str(self.usd.security_id), 2023)).read_bytes()

        second = self._build()

        self.assertEqual(first["data_snapshot_id"], second["data_snapshot_id"])
        self.assertEqual(self._manifest()["data_snapshot_id"], manifest["data_snapshot_id"])
        self.assertEqual(
            self._manifest()["summary"]["pack_count"], manifest["summary"]["pack_count"]
        )
        self.assertEqual(
            (self.output / pack_path(str(self.usd.security_id), 2023)).read_bytes(), pack_bytes
        )

    def test_new_store_data_produces_new_snapshot_and_merged_packs(self) -> None:
        self._write_usd_prices()
        first = self._build()

        self.store.upsert_prices(
            market="US",
            rows=[
                _price(self.usd, date(2023, 1, 4), "999"),  # replaces the close
                _price(self.usd, date(2025, 1, 2), "120"),  # extends coverage
            ],
            pipeline_version="test",
        )
        second = self._build()

        self.assertNotEqual(first["data_snapshot_id"], second["data_snapshot_id"])
        self.assertEqual(self._manifest()["data_snapshot_id"], second["data_snapshot_id"])
        self.assertEqual(second["pack_count"], 3)
        entry = self._entry("TEST")
        self.assertIn("2025", entry["years"])
        self.assertEqual(entry["last_year"], 2025)
        merged = self._pack(self.usd, 2023)
        self.assertEqual(merged["prices"]["close"], ["100", "999"])
        self.assertEqual(merged["coverage"]["row_count"], 2)
