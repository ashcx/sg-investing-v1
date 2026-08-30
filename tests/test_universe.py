from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import TestCase

from sg_investing.models import AssetType, Security
from sg_investing.universe.catalog import load_catalog
from sg_investing.universe.sources import _security_id


class UniverseCatalogTests(TestCase):
    def test_irish_domiciled_etf_comparison_set_is_configured(self) -> None:
        catalog = load_catalog(Path("config/universe.yaml"))
        expected = {
            "CSPX.L": ("IE00B5BMR087", "0.0007"),
            "CNDX.L": ("IE00B53SZB19", "0.0030"),
            "IWDA.L": ("IE00B4L5Y983", "0.0020"),
            "EIMI.L": ("IE00BKM4GZ66", "0.0018"),
            "VWRA.L": ("IE00BK5BQT80", "0.0019"),
            "VUAA.L": ("IE00BFMXXD54", "0.0007"),
        }

        for ticker, (isin, expense_ratio) in expected.items():
            security = catalog.security_by_ticker(ticker)
            self.assertEqual(security.exchange, "LSE")
            self.assertEqual(security.market, "GB")
            self.assertEqual(security.domicile, "IE")
            self.assertEqual(security.isin, isin)
            self.assertEqual(security.distribution_policy.value, "accumulating")
            self.assertEqual(security.expense_ratio, Decimal(expense_ratio))

    def test_configured_vall_is_unambiguous_and_accumulating(self) -> None:
        catalog = load_catalog(Path("config/universe.yaml"))
        vall = catalog.security_by_ticker("VALL.SW")

        self.assertEqual(vall.isin, "IE000VAHT5T0")
        self.assertEqual(vall.exchange, "SIX")
        self.assertEqual(vall.currency, "USD")
        self.assertEqual(vall.distribution_policy, "accumulating")
        self.assertEqual(vall.expense_ratio, Decimal("0.0007"))

    def test_configured_security_ids_are_stable_across_reloads(self) -> None:
        first = load_catalog(Path("config/universe.yaml"))
        second = load_catalog(Path("config/universe.yaml"))

        self.assertEqual(
            [entry.security.security_id for entry in first.securities],
            [entry.security.security_id for entry in second.securities],
        )

    def test_merge_current_listings_keeps_existing_catalog_entries(self) -> None:
        catalog = load_catalog(Path("config/universe.yaml"))
        sgx_security = Security(
            ticker="S68.SI",
            exchange="SGX",
            market="SG",
            name="Singapore Exchange Limited",
            currency="SGD",
            asset_type=AssetType.EQUITY,
            timezone="Asia/Singapore",
        )

        updated = catalog.merge_current_listings(
            universe="sgx_active",
            source="test_listing_source",
            as_of=date(2026, 8, 30),
            listings=[sgx_security],
        )

        self.assertEqual(len(updated.securities), len(catalog.securities) + 1)
        self.assertEqual(updated.security_by_ticker("S68.SI").exchange, "SGX")
        self.assertEqual(updated.memberships()[-1].effective_from, date(2026, 8, 30))

    def test_imported_security_ids_are_repeatable(self) -> None:
        self.assertEqual(
            _security_id(exchange="US", ticker="brk-b"),
            _security_id(exchange="us", ticker="BRK-B"),
        )

    def test_merge_current_listings_retains_multiple_memberships_for_one_security(self) -> None:
        catalog = load_catalog(Path("config/universe.yaml"))
        qqq = catalog.security_by_ticker("QQQ")
        updated = catalog.merge_current_listings(
            universe="overlapping_test_universe",
            source="test_listing_source",
            as_of=date(2026, 8, 30),
            listings=[qqq],
        )

        self.assertEqual(updated.security_by_ticker("QQQ").security_id, qqq.security_id)
        self.assertEqual(len([entry for entry in updated.securities if entry.security.security_id == qqq.security_id]), 2)
        self.assertEqual(len(updated.memberships()), len(catalog.memberships()) + 1)
