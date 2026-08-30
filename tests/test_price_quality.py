from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from sg_investing.data.price_quality import PriceCoverageExpectation, audit_price_files
from tests.helpers import price, security


def _write_rows(path: Path, rows) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [row.model_dump(mode="python") for row in rows]
    for row in payload:
        row["security_id"] = str(row["security_id"])
    pq.write_table(
        pa.Table.from_pylist(
            payload,
            schema=pa.schema(
                [
                    ("security_id", pa.string()),
                    ("trading_date", pa.date32()),
                    ("open", pa.decimal128(32, 18)),
                    ("high", pa.decimal128(32, 18)),
                    ("low", pa.decimal128(32, 18)),
                    ("close", pa.decimal128(32, 18)),
                    ("volume", pa.int64()),
                    ("currency", pa.string()),
                    ("exchange", pa.string()),
                    ("timezone", pa.string()),
                    ("source", pa.string()),
                    ("retrieved_at", pa.timestamp("us", tz="UTC")),
                ]
            ),
        ),
        path,
    )
    return path


def _expectation(sec, *, expected_start=None, expected_end=None):
    return PriceCoverageExpectation(
        security_id=str(sec.security_id),
        market=sec.market,
        currency=sec.currency,
        exchange=sec.exchange,
        expected_start=expected_start,
        expected_end=expected_end,
    )


def test_valid_history_has_no_duplicates_or_internal_gaps(tmp_path):
    sec = security()
    other = security(ticker="OTHER", security_id="33333333-3333-3333-3333-333333333333")
    rows = [
        price(sec, date(2024, 1, 2)),
        price(sec, date(2024, 1, 3)),
        price(sec, date(2024, 1, 5)),
        price(other, date(2024, 1, 2)),
        price(other, date(2024, 1, 3)),
        price(other, date(2024, 1, 5)),
    ]
    path = _write_rows(tmp_path / "prices" / "market=US" / "year=2024.parquet", rows)

    report = audit_price_files(
        [path],
        expectations={
            str(sec.security_id): _expectation(sec),
            str(other.security_id): _expectation(other),
        },
        max_internal_gap_sessions=0,
    )

    assert report.is_valid


def test_history_start_and_end_use_expected_sessions_and_tolerance(tmp_path):
    sec = security()
    other = security(ticker="OTHER", security_id="33333333-3333-3333-3333-333333333333")
    rows = [
        price(sec, date(2024, 1, 3)),
        price(other, date(2024, 1, 2)),
        price(other, date(2024, 1, 3)),
        price(other, date(2024, 1, 4)),
        price(other, date(2024, 1, 5)),
    ]
    path = _write_rows(tmp_path / "prices" / "market=US" / "year=2024.parquet", rows)
    expectation = _expectation(
        sec,
        expected_start=date(2024, 1, 2),
        expected_end=date(2024, 1, 5),
    )
    other_expectation = _expectation(other)

    report = audit_price_files(
        [path],
        expectations={str(sec.security_id): expectation, str(other.security_id): other_expectation},
        start_tolerance_sessions=0,
        end_tolerance_sessions=0,
    )

    codes = {issue.code for issue in report.issues if issue.security_id == str(sec.security_id)}
    assert "missing_start_history" in codes
    assert "missing_end_history" in codes


def test_history_audit_finds_missing_security_duplicate_and_internal_gap(tmp_path):
    sec = security()
    other = security(ticker="OTHER", security_id="33333333-3333-3333-3333-333333333333")
    absent = security(ticker="ABSENT", security_id="44444444-4444-4444-4444-444444444444")
    rows = [
        price(sec, date(2024, 1, 2)),
        price(sec, date(2024, 1, 4)),
        price(sec, date(2024, 1, 4)),
        price(other, date(2024, 1, 2)),
        price(other, date(2024, 1, 3)),
        price(other, date(2024, 1, 4)),
    ]
    path = _write_rows(tmp_path / "prices" / "market=US" / "year=2024.parquet", rows)

    report = audit_price_files(
        [path],
        expectations={
            str(sec.security_id): _expectation(sec),
            str(other.security_id): _expectation(other),
            str(absent.security_id): _expectation(absent),
        },
        max_internal_gap_sessions=0,
    )

    codes = {issue.code for issue in report.issues if issue.security_id == str(sec.security_id)}
    assert {"duplicate_price_observations", "internal_price_gaps"}.issubset(codes)
    assert any(
        issue.code == "missing_security_history" and issue.security_id == str(absent.security_id)
        for issue in report.issues
    )


