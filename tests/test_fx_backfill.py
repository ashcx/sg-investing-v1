"""Synthetic-fixture tests for the FX backfill (Sprint 7.5 Track A).

Covers the pure normalization/splice logic of scripts/backfill_fx_history.py
and the end-to-end splice through the storage layer with mocked fetchers. No
test touches the network (AGENTS.md: no live calls in the normal suite).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID

from scripts.backfill_fx_history import (
    _parse_mas_records,
    _parse_mirror_rows,
    backfill_pair,
    build_fx_rows,
    compute_normalization_ratio,
    coverage_gaps,
    cross_check_divergence,
    derive_required_pairs,
    detect_unit_scale,
    existing_fx_series,
    fetch_datagovsg_mirror,
)
from sg_investing.data.storage import ParquetStore
from sg_investing.models import AssetType, FxRate, PriceBar, Security

SECURITY_ID = UUID("11111111-1111-1111-1111-111111111111")
GBP_SECURITY_ID = UUID("22222222-2222-2222-2222-222222222222")


def _security(
    security_id: UUID, ticker: str, currency: str, market: str, exchange: str
) -> Security:
    return Security(
        security_id=security_id,
        ticker=ticker,
        name=f"Synthetic {ticker}",
        exchange=exchange,
        market=market,
        currency=currency,
        asset_type=AssetType.ETF,
        timezone="America/New_York" if market == "US" else "Asia/Singapore",
    )


def _price(security: Security, trading_date: date) -> PriceBar:
    return PriceBar(
        security_id=security.security_id,
        trading_date=trading_date,
        open=Decimal(1),
        high=Decimal(1),
        low=Decimal(1),
        close=Decimal(1),
        volume=1,
        currency=security.currency,
        exchange=security.exchange,
        timezone=security.timezone,
        source="synthetic",
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class DeriveRequiredPairsTestCase(TestCase):
    """Only currencies priced before 2003-12-01 are required."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = ParquetStore(self.root / "data")
        self.us = _security(SECURITY_ID, "TESTUS", "USD", "US", "NASDAQ")
        self.gb = _security(GBP_SECURITY_ID, "TESTGB", "GBP", "GB", "LSE")
        self.store.upsert_prices(
            market="US",
            rows=[
                _price(self.us, date(2000, 1, 3)),
                _price(self.us, date(2003, 11, 28)),
            ],
            pipeline_version="test",
        )
        self.store.upsert_prices(
            market="GB", rows=[_price(self.gb, date(2009, 1, 5))], pipeline_version="test"
        )
        self.store.upsert_prices(
            market="SG", rows=[_price(self.us, date(2002, 6, 3))], pipeline_version="test"
        )

    def test_only_pre_cutoff_non_sgd_currencies_are_derived(self) -> None:
        pairs = derive_required_pairs(self.root / "data")
        self.assertEqual(set(pairs), {"USD"})
        self.assertEqual(pairs["USD"], date(2000, 1, 3))

    def test_cutoff_boundary_date_does_not_create_a_requirement(self) -> None:
        self.store.upsert_prices(
            market="GB", rows=[_price(self.gb, date(2003, 12, 1))], pipeline_version="test"
        )
        pairs = derive_required_pairs(self.root / "data")
        self.assertNotIn("GBP", pairs)


class DetectUnitScaleTestCase(TestCase):
    """MAS per-100 quoting is detected against the ECB series."""

    def test_one_unit_quoting(self) -> None:
        dates = [date(2003, 1, 2), date(2003, 1, 3), date(2003, 1, 6)]
        mas = {d: Decimal("0.22189") for d in dates}
        ecb = {d: Decimal("0.222") for d in dates}
        self.assertEqual(detect_unit_scale(mas, ecb), Decimal(1))

    def test_per_hundred_quoting(self) -> None:
        dates = [date(2003, 1, 2), date(2003, 1, 3), date(2003, 1, 6)]
        mas = {d: Decimal("22.189") for d in dates}
        ecb = {d: Decimal("0.222") for d in dates}
        self.assertEqual(detect_unit_scale(mas, ecb), Decimal(100))


