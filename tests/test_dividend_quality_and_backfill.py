from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sg_investing.data.dividend_backfill import backfill_dividends
from sg_investing.data.dividend_quality import (
    DividendCoverageStatus,
    build_dividend_coverage,
    load_coverage_report,
    record_coverage_snapshot,
)
from sg_investing.data.storage import ParquetStore
from sg_investing.models import DistributionPolicy, DividendEvent
from sg_investing.universe.catalog import ConfiguredSecurity, UniverseCatalog
from tests.helpers import dividend, security


def _catalog(*securities) -> UniverseCatalog:
    return UniverseCatalog(
        history_start=date(2024, 1, 1),
        securities=[
            ConfiguredSecurity(
                universe="test",
                effective_from=date(2024, 1, 1),
                source="test",
                security=item,
            )
            for item in securities
        ],
    )


class DividendProvider:
    name = "test_provider"

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.calls = []

    def get_dividends(self, security, start_date, end_date):
        self.calls.append((security.ticker, start_date, end_date))
        return [
            row
            for row in self.rows
            if row.security_id == security.security_id and start_date <= row.ex_date <= end_date
        ]


def test_coverage_matrix_distinguishes_accumulating_missing_and_unknown(tmp_path: Path):
    distributing = security(
        ticker="PAY",
        security_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        distribution_policy=DistributionPolicy.DISTRIBUTING,
    )
    accumulating = security(
        ticker="ACC",
        security_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        distribution_policy=DistributionPolicy.ACCUMULATING,
    )
    unknown = security(
        ticker="UNK",
        security_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        distribution_policy=DistributionPolicy.UNKNOWN,
    )
    non_distributing = security(
        ticker="NODIV",
        security_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        distribution_policy=DistributionPolicy.NON_DISTRIBUTING,
    )
    store = ParquetStore(tmp_path)
    store.upsert_dividends([dividend(unknown, date(2024, 2, 1), "1")])

    report = build_dividend_coverage(
        catalog=_catalog(distributing, accumulating, unknown, non_distributing), store=store
    )
    by_ticker = {record.ticker: record for record in report.securities}

    assert by_ticker["PAY"].coverage_status == DividendCoverageStatus.DIVIDEND_DATA_MISSING
    assert by_ticker["ACC"].coverage_status == DividendCoverageStatus.KNOWN_ACCUMULATING
    assert by_ticker["UNK"].coverage_status == DividendCoverageStatus.DATA_AVAILABLE_POLICY_UNKNOWN
    assert by_ticker["NODIV"].coverage_status == DividendCoverageStatus.KNOWN_NON_DISTRIBUTING
    assert report.summary["dividend_event_rows"] == 1
    assert report.summary["securities_with_dividend_events"] == 1


def test_coverage_report_persists_frequency_and_amount_anomaly_metrics(tmp_path: Path):
    paying = security(ticker="PAY")
    store = ParquetStore(tmp_path)
    store.upsert_dividends(
        [
            dividend(paying, date(2024, 1, 1), "1"),
            dividend(paying, date(2024, 4, 1), "3"),
            dividend(paying, date(2024, 7, 1), "5"),
        ]
    )

    record = build_dividend_coverage(catalog=_catalog(paying), store=store).securities[0]

    assert record.average_inter_event_gap_days == 91.0
    assert record.median_dividend_amount == Decimal(3)
    assert record.largest_dividend_amount == Decimal(5)
    assert record.smallest_dividend_amount == Decimal(1)
    assert record.longest_inter_event_gap_days == 91


