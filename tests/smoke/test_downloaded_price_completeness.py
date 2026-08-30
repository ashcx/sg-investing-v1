from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest

from sg_investing.data.backfill import MAX_INTERNAL_PRICE_GAP_SESSIONS
from sg_investing.data.price_quality import (
    PriceAuditIssue,
    PriceAuditReport,
    PriceCoverageExpectation,
    audit_price_files,
)
from sg_investing.universe.catalog import load_catalog


pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("SG_INVESTING_RUN_UNIVERSE_SMOKE") != "1",
        reason="set SG_INVESTING_RUN_UNIVERSE_SMOKE=1 to run against downloaded data",
    ),
]


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _expected_start_dates(root: Path) -> dict[str, date]:
    """Load optional local first-trading-date expectations.

    The file is intentionally optional.  Until first-trading dates are added
    to the local security master, the audit can still prove that all catalog
    securities have rows and that their stored ranges are structurally sound.
    """

    path = root / "data" / "universe" / "price_history_expectations.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"Expected an object in {path}.")
    starts: dict[str, date] = {}
    for security_id, value in payload.items():
        if not isinstance(value, str):
            raise AssertionError(f"Expected an ISO date for {security_id} in {path}.")
        starts[security_id] = date.fromisoformat(value)
    return starts


def test_downloaded_price_histories_are_complete_and_valid():
    root = _root()
    catalog_path = root / "data" / "universe" / "current_catalog.json"
    if not catalog_path.exists():
        pytest.skip("current downloaded-universe catalog is not present")

    catalog = load_catalog(catalog_path)
    securities = {
        str(entry.security.security_id): entry.security
        for entry in catalog.securities
    }
    configured_starts = _expected_start_dates(root)
    expectations = {
        security_id: PriceCoverageExpectation(
            security_id=security_id,
            market=security.market,
            currency=security.currency,
            exchange=security.exchange,
            expected_start=(
                configured_starts[security_id]
                if security_id in configured_starts
                else None
            ),
            active=security.active,
        )
        for security_id, security in securities.items()
    }
    paths = sorted((root / "data" / "prices").glob("market=*/year=*.parquet"))
    report = audit_price_files(
        paths,
        expectations=expectations,
        history_floor=catalog.history_start,
        start_tolerance_sessions=5,
        end_tolerance_sessions=5,
        max_internal_gap_sessions=5,
    )
    report_issues = list(report.issues)
    state_path = root / "data" / "backfill" / "price_backfill_state.json"
    if state_path.exists():
        state_payload = json.loads(state_path.read_text(encoding="utf-8"))
        state_records = state_payload.get("securities", {})
        for security_id in sorted(expectations):
            record = state_records.get(security_id)
            stats = report.security_stats.get(security_id)
            if not isinstance(record, dict):
                report_issues.append(
                    PriceAuditIssue(
                        "missing_backfill_state",
                        f"{security_id}: no corresponding price-backfill state record.",
                        security_id,
                    )
                )
                continue
            actual_bars = stats.row_count if stats else 0
            if int(record.get("bars", 0)) != actual_bars:
                report_issues.append(
                    PriceAuditIssue(
                        "backfill_bar_count_mismatch",
                        f"{security_id}: backfill state bars={record.get('bars')} but Parquet has "
                        f"{actual_bars}.",
                        security_id,
                    )
                )
            if (
                stats
                and stats.max_internal_gap_sessions > MAX_INTERNAL_PRICE_GAP_SESSIONS
                and record.get("status") == "stored"
            ):
                report_issues.append(
                    PriceAuditIssue(
                        "stored_internal_gap",
                        f"{security_id}: backfill state is stored despite a maximum internal gap of "
                        f"{stats.max_internal_gap_sessions}.",
                        security_id,
                    )
                )
    report = PriceAuditReport(
        issues=tuple(report_issues),
        security_stats=report.security_stats,
        market_sessions=report.market_sessions,
    )
    if not report.is_valid:
        pytest.fail(report.format_issues())
