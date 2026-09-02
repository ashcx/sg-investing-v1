"""Synthetic-fixture tests for the incremental updater (Sprint 7.5, Track B).

Covers scripts/update_incremental.py (tail fetch, gap backfill, late-dividend
reconciliation, dry-run payload, incremental snapshot ids, scoped pack
rebuilds) and the scoped merge mode of scripts/build_data_packs.py (full-run
behavior unchanged, untouched securities preserved byte-for-byte). Providers
are fakes; no test touches the network (AGENTS.md: no live calls in the
normal suite).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import uuid as uuid_module
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.update_incremental import (
    RECONCILIATION_DAYS_DEFAULT,
    incremental_snapshot_id,
    parse_since,
    run_incremental_update,
)
from sg_investing.data.packs import build_data_packs, compute_data_snapshot_id
from sg_investing.data.storage import ParquetStore
from sg_investing.models import (
    AssetType,
    DistributionPolicy,
    DividendEvent,
    FxRate,
    PriceBar,
    Security,
)
from sg_investing.universe.catalog import ConfiguredSecurity, UniverseCatalog, save_catalog

_REPO = Path(__file__).resolve().parents[1]
TEST_ID = "11111111-1111-1111-1111-111111111111"
FUND_ID = "22222222-2222-2222-2222-222222222222"
RETRIEVED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
END = date(2026, 9, 1)
# 2026-08-31 (last stored price date) minus the default reconciliation window.
AUTO_WINDOW_START = date(2026, 7, 17)

MARCH_DATES = [date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4), date(2026, 3, 5), date(2026, 3, 6)]
AUGUST_DATES = [date(2026, 8, 28), date(2026, 8, 31)]
SEPTEMBER_DATES = [date(2026, 9, 1)]


def _security(
    security_id: str,
    ticker: str,
    currency: str,
    market: str,
    *,
    policy: DistributionPolicy = DistributionPolicy.DISTRIBUTING,
) -> Security:
    return Security(
        security_id=uuid_module.UUID(security_id),
        ticker=ticker,
        exchange="NYSE" if market == "US" else "SGX",
        market=market,
        name=f"Synthetic {ticker}",
        currency=currency,
        asset_type=AssetType.ETF,
        distribution_policy=policy,
        timezone="America/New_York" if market == "US" else "Asia/Singapore",
    )


def _price(security: Security, trading_date: date, close: str = "100") -> PriceBar:
    value = Decimal(close)
    return PriceBar(
        security_id=security.security_id,
        trading_date=trading_date,
        open=value,
        high=value,
        low=value,
        close=value,
        volume=1000,
        currency=security.currency,
        exchange=security.exchange,
        timezone=security.timezone,
        source="synthetic",
        retrieved_at=RETRIEVED_AT,
    )


def _fx(rate_date: date, rate: str = "1.35") -> FxRate:
    return FxRate(rate_date=rate_date, base_currency="USD", rate_to_sgd=Decimal(rate), source="synthetic")


def _dividend(security: Security, ex_date: date, amount: str = "0.50") -> DividendEvent:
    return DividendEvent(
        security_id=security.security_id,
        ex_date=ex_date,
        amount=Decimal(amount),
        currency=security.currency,
        source="synthetic",
        retrieved_at=RETRIEVED_AT,
        ingested_at=RETRIEVED_AT,
    )


class RecordingProvider:
    """Fake MarketDataProvider: filters canned rows, records every call."""

    name = "fake"

    def __init__(self, *, prices=(), dividends=(), actions=(), fx=()):
        self._prices = list(prices)
        self._dividends = list(dividends)
        self._actions = list(actions)
        self._fx = list(fx)
        self.calls: list[str] = []

    def get_prices(self, security: Security, start_date: date, end_date: date) -> list[PriceBar]:
        self.calls.append(f"prices:{security.ticker}:{start_date}:{end_date}")
        return [
            row
            for row in self._prices
            if row.security_id == security.security_id and start_date <= row.trading_date <= end_date
        ]

    def get_dividends(self, security: Security, start_date: date, end_date: date) -> list[DividendEvent]:
        self.calls.append(f"dividends:{security.ticker}:{start_date}:{end_date}")
        return [
            row
            for row in self._dividends
            if row.security_id == security.security_id and start_date <= row.ex_date <= end_date
        ]

    def get_corporate_actions(self, security: Security, start_date: date, end_date: date):
        self.calls.append(f"actions:{security.ticker}:{start_date}:{end_date}")
        return [
            row
            for row in self._actions
            if row.security_id == security.security_id
            and start_date <= row.effective_date <= end_date
        ]

    def get_fx_rates(self, base_currency: str, start_date: date, end_date: date) -> list[FxRate]:
        self.calls.append(f"fx:{base_currency}:{start_date}:{end_date}")
        return [
            row
            for row in self._fx
            if row.base_currency == base_currency.upper() and start_date <= row.rate_date <= end_date
        ]


class IncrementalUpdaterCase(TestCase):
    """Temp repo with catalog, seeded store and a scripts/ mirror for packs."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "config").mkdir()
        (self.root / "config" / "settings.yaml").write_text(
            "data_directory: data\npipeline_version: test-0.7.5\nprice_backfill_workers: 1\n",
            encoding="utf-8",
        )
        scripts = self.root / "scripts"
        scripts.mkdir()
        shutil.copyfile(_REPO / "scripts" / "build_data_packs.py", scripts / "build_data_packs.py")
        self.usd = _security(TEST_ID, "TEST", "USD", "US")
        self.sgd = _security(
            FUND_ID, "SGDFUND", "SGD", "SG", policy=DistributionPolicy.ACCUMULATING
        )
        entries = [
            ConfiguredSecurity(
                universe="major_global_etfs",
                effective_from=date(1999, 1, 1),
                source="configured_seed",
                security=security,
            )
            for security in (self.usd, self.sgd)
        ]
        catalog_target = self.root / "data" / "universe" / "current_catalog.json"
        catalog_target.parent.mkdir(parents=True, exist_ok=True)
        save_catalog(UniverseCatalog(history_start=date(2020, 1, 1), securities=entries), catalog_target)
        (catalog_target.parent / "summary.json").write_text(
            json.dumps({"as_of": "2026-08-30", "unique_securities": 2}), encoding="utf-8"
        )
        self.store = ParquetStore(self.root / "data")
        self._seed_store()
        self.output = self.root / "frontend" / "data" / "packs"

    def _seed_store(self) -> None:
        """TEST priced in March and late August; FX and one dividend stored."""

        self.store.upsert_prices(
            market="US",
            rows=[_price(self.usd, date(2025, 12, 1)), _price(self.usd, MARCH_DATES[0])]
            + [_price(self.usd, day) for day in MARCH_DATES[1:2]]
            + [_price(self.usd, day) for day in AUGUST_DATES],
            pipeline_version="seed",
        )
        self.store.upsert_prices(market="SG", rows=[_price(self.sgd, date(2026, 8, 31))], pipeline_version="seed")
        self.store.upsert_fx(
            rows=[_fx(day) for day in [date(2025, 11, 25), date(2025, 12, 1), *MARCH_DATES, *AUGUST_DATES]]
        )
        self.store.upsert_dividends([_dividend(self.usd, date(2026, 8, 10))])

    def _provider(self, **kwargs) -> RecordingProvider:
        defaults = {
            "prices": [_price(self.usd, day) for day in [*MARCH_DATES, *AUGUST_DATES]]
            + [_price(self.sgd, date(2026, 8, 31))]
            + [_price(self.usd, day, "101") for day in SEPTEMBER_DATES],
            "dividends": [_dividend(self.usd, date(2026, 8, 10))],
            "actions": [],
            "fx": [_fx(day) for day in [*MARCH_DATES, *AUGUST_DATES, *SEPTEMBER_DATES]],
        }
        defaults.update(kwargs)
        return RecordingProvider(**defaults)

    def _run(self, provider: RecordingProvider, **kwargs) -> dict:
        kwargs.setdefault("end_date", END)
        kwargs.setdefault("build_packs", False)
        return run_incremental_update(self.root, provider=provider, **kwargs)

    def _store_hash(self) -> str:
        return compute_data_snapshot_id(self.root / "data")

    def _manifest(self) -> dict:
        return json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))

    def _entry(self, manifest: dict, security_id: str) -> dict:
        return next(entry for entry in manifest["securities"] if entry["security_id"] == security_id)

    def _pack_bytes(self, security_id: str, year: int) -> bytes:
        return (self.output / f"security={security_id}/year={year}.json").read_bytes()