def test_backfill_is_idempotent_and_records_empty_queries(tmp_path: Path):
    paying = security(ticker="PAY", security_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    empty = security(ticker="EMPTY", security_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    event = DividendEvent(
        security_id=paying.security_id,
        ex_date=date(2024, 2, 1),
        amount=Decimal("1.25"),
        currency="USD",
        source="test_provider",
        source_id="test_provider:PAY:2024-02-01",
    )
    provider = DividendProvider([event])
    store = ParquetStore(tmp_path)
    coverage_path = tmp_path / "dividends" / "coverage_report.json"
    catalog = _catalog(paying, empty)

    first, _ = backfill_dividends(
        catalog=catalog,
        store=store,
        provider=provider,
        coverage_path=coverage_path,
        end_date=date(2024, 12, 31),
        workers=1,
        retries=0,
    )
    second, _ = backfill_dividends(
        catalog=catalog,
        store=store,
        provider=provider,
        coverage_path=coverage_path,
        end_date=date(2024, 12, 31),
        workers=1,
        retries=0,
    )

    assert first.summary["dividend_event_rows"] == 1
    assert second.summary["dividend_event_rows"] == 1
    assert len(store.read_dividends(year=2024)) == 1
    assert load_coverage_report(coverage_path) is not None
    records = {record.ticker: record for record in second.securities}
    assert records["PAY"].coverage_status == DividendCoverageStatus.DATA_AVAILABLE
    assert records["EMPTY"].coverage_status == DividendCoverageStatus.KNOWN_DISTRIBUTING_WITH_NO_EVENTS
    assert records["EMPTY"].provider_query_succeeded is True
    assert any("not proof" in warning for warning in records["EMPTY"].warnings)
    assert len(provider.calls) == 4
    assert provider.calls[-1][1] == date(2024, 12, 24)


def test_accumulating_security_is_not_requested(tmp_path: Path):
    accumulating = security(ticker="ACC", distribution_policy=DistributionPolicy.ACCUMULATING)
    provider = DividendProvider()
    report, results = backfill_dividends(
        catalog=_catalog(accumulating),
        store=ParquetStore(tmp_path),
        provider=provider,
        coverage_path=tmp_path / "coverage.json",
        end_date=date(2024, 12, 31),
        workers=1,
        retries=0,
    )

    assert provider.calls == []
    assert results[0].status == DividendCoverageStatus.KNOWN_ACCUMULATING
    assert report.securities[0].coverage_status == DividendCoverageStatus.KNOWN_ACCUMULATING
    assert report.securities[0].provider_query_succeeded is False
    assert report.securities[0].queried_from is None
    assert report.securities[0].queried_through is None


def test_backfill_accepts_and_reports_a_provider_event_currency_difference(tmp_path: Path):
    paying = security(ticker="JP", currency="SGD", market="SG", exchange="SGX")
    event = DividendEvent(
        security_id=paying.security_id,
        ex_date=date(2024, 2, 1),
        amount=Decimal(7),
        currency="JPY",
        source="test_provider",
        source_id="test_provider:jp:2024-02-01:7:JPY",
    )
    provider = DividendProvider([event])
    report, _ = backfill_dividends(
        catalog=_catalog(paying),
        store=ParquetStore(tmp_path),
        provider=provider,
        coverage_path=tmp_path / "coverage.json",
        end_date=date(2024, 12, 31),
        workers=1,
        retries=0,
    )
    record = report.securities[0]
    assert record.event_currencies == ["JPY"]
    assert record.event_count == 1


def test_full_history_ignores_an_existing_checkpoint(tmp_path: Path):
    paying = security(ticker="PAY")
    provider = DividendProvider()
    coverage_path = tmp_path / "coverage.json"
    catalog = _catalog(paying)
    first, _ = backfill_dividends(
        catalog=catalog,
        store=ParquetStore(tmp_path),
        provider=provider,
        coverage_path=coverage_path,
        end_date=date(2024, 12, 31),
        workers=1,
        retries=0,
    )
    assert first.securities[0].queried_from == date(2024, 1, 1)

    _, _ = backfill_dividends(
        catalog=catalog,
        store=ParquetStore(tmp_path),
        provider=provider,
        coverage_path=coverage_path,
        end_date=date(2024, 12, 31),
        workers=1,
        retries=0,
        full_history=True,
    )
    assert provider.calls[-1][1] == date(2024, 1, 1)


def test_provider_error_is_recorded_without_erasing_existing_events(tmp_path: Path):
    paying = security(ticker="PAY")
    event = dividend(paying, date(2024, 2, 1), "1").model_copy(
        update={"source": "test_provider", "source_id": "test_provider:PAY:2024-02-01"}
    )
    coverage_path = tmp_path / "coverage.json"
    store = ParquetStore(tmp_path)
    store.upsert_dividends([event])

    class FailingProvider(DividendProvider):
        def get_dividends(self, security, start_date, end_date):
            self.calls.append((security.ticker, start_date, end_date))
            raise RuntimeError("provider outage")

    report, results = backfill_dividends(
        catalog=_catalog(paying),
        store=store,
        provider=FailingProvider(),
        coverage_path=coverage_path,
        end_date=date(2024, 12, 31),
        workers=1,
        retries=0,
    )

    record = report.securities[0]
    assert results[0].status == DividendCoverageStatus.PROVIDER_ERROR
    assert record.coverage_status == DividendCoverageStatus.PROVIDER_ERROR
    assert record.event_count == 1
    assert store.read_dividends(year=2024) == [event]


def test_retry_provider_errors_only_queries_the_failed_subset(tmp_path: Path):
    good = security(ticker="GOOD", security_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    bad = security(ticker="BAD", security_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    coverage_path = tmp_path / "coverage.json"
    catalog = _catalog(good, bad)

    class SelectiveProvider(DividendProvider):
        def get_dividends(self, security, start_date, end_date):
            self.calls.append((security.ticker, start_date, end_date))
            if security.ticker == "BAD":
                raise RuntimeError("temporary outage")
            return []

    first_provider = SelectiveProvider()
    backfill_dividends(
        catalog=catalog,
        store=ParquetStore(tmp_path),
        provider=first_provider,
        coverage_path=coverage_path,
        end_date=date(2024, 12, 31),
        workers=1,
        retries=0,
    )
    assert {call[0] for call in first_provider.calls} == {"GOOD", "BAD"}

    retry_provider = DividendProvider()
    _, retry_results = backfill_dividends(
        catalog=catalog,
        store=ParquetStore(tmp_path),
        provider=retry_provider,
        coverage_path=coverage_path,
        end_date=date(2024, 12, 31),
        workers=1,
        retries=0,
        retry_provider_errors=True,
    )
    assert [result.ticker for result in retry_results] == ["BAD"]
    assert retry_provider.calls == [("BAD", date(2024, 1, 1), date(2024, 12, 31))]


def test_coverage_history_warns_on_provider_errors_archive_loss_and_coverage_drop(tmp_path: Path):
    paying = security(ticker="PAY", security_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    store = ParquetStore(tmp_path)
    base = build_dividend_coverage(catalog=_catalog(paying), store=store)
    first = base.model_copy(
        update={
            "summary": {
                **base.summary,
                "dividend_data_coverage_percent": 100.0,
                "status_data_available": 1,
                "dividend_event_rows": 10,
            }
        }
    )
    history_path = tmp_path / "dividends" / "coverage_history.json"
    assert record_coverage_snapshot(first, history_path) == []

    degraded = first.model_copy(
        update={
            "summary": {
                **first.summary,
                "dividend_data_coverage_percent": 90.0,
                "status_provider_error": 1,
                "dividend_event_rows": 0,
            }
        }
    )
    warnings = record_coverage_snapshot(degraded, history_path)
    assert any("coverage fell" in warning for warning in warnings)
    assert any("provider errors increased" in warning for warning in warnings)
    assert any("row count fell" in warning for warning in warnings)