class NormalizationRatioTestCase(TestCase):
    """Ratio comes from the last month covered by both MAS and the store."""

    def test_ratio_uses_last_fully_overlapping_month(self) -> None:
        mas = {
            date(2003, 11, 28): Decimal("1.70"),
            date(2003, 12, 1): Decimal("1.70"),
            date(2003, 12, 2): Decimal("1.70"),
            date(2003, 12, 3): Decimal("1.70"),
            date(2003, 12, 4): Decimal("1.70"),
            date(2003, 12, 5): Decimal("1.70"),
        }
        existing = {
            date(2003, 12, 1): Decimal("1.717"),
            date(2003, 12, 2): Decimal("1.717"),
            date(2003, 12, 3): Decimal("1.717"),
            date(2003, 12, 4): Decimal("1.717"),
            date(2003, 12, 5): Decimal("1.717"),
        }
        ratio, month = compute_normalization_ratio(mas, existing)
        self.assertEqual(month, "2003-12")
        self.assertEqual(ratio, Decimal("1.01"))

    def test_no_overlap_means_identity_ratio(self) -> None:
        mas = {date(2003, 11, 28): Decimal("1.70")}
        existing = {date(2004, 1, 2): Decimal("1.70")}
        self.assertEqual(compute_normalization_ratio(mas, existing), (Decimal(1), None))

    def test_existing_store_with_no_rates_returns_identity(self) -> None:
        mas = {date(2003, 11, 28): Decimal("1.70")}
        self.assertEqual(compute_normalization_ratio(mas, {}), (Decimal(1), None))


class BuildFxRowsTestCase(TestCase):
    """Splice keeps only missing in-window dates and applies the scaling."""

    def setUp(self) -> None:
        self.mas = {
            date(2003, 11, 28): Decimal("1.70"),
            date(2003, 11, 29): Decimal("1.70"),  # duplicate date below
            date(2003, 12, 15): Decimal("1.72"),  # beyond the window end
            date(2004, 1, 2): Decimal("1.72"),  # beyond the window end
        }
        self.mas[date(2003, 11, 29)] = Decimal("1.701")

    def test_window_existing_and_scaling_rules(self) -> None:
        rows = build_fx_rows(
            self.mas,
            currency="USD",
            unit_scale=Decimal(1),
            normalization_ratio=Decimal("1.01"),
            existing_dates={date(2003, 11, 28)},
        )
        self.assertEqual(
            [(row.rate_date, row.rate_to_sgd) for row in rows],
            [(date(2003, 11, 29), Decimal("1.71801"))],
        )
        self.assertEqual(rows[0].source, "mas")
        self.assertEqual(rows[0].base_currency, "USD")

    def test_existing_dates_are_never_rewritten(self) -> None:
        rows = build_fx_rows(
            self.mas,
            currency="USD",
            unit_scale=Decimal(100),
            normalization_ratio=Decimal(1),
            existing_dates={date(2003, 11, 28), date(2003, 11, 29)},
        )
        self.assertEqual(rows, [])