class IncrementalSnapshotIdTests(TestCase):
    def test_empty_change_set_keeps_base_id(self) -> None:
        self.assertEqual(incremental_snapshot_id("sha256-abc", []), "sha256-abc")

    def test_id_is_deterministic_and_order_independent(self) -> None:
        keys = ["price:a:2026-09-01", "fx:new:2026-09-01:USD", "dividends:a:2026-08-10:0.5"]
        first = incremental_snapshot_id("base", keys)
        self.assertEqual(first, incremental_snapshot_id("base", list(reversed(keys))))
        self.assertTrue(first.startswith("incr-"))
        self.assertEqual(len(first), len("incr-") + 32)

    def test_different_base_or_change_set_changes_id(self) -> None:
        keys = ["price:a:2026-09-01"]
        self.assertNotEqual(incremental_snapshot_id("base", keys), incremental_snapshot_id("other", keys))
        self.assertNotEqual(incremental_snapshot_id("base", keys), incremental_snapshot_id("base", keys + ["price:a:2026-09-02"]))

    def test_parse_since(self) -> None:
        self.assertIsNone(parse_since("auto"))
        self.assertEqual(parse_since("2026-03-01"), date(2026, 3, 1))
        with self.assertRaises(ValueError):
            parse_since("yesterday")