def test_history_audit_finds_out_of_order_dates(tmp_path):
    sec = security()
    other = security(ticker="OTHER", security_id="33333333-3333-3333-3333-333333333333")
    rows = [
        price(sec, date(2024, 1, 3)),
        price(sec, date(2024, 1, 2)),
        price(other, date(2024, 1, 2)),
        price(other, date(2024, 1, 3)),
    ]
    path = _write_rows(tmp_path / "prices" / "market=US" / "year=2024.parquet", rows)

    report = audit_price_files(
        [path],
        expectations={
            str(sec.security_id): _expectation(sec),
            str(other.security_id): _expectation(other),
        },
    )

    assert any(
        issue.code == "dates_not_ordered" and issue.security_id == str(sec.security_id)
        for issue in report.issues
    )


def test_history_audit_finds_ohlc_volume_and_metadata_errors(tmp_path):
    sec = security()
    when = datetime(2024, 1, 2, tzinfo=timezone.utc)
    raw = [
        {
            "security_id": str(sec.security_id),
            "trading_date": date(2024, 1, 2),
            "open": Decimal("110"),
            "high": Decimal("100"),
            "low": Decimal("90"),
            "close": Decimal("0"),
            "volume": -1,
            "currency": "SGD",
            "exchange": "NASDAQ",
            "timezone": None,
            "source": "synthetic",
            "retrieved_at": when,
        }
    ]
    path = tmp_path / "prices" / "market=US" / "year=2024.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(
            raw,
            schema=pa.schema(
                [
                    ("security_id", pa.string()),
                    ("trading_date", pa.date32()),
                    ("open", pa.decimal128(32, 18)),
                    ("high", pa.decimal128(32, 18)),
                    ("low", pa.decimal128(32, 18)),
                    ("close", pa.decimal128(32, 18)),
                    ("volume", pa.int64()),
                    ("currency", pa.string()),
                    ("exchange", pa.string()),
                    ("timezone", pa.string()),
                    ("source", pa.string()),
                    ("retrieved_at", pa.timestamp("us", tz="UTC")),
                ]
            ),
        ),
        path,
    )

    report = audit_price_files([path], expectations={str(sec.security_id): _expectation(sec)})

    codes = {issue.code for issue in report.issues if issue.security_id == str(sec.security_id)}
    assert {
        "invalid_ohlc",
        "invalid_prices",
        "invalid_volume",
        "currency_mismatch",
        "exchange_mismatch",
        "timezone_missing",
    }.issubset(codes)


def test_history_audit_flags_zero_low_and_extreme_price_levels(tmp_path):
    sec = security()
    other = security(ticker="OTHER", security_id="33333333-3333-3333-3333-333333333333")
    raw = [
        price(sec, date(2024, 1, 2), "100").model_copy(
            update={"low": Decimal("0")}
        ),
        price(other, date(2024, 1, 2), "1000001"),
    ]
    path = _write_rows(tmp_path / "prices" / "market=US" / "year=2024.parquet", raw)

    report = audit_price_files(
        [path],
        expectations={str(sec.security_id): _expectation(sec), str(other.security_id): _expectation(other)},
    )

    codes = {issue.code for issue in report.issues if issue.security_id == str(sec.security_id)}
    other_codes = {issue.code for issue in report.issues if issue.security_id == str(other.security_id)}
    assert "invalid_prices" in codes
    assert "suspicious_price_levels" in other_codes