class ParseRecordsTestCase(TestCase):
    """Both MAS record schemas parse into {date: rate} with window filtering."""

    def test_legacy_api_schema_is_parsed_and_filtered(self) -> None:
        records = [
            {"end_of_day": "2000-01-03", "end_of_day_usd_sgd": "1.6635"},
            {"end_of_day": "1999-12-31", "end_of_day_usd_sgd": "1.6620"},  # before window
            {"end_of_day": "2004-01-02", "end_of_day_usd_sgd": "1.6900"},  # after window
            {"end_of_day": "2000-01-04", "end_of_day_usd_sgd": None},  # missing quote
            {"end_of_day": "2000-01-05", "end_of_day_usd_sgd": "-"},  # MAS missing marker
            {"end_of_day": "bad", "end_of_day_usd_sgd": "1.67"},
        ]
        rates = _parse_mas_records(
            records, "USD", date(2000, 1, 1), date(2003, 12, 31)
        )
        self.assertEqual(rates, {date(2000, 1, 3): Decimal("1.6635")})

    def test_mirror_schema_and_missing_currency_column(self) -> None:
        rows = [
            {"vault_id": "1", "date": "2000-01-07", "exchange_rate_usd": "1.6635"},
            {"vault_id": "2", "date": "2000-01-14", "exchange_rate_hkd": "0.2145"},
            {"vault_id": "3", "date": "2003-11-12", "exchange_rate_usd": "1.7347"},
        ]
        usd = _parse_mirror_rows(rows, "USD", date(2000, 1, 1), date(2003, 12, 31))
        hkd = _parse_mirror_rows(rows, "HKD", date(2000, 1, 1), date(2003, 12, 31))
        self.assertEqual(usd, {date(2000, 1, 7): Decimal("1.6635"), date(2003, 11, 12): Decimal("1.7347")})
        self.assertEqual(hkd, {date(2000, 1, 14): Decimal("0.2145")})


class FetchMirrorPagingTestCase(TestCase):
    """The list-rows cursor cycles on exhausted views; the loop must stop."""

    def test_cycling_cursor_terminates_and_normalises_next_links(self) -> None:
        page = {"data": {"rows": [{"vault_id": "1", "date": "2000-01-07", "exchange_rate_usd": "1.6635"}],
                         "links": {"next": "idCursor%5Bvalue%5D=1&limit=1000"}}}
        requested_urls: list[str] = []

        def fake_get_json(url: str) -> dict:
            requested_urls.append(url)
            return dict(page)

        with (
            patch("scripts.backfill_fx_history.DATAGOVSG_PACE_SECONDS", 0),
            patch(
                "scripts.backfill_fx_history._http_get_json",
                side_effect=fake_get_json,
            ),
        ):
            rates = fetch_datagovsg_mirror("USD", date(2000, 1, 1), date(2003, 12, 31))

        self.assertEqual(rates, {date(2000, 1, 7): Decimal("1.6635")})
        self.assertEqual(len(requested_urls), 2)  # second page is a repeat: stop
        # The bare cursor fragment must be joined onto the full list-rows endpoint.
        self.assertEqual(
            requested_urls[1],
            "https://api-production.data.gov.sg/v2/public/api/datasets/"
            "d_046ff8d521a218d9178178cfbfc45c2c/list-rows?idCursor%5Bvalue%5D=1&limit=1000",
        )


class CoverageGapsTestCase(TestCase):
    """A1: the exact coverage gap of a sourced series is quantified."""

    def test_weekly_series_reports_head_gap_and_tail_hole(self) -> None:
        rates = {
            date(2003, 10, 31): Decimal(1),
            date(2003, 11, 7): Decimal(1),
            date(2003, 11, 14): Decimal(1),
        }
        gaps = coverage_gaps(rates, date(2000, 1, 1), date(2003, 11, 30))
        self.assertEqual(gaps["first"], "2003-10-31")
        self.assertEqual(gaps["last"], "2003-11-14")
        self.assertEqual(gaps["observations"], 3)
        # 2000-01-01 -> 2003-10-31 head gap dominates the interior 6-day gaps.
        self.assertEqual(gaps["longest_gap"], ["2000-01-01", "2003-10-31"])
        self.assertEqual(gaps["longest_gap_days"], (date(2003, 10, 31) - date(2000, 1, 1)).days)

    def test_empty_series_reports_the_whole_window(self) -> None:
        gaps = coverage_gaps({}, date(2000, 1, 1), date(2003, 11, 30))
        self.assertIsNone(gaps["first"])
        self.assertEqual(gaps["observations"], 0)
        self.assertEqual(gaps["longest_gap"], ["2000-01-01", "2003-11-30"])

    def test_daily_series_has_no_interior_gap(self) -> None:
        rates = {date(2003, 11, d): Decimal(1) for d in (26, 27, 28)}
        gaps = coverage_gaps(rates, date(2003, 11, 26), date(2003, 11, 28))
        self.assertEqual(gaps["longest_gap_days"], 0)
        self.assertEqual(gaps["observations"], 3)

    def test_interior_gap_counts_only_missing_days(self) -> None:
        rates = {date(2003, 11, 3): Decimal(1), date(2003, 11, 10): Decimal(1)}
        gaps = coverage_gaps(rates, date(2003, 11, 1), date(2003, 11, 12))
        # Mon 3 Nov -> Mon 10 Nov: six calendar days without a quote.
        self.assertEqual(gaps["longest_gap_days"], 6)
        self.assertEqual(gaps["longest_gap"], ["2003-11-03", "2003-11-10"])
        self.assertEqual(gaps["first"], "2003-11-03")
        self.assertEqual(gaps["last"], "2003-11-10")