class DryRunTests(IncrementalUpdaterCase):
    def test_dry_run_prints_windows_without_network_or_writes(self) -> None:
        provider = self._provider()
        before_hash = self._store_hash()

        summary = self._run(provider, since="auto", dry_run=True, build_packs=True)

        self.assertEqual(provider.calls, [])
        self.assertEqual(self._store_hash(), before_hash)
        self.assertFalse((self.root / "data" / "update_summary.json").exists())
        self.assertEqual(summary["mode"], "dry-run")
        self.assertIn("Nothing was fetched", summary["note"])
        self.assertEqual(summary["since"], "auto")
        self.assertEqual(summary["reconciliation_days"], RECONCILIATION_DAYS_DEFAULT)
        self.assertEqual(summary["securities_selected_count"], 2)
        self.assertEqual(summary["full_history_fetch_count"], 0)

        plan = summary["securities"][0]
        self.assertEqual(plan["ticker"], "TEST")
        self.assertEqual(plan["last_stored_price_date"], "2026-08-31")
        self.assertEqual(plan["price_fetch_start"], AUTO_WINDOW_START.isoformat())
        self.assertEqual(plan["price_fetch_end"], END.isoformat())
        self.assertEqual(plan["fetch_years"], [2026])
        self.assertEqual(
            plan["endpoint"],
            f"yfinance:TEST:history(start={AUTO_WINDOW_START.isoformat()}, end=2026-09-02)",
        )
        self.assertTrue(plan["would_reconcile_dividends"])
        self.assertTrue(plan["would_reconcile_corporate_actions"])

        fx_plan = next(item for item in summary["fx"] if item["base_currency"] == "USD")
        self.assertEqual(fx_plan["last_stored_date"], "2026-08-31")
        self.assertEqual(fx_plan["start"], AUTO_WINDOW_START.isoformat())
        self.assertIn("USDSGD=X", fx_plan["endpoint"])
        self.assertFalse(any(item["base_currency"] == "SGD" for item in summary["fx"]))

        self.assertIn("market=US/year=2026.parquet", " ".join(summary["would_write_paths"]))
        self.assertIn("update_summary.json", " ".join(summary["would_write_paths"]))
        command = summary["pack_rebuild"]["command"]
        self.assertIn("--security", command)
        self.assertIn(TEST_ID, command)

    def test_dry_run_since_widens_window_back(self) -> None:
        summary = self._run(self._provider(), since="2026-03-01", dry_run=True)
        plan = summary["securities"][0]
        self.assertEqual(plan["price_fetch_start"], "2026-03-01")
        self.assertEqual(plan["fetch_years"], [2026])

    def test_dry_run_security_filter_and_unknown_selector(self) -> None:
        summary = self._run(self._provider(), since="auto", dry_run=True, securities=["TEST"])
        self.assertEqual([item["ticker"] for item in summary["securities"]], ["TEST"])
        with self.assertRaises(ValueError):
            self._run(self._provider(), since="auto", dry_run=True, securities=["NOPE"])


