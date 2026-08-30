from __future__ import annotations

import json
import os
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from sg_investing.data.dividend_quality import load_coverage_report
from sg_investing.data.storage import ParquetStore
from sg_investing.data.validation import dividend_event_key, validate_dividends
from sg_investing.models import DistributionPolicy
from sg_investing.universe.catalog import load_catalog

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("SG_INVESTING_RUN_UNIVERSE_SMOKE") != "1",
        reason="set SG_INVESTING_RUN_UNIVERSE_SMOKE=1 to run against downloaded data",
    ),
]


def _context():
    root = Path(__file__).resolve().parents[2]
    catalog_path = root / "data" / "universe" / "current_catalog.json"
    coverage_path = root / "data" / "dividends" / "coverage_report.json"
    if not catalog_path.exists() or not coverage_path.exists():
        pytest.skip("downloaded catalog and dividend coverage report are required")
    catalog = load_catalog(catalog_path)
    report = load_coverage_report(coverage_path)
    assert report is not None
    return catalog, report, ParquetStore(root / "data")


def _archive_rows(store: ParquetStore):
    rows = []
    for path in sorted((Path(store.root) / "dividends").glob("year=*.parquet")):
        rows.extend(store.read_dividends(year=int(path.stem.split("=", 1)[1])))
    return rows


def test_dividend_archive_is_valid_and_unique():
    _, _, store = _context()
    rows = _archive_rows(store)
    report = validate_dividends(rows)
    assert report.is_valid, report.errors
    assert len(rows) == len({dividend_event_key(row) for row in rows})
    assert all(row.ticker and row.exchange and row.ingested_at for row in rows)
    required_columns = {
        "security_id",
        "ticker",
        "exchange",
        "ex_date",
        "record_date",
        "pay_date",
        "amount",
        "currency",
        "dividend_type",
        "source",
        "source_id",
        "retrieved_at",
        "ingested_at",
    }
    for path in (Path(store.root) / "dividends").glob("year=*.parquet"):
        assert required_columns <= set(pq.read_schema(path).names)


def test_coverage_report_accounts_for_every_catalog_security():
    catalog, report, store = _context()
    catalog_ids = {str(entry.security.security_id) for entry in catalog.securities}
    report_ids = {str(record.security_id) for record in report.securities}
    archive_ids = {str(row.security_id) for row in _archive_rows(store)}
    assert report_ids == catalog_ids
    assert archive_ids <= catalog_ids
    assert report.summary["tracked_securities"] == len(catalog_ids)
    assert report.summary["dividend_event_rows"] == sum(record.event_count for record in report.securities)


def test_coverage_status_never_hides_empty_or_skipped_data():
    _, report, _ = _context()
    allowed_empty = {
        "dividend_data_missing",
        "provider_error",
        "known_accumulating",
        "known_non_distributing",
        "known_distributing_with_no_events",
        "unknown",
    }
    for record in report.securities:
        if record.event_count:
            assert record.coverage_status in {"data_available", "data_available_policy_unknown"}
        else:
            assert record.coverage_status in allowed_empty
        if record.distribution_policy == DistributionPolicy.ACCUMULATING:
            assert record.coverage_status == "known_accumulating"
        if record.distribution_policy == DistributionPolicy.NON_DISTRIBUTING:
            assert record.coverage_status == "known_non_distributing"
        if record.coverage_status == "provider_error":
            assert record.provider_query_succeeded is False
            assert record.error
        if record.provider_query_succeeded:
            assert record.queried_from is not None
            assert record.queried_through is not None


def test_event_currency_metadata_is_valid_and_differences_are_explicit():
    _, report, _ = _context()
    for record in report.securities:
        assert all(len(currency) == 3 and currency.isalpha() and currency == currency.upper()
                   for currency in record.event_currencies)
        if any(currency != record.currency for currency in record.event_currencies):
            assert any("FX conversion" in warning for warning in record.warnings)


def test_coverage_history_and_price_behavior_artifacts_are_current():
    _, report, store = _context()
    history_path = Path(store.root) / "dividends" / "coverage_history.json"
    behavior_path = Path(store.root) / "dividends" / "price_behavior_report.json"
    assert history_path.exists()
    assert behavior_path.exists()
    history = json.loads(history_path.read_text(encoding="utf-8"))
    behavior = json.loads(behavior_path.read_text(encoding="utf-8"))
    assert history["snapshots"]
    assert history["snapshots"][-1]["event_rows"] == report.summary["dividend_event_rows"]
    assert behavior["event_count"] == report.summary["dividend_event_rows"]
    assert behavior["comparable_event_count"] <= behavior["event_count"]