class CrossCheckDivergenceTestCase(TestCase):
    def test_identical_series_diverge_by_zero(self) -> None:
        ecb = {date(2003, 1, 2): Decimal("1.7000"), date(2003, 1, 3): Decimal("1.7010")}
        divergence = cross_check_divergence(dict(ecb), ecb)
        assert divergence is not None
        self.assertEqual(divergence.mean_bps, Decimal(0))
        self.assertFalse(divergence.as_dict()["flagged"])

    def test_two_percent_gap_is_flagged(self) -> None:
        ecb = {date(2003, 1, 2): Decimal("1.70")}
        mas = {date(2003, 1, 2): Decimal("1.734")}
        divergence = cross_check_divergence(mas, ecb)
        assert divergence is not None
        self.assertEqual(divergence.max_bps.quantize(Decimal(1)), Decimal(200))
        self.assertTrue(divergence.as_dict()["flagged"])

    def test_no_common_dates(self) -> None:
        self.assertIsNone(cross_check_divergence({date(2003, 1, 2): Decimal(1)}, {}))


class BackfillPairSpliceTestCase(TestCase):
    """End-to-end splice through the store with mocked fetchers."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data_root = self.root / "data"
        self.store = ParquetStore(self.data_root)
        self.store.upsert_fx(
            rows=[
                FxRate(
                    rate_date=date(2003, 12, 1),
                    base_currency="USD",
                    rate_to_sgd=Decimal("1.717"),
                    source="yahoo_finance",
                ),
                FxRate(
                    rate_date=date(2003, 12, 2),
                    base_currency="USD",
                    rate_to_sgd=Decimal("1.717"),
                    source="yahoo_finance",
                ),
                FxRate(
                    rate_date=date(2003, 12, 3),
                    base_currency="USD",
                    rate_to_sgd=Decimal("1.717"),
                    source="yahoo_finance",
                ),
                FxRate(
                    rate_date=date(2003, 12, 4),
                    base_currency="USD",
                    rate_to_sgd=Decimal("1.717"),
                    source="yahoo_finance",
                ),
                FxRate(
                    rate_date=date(2003, 12, 5),
                    base_currency="USD",
                    rate_to_sgd=Decimal("1.717"),
                    source="yahoo_finance",
                ),
            ]
        )

    def _mas_series(self) -> dict[date, Decimal]:
        series: dict[date, Decimal] = {}
        for day, rate in self._business_days(date(2000, 1, 3), date(2003, 11, 28)):
            series[day] = Decimal("1.70")
        # December 2003 exists in the MAS pull only to measure the seam.
        for day, _rate in self._business_days(date(2003, 12, 1), date(2003, 12, 31)):
            series[day] = Decimal("1.70")
        return series

    @staticmethod
    def _business_days(start: date, end: date) -> list[tuple[date, Decimal]]:
        days = []
        cursor = start
        while cursor <= end:
            if cursor.weekday() < 5:
                days.append((cursor, Decimal(1)))
            cursor += timedelta(days=1)
        return days

    def test_usd_splice_is_normalized_and_never_touches_2003_plus(self) -> None:
        mas = self._mas_series()
        ecb = {day: rate * Decimal("1.0001") for day, rate in mas.items()}
        with (
            patch(
                "scripts.backfill_fx_history.fetch_mas_rates", return_value=(mas, "api.mas.gov.sg")
            ),
            patch("scripts.backfill_fx_history.fetch_ecb_rates", return_value=ecb),
        ):
            summary, _rows = backfill_pair(
                store=self.store,
                data_root=self.data_root,
                currency="USD",
                earliest_price_date=date(2000, 1, 3),
                write=True,
            )

        self.assertIsNone(summary.error)
        self.assertEqual(summary.mas_source_used, "api.mas.gov.sg")
        self.assertEqual(summary.unit_scale, Decimal(1))
        self.assertEqual(summary.normalization_month, "2003-12")
        self.assertEqual(summary.normalization_ratio, Decimal("1.01"))

        stored = existing_fx_series(self.data_root, "USD")
        backfilled = {d: v for d, v in stored.items() if d < date(2003, 12, 1)}
        untouched = {d: v for d, v in stored.items() if d >= date(2003, 12, 1)}
        self.assertEqual(len(backfilled), summary.rows_written)
        self.assertEqual(
            untouched,
            {
                date(2003, 12, 1): Decimal("1.717"),
                date(2003, 12, 2): Decimal("1.717"),
                date(2003, 12, 3): Decimal("1.717"),
                date(2003, 12, 4): Decimal("1.717"),
                date(2003, 12, 5): Decimal("1.717"),
            },
        )
        # 1.70 * 1.01 at the seam equals the stored December level exactly, so
        # no level seam enters SGD returns.
        seam = backfilled[date(2003, 11, 28)]
        self.assertEqual(seam, Decimal("1.717"))

    def test_pair_without_existing_history_is_written_as_is(self) -> None:
        mas = {
            day: Decimal("0.22189")
            for day, _ in self._business_days(date(2003, 11, 24), date(2003, 11, 28))
        }
        with (
            patch(
                "scripts.backfill_fx_history.fetch_mas_rates",
                return_value=(mas, "data.gov.sg mirror of MAS dataset"),
            ),
            patch(
                "scripts.backfill_fx_history.fetch_ecb_rates",
                return_value={day: rate * Decimal("1.001") for day, rate in mas.items()},
            ),
        ):
            summary, _rows = backfill_pair(
                store=self.store,
                data_root=self.data_root,
                currency="HKD",
                earliest_price_date=date(2000, 1, 3),
                write=True,
            )

        self.assertIsNone(summary.error)
        self.assertEqual(summary.normalization_ratio, Decimal(1))
        self.assertIsNone(summary.normalization_month)
        stored = existing_fx_series(self.data_root, "HKD")
        self.assertEqual(sorted(stored), sorted(mas))
        self.assertEqual(stored[date(2003, 11, 28)], Decimal("0.22189"))

    def test_all_mas_paths_blocked_reports_error_without_writes(self) -> None:
        from scripts.backfill_fx_history import MasUnavailable

        with (
            patch(
                "scripts.backfill_fx_history.fetch_mas_rates",
                side_effect=MasUnavailable("api.mas.gov.sg: DNS failure"),
            ),
        ):
            summary, rows = backfill_pair(
                store=self.store,
                data_root=self.data_root,
                currency="USD",
                earliest_price_date=date(2000, 1, 3),
                write=True,
            )
        self.assertIn("api.mas.gov.sg: DNS failure", summary.error or "")
        self.assertEqual(rows, [])
        self.assertEqual(summary.rows_written, 0)