class TailFetchTests(IncrementalUpdaterCase):
    def test_tail_fetch_appends_new_dates_and_chains_snapshot_id(self) -> None:
        provider = self._provider()
        pre_run_hash = self._store_hash()

        first = self._run(provider, since="auto")

        stored = self.store.read_prices(market="US", year=2026)
        dates = {row.trading_date for row in stored if row.security_id == self.usd.security_id}
        self.assertTrue(set(AUGUST_DATES + SEPTEMBER_DATES) <= dates)
        self.assertTrue(set(MARCH_DATES[:2]) <= dates)
        self.assertEqual(first["price_rows_fetched"], 4)
        self.assertEqual(first["price_dates_new"], 1)
        self.assertEqual(first["price_dates_restated"], 0)
        self.assertEqual(first["fx_rows_new_or_restated"], 1)
        self.assertEqual(first["changed_securities"], [TEST_ID])
        self.assertEqual(first["changed_years"], {"2026": [TEST_ID]})
        self.assertTrue(first["incremental_snapshot_id"].startswith("incr-"))
        self.assertEqual(first["base_data_snapshot_id"], pre_run_hash)
        self.assertFalse(first["store_content_hash_unchanged"])
        self.assertEqual(
            sorted(result["ticker"] for result in first["results"]),
            ["SGDFUND", "TEST"],
        )
        self.assertEqual(first["failed"], 0)

        second = self._run(self._provider(), since="auto")

        # Re-running an applied update fetches the same tail, registers no
        # change, keeps the incremental id and skips the pack rebuild.
        self.assertEqual(second["change_set"]["count"], 0)
        self.assertEqual(second["price_dates_new"], 0)
        self.assertEqual(second["changed_securities"], [])
        self.assertEqual(second["incremental_snapshot_id"], first["incremental_snapshot_id"])
        self.assertEqual(second["base_data_snapshot_id"], first["incremental_snapshot_id"])
        self.assertIsNone(second["packs"])


class GapBackfillTests(IncrementalUpdaterCase):
    def test_since_backfills_mid_range_gap_older_than_the_window(self) -> None:
        provider = self._provider(
            prices=[_price(self.usd, day) for day in [*MARCH_DATES, *AUGUST_DATES]]
            + [_price(self.sgd, date(2026, 8, 31))],
            fx=[_fx(day) for day in [*MARCH_DATES, *AUGUST_DATES]],
        )
        gap_dates = MARCH_DATES[2:]

        summary = self._run(provider, since="2026-03-01")

        stored = {row.trading_date for row in self.store.read_prices(market="US", year=2026)}
        self.assertTrue(set(gap_dates) <= stored)
        self.assertEqual(summary["price_dates_new"], 3)
        self.assertEqual(summary["price_dates_restated"], 0)
        self.assertEqual(summary["fx_rows_new_or_restated"], 0)
        self.assertEqual(summary["changed_securities"], [TEST_ID])
        self.assertEqual(summary["changed_years"], {"2026": [TEST_ID]})
        self.assertTrue(summary["incremental_snapshot_id"].startswith("incr-"))

        # The dividend sweep widens with --since: once a coverage report
        # exists, a second --since run queries dividends back to the gap
        # start, not just the default trailing window.
        second = self._run(provider, since="2026-03-01")
        dividend_start = next(
            result["start_date"] for result in second["dividend_updates"] if result["ticker"] == "TEST"
        )
        self.assertLessEqual(dividend_start, "2026-03-01")


class LateDividendReconciliationTests(IncrementalUpdaterCase):
    def test_restated_dividend_registers_change_and_touches_pack(self) -> None:
        provider = self._provider(
            prices=[_price(self.usd, day) for day in [*MARCH_DATES, *AUGUST_DATES]]
            + [_price(self.sgd, date(2026, 8, 31))],
            fx=[_fx(day) for day in [*MARCH_DATES, *AUGUST_DATES]],
            dividends=[_dividend(self.usd, date(2026, 8, 10), "0.55")],
        )

        summary = self._run(provider, since="auto")

        self.assertEqual(summary["dividend_events_new_or_restated"], 1)
        self.assertEqual(summary["dividend_events_restated"], 1)
        self.assertEqual(summary["price_dates_new"], 0)
        self.assertEqual(summary["fx_rows_new_or_restated"], 0)
        # Regression: a dividend-only change must still map to (security,
        # year) pack partitions so the affected pack is rebuilt.
        self.assertEqual(summary["changed_securities"], [TEST_ID])
        self.assertEqual(summary["changed_years"], {"2026": [TEST_ID]})
        amounts = {
            row.amount
            for row in self.store.read_dividends(year=2026)
            if row.security_id == self.usd.security_id
        }
        self.assertEqual(amounts, {Decimal("0.55")})

    def test_new_late_dividend_counts_as_new(self) -> None:
        provider = self._provider(
            prices=[_price(self.usd, day) for day in [*MARCH_DATES, *AUGUST_DATES]]
            + [_price(self.sgd, date(2026, 8, 31))],
            fx=[_fx(day) for day in [*MARCH_DATES, *AUGUST_DATES]],
            dividends=[_dividend(self.usd, date(2026, 8, 10)), _dividend(self.usd, date(2026, 8, 20), "0.30")],
        )

        summary = self._run(provider, since="auto")

        self.assertEqual(summary["dividend_events_new_or_restated"], 1)
        self.assertEqual(summary["dividend_events_restated"], 0)
        self.assertEqual(summary["changed_years"], {"2026": [TEST_ID]})
        self.assertEqual(summary["dividends"]["summary"]["dividend_event_rows"], 2)


class FxTailTests(IncrementalUpdaterCase):
    def test_new_fx_rate_inside_existing_coverage_touches_packs(self) -> None:
        # 2026-08-27 is missing from the FX store while prices already exist
        # through 2026-08-31: the gap-fill rate must invalidate the pack even
        # though no price changed. The tail rate 2026-09-01 lies beyond the
        # stored price coverage and must not add touches on its own.
        provider = self._provider(
            prices=[_price(self.usd, day) for day in [*MARCH_DATES, *AUGUST_DATES]]
            + [_price(self.sgd, date(2026, 8, 31))],
            fx=[_fx(date(2026, 8, 27), "1.34"), *[_fx(day) for day in AUGUST_DATES]],
        )

        summary = self._run(provider, since="auto")

        self.assertEqual(summary["price_dates_new"], 0)
        self.assertEqual(summary["fx_rows_new_or_restated"], 1)
        self.assertEqual(summary["changed_securities"], [TEST_ID])
        self.assertEqual(summary["changed_years"], {"2026": [TEST_ID]})


class ScopedPackMergeTests(IncrementalUpdaterCase):
    """Scoped build_data_packs merge: full run unchanged, merge preserves others."""

    def _build_full(self) -> dict:
        return build_data_packs(self.root, self.output)

    def _run_builder(self, *flags: str) -> dict:
        completed = subprocess.run(
            [sys.executable, str(_REPO / "scripts" / "build_data_packs.py"), "--root", str(self.root), *flags],
            capture_output=True,
            text=True,
            check=True,
            timeout=180,
        )
        return json.loads(completed.stdout)

    def _mutate_store(self) -> None:
        self.store.upsert_prices(
            market="US",
            rows=[_price(self.usd, date(2026, 9, 1), "101")],
            pipeline_version="incremental",
        )

    def test_full_build_answers_for_the_whole_universe(self) -> None:
        summary = self._build_full()
        manifest = self._manifest()

        self.assertEqual(summary["pack_count"], 3)
        self.assertEqual(manifest["scope"], {"security_ids": None, "markets": None})
        self.assertNotIn("incremental", manifest)
        self.assertEqual(
            manifest["support"]["counts"],
            {"fully_supported": 2, "incomplete": 0, "unavailable": 0},
        )

    def test_scoped_merge_replaces_touched_and_preserves_others(self) -> None:
        full = self._build_full()
        full_manifest = self._manifest()
        fund_pack = self._pack_bytes(FUND_ID, 2026)
        usd_2025_pack = self._pack_bytes(TEST_ID, 2025)
        self._mutate_store()
        new_hash = self._store_hash()

        summary = self._run_builder("--security", TEST_ID, "--years", "2026")
        manifest = self._manifest()

        self.assertEqual(summary["merge"]["mode"], "merge")
        self.assertEqual(summary["merge"]["replaced_packs"], 1)
        self.assertEqual(summary["merge"]["updated_entries"], 1)
        self.assertEqual(summary["merge"]["base_data_snapshot_id"], full["data_snapshot_id"])
        # Untouched securities: pack file byte-for-byte and manifest entry
        # preserved exactly.
        self.assertEqual(self._pack_bytes(FUND_ID, 2026), fund_pack)
        self.assertEqual(self._entry(manifest, FUND_ID), self._entry(full_manifest, FUND_ID))
        # Years outside the scope keep their previous pack files too.
        self.assertEqual(self._pack_bytes(TEST_ID, 2025), usd_2025_pack)
        # Touched pack is rebuilt from the new store and reclassified.
        pack = json.loads(self._pack_bytes(TEST_ID, 2026))
        self.assertEqual(pack["data_snapshot_id"], new_hash)
        self.assertEqual(
            pack["prices"]["dates"],
            ["2026-03-02", "2026-03-03", "2026-08-28", "2026-08-31", "2026-09-01"],
        )
        entry = self._entry(manifest, TEST_ID)
        self.assertEqual(entry["last_date"], "2026-09-01")
        self.assertEqual(entry["row_count"], 6)
        # The merged manifest answers for the union with recomputed totals.
        self.assertEqual(manifest["data_snapshot_id"], new_hash)
        self.assertEqual(manifest["scope"], full_manifest["scope"])
        self.assertEqual(manifest["summary"]["securities"], 2)
        self.assertEqual(manifest["summary"]["pack_count"], 3)
        self.assertEqual(
            manifest["support"]["counts"],
            {"fully_supported": 2, "incomplete": 0, "unavailable": 0},
        )
        self.assertEqual(
            manifest["incremental"]["scope"],
            {"security_ids": [TEST_ID], "markets": None, "years": [2026]},
        )

    def test_second_scoped_merge_preserves_previous_merge(self) -> None:
        self._build_full()
        self._mutate_store()
        self._run_builder("--security", TEST_ID, "--years", "2026")
        merged = self._manifest()
        fund_pack = self._pack_bytes(FUND_ID, 2026)

        self._run_builder("--security", FUND_ID, "--years", "2026")
        manifest = self._manifest()

        self.assertEqual(self._entry(manifest, TEST_ID), self._entry(merged, TEST_ID))
        self.assertNotEqual(self._pack_bytes(FUND_ID, 2026), fund_pack)
        self.assertEqual(manifest["incremental"]["scope"]["security_ids"], [FUND_ID])

    def test_scoped_build_without_previous_manifest_is_filtered(self) -> None:
        summary = self._run_builder("--security", TEST_ID, "--years", "2026")
        manifest = self._manifest()

        self.assertEqual(summary["securities"], 1)
        self.assertEqual([entry["security_id"] for entry in manifest["securities"]], [TEST_ID])
        self.assertEqual(
            manifest["scope"],
            {"security_ids": [TEST_ID], "markets": None, "years": [2026]},
        )
        self.assertIsNone(manifest["incremental"]["base_data_snapshot_id"])

    def test_full_rebuild_after_merge_resets_directory_and_manifest(self) -> None:
        self._build_full()
        self._mutate_store()
        self._run_builder("--security", TEST_ID, "--years", "2026")
        orphan = self.output / "orphan.json"
        orphan.write_text("{}", encoding="utf-8")

        self._build_full()
        manifest = self._manifest()

        self.assertFalse(orphan.exists())
        self.assertNotIn("incremental", manifest)
        self.assertEqual(manifest["scope"], {"security_ids": None, "markets": None})
        self.assertEqual(manifest["data_snapshot_id"], self._store_hash())
        entry = self._entry(manifest, TEST_ID)
        self.assertEqual(entry["last_date"], "2026-09-01")


class IncrementalEndToEndPackTests(IncrementalUpdaterCase):
    def test_incremental_run_rebuilds_only_touched_packs(self) -> None:
        build_data_packs(self.root, self.output)
        manifest_before = self._manifest()
        fund_pack = self._pack_bytes(FUND_ID, 2026)
        provider = self._provider()

        summary = self._run(provider, since="auto", build_packs=True)

        self.assertIsInstance(summary["packs"], dict)
        self.assertNotIn("error", summary["packs"])
        self.assertEqual(summary["packs"]["summary"]["merge"]["replaced_packs"], 1)
        command = summary["packs"]["command"]
        self.assertIn("--security", command)
        self.assertEqual(command[command.index("--security") + 1], TEST_ID)
        self.assertIn("--years", command)
        self.assertEqual(command[command.index("--years") + 1], "2026")

        manifest = self._manifest()
        self.assertEqual(self._entry(manifest, FUND_ID), self._entry(manifest_before, FUND_ID))
        self.assertEqual(self._pack_bytes(FUND_ID, 2026), fund_pack)
        entry = self._entry(manifest, TEST_ID)
        self.assertEqual(entry["last_date"], "2026-09-01")
        self.assertEqual((self.root / "data" / "update_summary.json").exists(), True)
