"""Local dividend coverage profiling and persisted coverage contracts.

The event archive answers "which cash events were stored?".  This module
tracks the separate question "was the provider actually queried for this
security and what did an empty response mean?" so an empty list is never
silently treated as a confirmed zero dividend history.
"""

from __future__ import annotations

import json
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from statistics import median
from uuid import UUID

import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, Field

from sg_investing.data.storage import ParquetStore
from sg_investing.models import DistributionPolicy, DividendEvent, PriceBar, Security
from sg_investing.universe.catalog import UniverseCatalog


class DividendCoverageStatus(str):
    """String constants persisted in the coverage report."""

    DATA_AVAILABLE = "data_available"
    DATA_AVAILABLE_POLICY_UNKNOWN = "data_available_policy_unknown"
    KNOWN_ACCUMULATING = "known_accumulating"
    KNOWN_NON_DISTRIBUTING = "known_non_distributing"
    KNOWN_DISTRIBUTING_WITH_NO_EVENTS = "known_distributing_with_no_events"
    DIVIDEND_DATA_MISSING = "dividend_data_missing"
    PROVIDER_ERROR = "provider_error"
    UNKNOWN = "unknown"


class DividendCoverageRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    security_id: UUID
    ticker: str
    asset_type: str
    exchange: str
    currency: str
    distribution_policy: DistributionPolicy
    required_start_date: date
    event_count: int = Field(ge=0)
    first_event_date: date | None = None
    last_event_date: date | None = None
    average_inter_event_gap_days: float | None = None
    median_dividend_amount: Decimal | None = None
    largest_dividend_amount: Decimal | None = None
    smallest_dividend_amount: Decimal | None = None
    longest_inter_event_gap_days: int = Field(default=0, ge=0)
    queried_from: date | None = None
    queried_through: date | None = None
    provider_query_succeeded: bool = False
    coverage_status: str = DividendCoverageStatus.UNKNOWN
    sources: list[str] = Field(default_factory=list)
    event_currencies: list[str] = Field(default_factory=list)
    last_attempt_at: datetime | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)


class DividendCoverageReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    generated_at: datetime
    history_start: date
    summary: dict[str, int | float]
    securities: list[DividendCoverageRecord]


@dataclass(frozen=True)
class DividendPriceBehaviorReport:
    """Review-only comparison between dividend events and local raw prices."""

    event_count: int
    comparable_event_count: int
    events_without_price_window: int
    events_with_price_response: int
    large_price_drops_without_dividend: int
    currency_mismatch_events: int
    warnings: list[str] = field(default_factory=list)


def audit_dividend_price_behavior(
    dividends: list[DividendEvent],
    prices: list[PriceBar],
    *,
    large_drop_threshold: Decimal = Decimal("0.20"),
    event_window_days: int = 3,
    warning_limit: int = 100,
) -> DividendPriceBehaviorReport:
    """Flag price/dividend mismatches without treating market moves as proof.

    This is deliberately a review signal.  A price drop near an ex-date can
    also reflect market news, corporate actions, or adjusted-price semantics;
    a dividend can be paid without a clean one-day price response.
    """

    if event_window_days < 0 or large_drop_threshold < 0 or warning_limit < 0:
        raise ValueError("Price-behavior thresholds cannot be negative.")
    prices_by_security: dict[object, list[PriceBar]] = {}
    for row in prices:
        prices_by_security.setdefault(row.security_id, []).append(row)
    for rows in prices_by_security.values():
        rows.sort(key=lambda row: row.trading_date)

    events_by_security: dict[object, list[DividendEvent]] = {}
    for event in dividends:
        events_by_security.setdefault(event.security_id, []).append(event)
    for rows in events_by_security.values():
        rows.sort(key=lambda row: row.ex_date)

    events_without_price_window = 0
    events_with_price_response = 0
    currency_mismatch_events = 0
    large_unmatched_drop_count = 0
    warnings: list[str] = []
    for security_id, event_rows in events_by_security.items():
        price_rows = prices_by_security.get(security_id, [])
        dates = [row.trading_date for row in price_rows]
        for event in event_rows:
            index = bisect_left(dates, event.ex_date)
            if index == 0 or index == len(price_rows):
                events_without_price_window += 1
                continue
            previous = price_rows[index - 1]
            current = price_rows[index]
            if current.trading_date > event.ex_date and (current.trading_date - event.ex_date).days > event_window_days:
                events_without_price_window += 1
                continue
            if event.currency != current.currency:
                currency_mismatch_events += 1
                continue
            comparable_amount = event.amount
            observed_drop = previous.close - current.close
            tolerance = max(comparable_amount * Decimal("0.75"), previous.close * Decimal("0.02"))
            if comparable_amount > 0 and observed_drop > 0 and abs(observed_drop - comparable_amount) <= tolerance:
                events_with_price_response += 1

    for security_id, price_rows in prices_by_security.items():
        event_dates = [event.ex_date for event in events_by_security.get(security_id, [])]
        for previous, current in pairwise(price_rows):
            if previous.close <= 0:
                continue
            drop = (previous.close - current.close) / previous.close
            if drop < large_drop_threshold:
                continue
            if not any(abs((event_date - current.trading_date).days) <= event_window_days for event_date in event_dates):
                large_unmatched_drop_count += 1
                if len(warnings) < warning_limit:
                    warnings.append(
                        f"{security_id}: {drop:.2%} price drop on {current.trading_date} has no nearby dividend event."
                    )

    return DividendPriceBehaviorReport(
        event_count=len(dividends),
        comparable_event_count=(
            len(dividends) - events_without_price_window - currency_mismatch_events
        ),
        events_without_price_window=events_without_price_window,
        events_with_price_response=events_with_price_response,
        large_price_drops_without_dividend=large_unmatched_drop_count,
        currency_mismatch_events=currency_mismatch_events,
        warnings=warnings,
    )


def coverage_metric_snapshot(report: DividendCoverageReport) -> dict[str, int | float | str]:
    """Extract stable metrics for longitudinal coverage monitoring."""

    summary = report.summary
    return {
        "generated_at": report.generated_at.isoformat(),
        "tracked_securities": int(summary.get("tracked_securities", 0)),
        "distributing": int(summary.get("distributing", 0)),
        "accumulating": int(summary.get("accumulating", 0)),
        "non_distributing": int(summary.get("non_distributing", 0)),
        "unknown_policy": int(summary.get("unknown_policy", 0)),
        "data_available": int(summary.get("status_data_available", 0)),
        "data_available_policy_unknown": int(
            summary.get("status_data_available_policy_unknown", 0)
        ),
        "coverage_percent": float(summary.get("dividend_data_coverage_percent", 0.0)),
        "provider_errors": int(summary.get("status_provider_error", 0)),
        "event_rows": int(summary.get("dividend_event_rows", 0)),
        "securities_with_events": int(summary.get("securities_with_dividend_events", 0)),
    }


def load_coverage_history(path: str | Path) -> list[dict[str, int | float | str]]:
    """Load persisted coverage snapshots, returning an empty history if absent."""

    target = Path(path)
    if not target.exists():
        return []
    payload = json.loads(target.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        snapshots = payload.get("snapshots", [])
    else:
        snapshots = payload
    if not isinstance(snapshots, list) or not all(isinstance(item, dict) for item in snapshots):
        raise ValueError(f"Invalid dividend coverage history in {target}.")
    return snapshots


def record_coverage_snapshot(
    report: DividendCoverageReport,
    path: str | Path,
    *,
    coverage_drop_threshold_pct: float = 5.0,
) -> list[str]:
    """Append a report snapshot and return warnings for material deterioration.

    The comparison is intentionally conservative: it warns on large coverage
    drops, new provider failures, or event-row loss, while leaving the
    decision to fail a deployment to the caller.
    """

    target = Path(path)
    history = load_coverage_history(target)
    current = coverage_metric_snapshot(report)
    warnings: list[str] = []
    if history:
        previous = history[-1]
        previous_coverage = float(previous.get("coverage_percent", 0.0))
        current_coverage = float(current["coverage_percent"])
        if previous_coverage - current_coverage >= coverage_drop_threshold_pct:
            warnings.append(
                f"Dividend coverage fell from {previous_coverage:.2f}% to "
                f"{current_coverage:.2f}% (threshold {coverage_drop_threshold_pct:.2f}%)."
            )
        previous_errors = int(previous.get("provider_errors", 0))
        current_errors = int(current["provider_errors"])
        if current_errors > previous_errors:
            warnings.append(
                f"Dividend provider errors increased from {previous_errors} to {current_errors}."
            )
        previous_rows = int(previous.get("event_rows", 0))
        current_rows = int(current["event_rows"])
        if current_rows < previous_rows:
            warnings.append(
                f"Dividend archive row count fell from {previous_rows} to {current_rows}."
            )
    history.append(current)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.write_text(
        json.dumps({"schema_version": 1, "snapshots": history}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(target)
    return warnings


def _archive_stats(store: ParquetStore) -> tuple[dict[str, dict[str, object]], set[str]]:
    stats: dict[str, dict[str, object]] = {}
    for path in sorted((store.root / "dividends").glob("year=*.parquet")):
        parquet = pq.ParquetFile(path)
        columns = [
            column
            for column in ("security_id", "ex_date", "amount", "currency", "source")
            if column in parquet.schema_arrow.names
        ]
        if "security_id" not in columns or "ex_date" not in columns:
            continue
        for batch in parquet.iter_batches(columns=columns, batch_size=50_000):
            payload = batch.to_pylist()
            for row in payload:
                security_id = str(row["security_id"])
                record = stats.setdefault(
                    security_id,
                    {
                        "event_count": 0,
                        "first_event_date": row["ex_date"],
                        "last_event_date": row["ex_date"],
                        "sources": set(),
                        "event_currencies": set(),
                        "event_dates": [],
                        "amounts": [],
                    },
                )
                record["event_count"] = int(record["event_count"]) + 1
                record["event_dates"].append(row["ex_date"])
                if row.get("amount") is not None:
                    record["amounts"].append(Decimal(str(row["amount"])))
                event_date = row["ex_date"]
                record["first_event_date"] = min(record["first_event_date"], event_date)
                record["last_event_date"] = max(record["last_event_date"], event_date)
                if row.get("source"):
                    record["sources"].add(str(row["source"]))
                if row.get("currency"):
                    record["event_currencies"].add(str(row["currency"]))
    catalog_ids = set(stats)
    return stats, catalog_ids


def _frequency_metrics(
    stats: dict[str, dict[str, object]],
    *,
    max_gap_days: int = 550,
) -> dict[str, int]:
    """Return review metrics for unusually long gaps between cash events.

    Dividend schedules are not guaranteed to be quarterly or annual, so these
    are anomaly indicators rather than completeness failures.  They make
    sparse histories visible for targeted review without treating legitimate
    non-distributors as broken.
    """

    securities_with_events = 0
    securities_with_long_gap = 0
    largest_gap = 0
    for record in stats.values():
        metrics = _event_history_metrics(record)
        dates = metrics["dates"]
        if not dates:
            continue
        securities_with_events += 1
        gaps = metrics["gaps"]
        if gaps:
            largest_gap = max(largest_gap, max(gaps))
            if max(gaps) > max_gap_days:
                securities_with_long_gap += 1
    return {
        "securities_with_dividend_events": securities_with_events,
        "securities_with_long_dividend_gap": securities_with_long_gap,
        "max_inter_event_gap_days": largest_gap,
        "dividend_gap_review_threshold_days": max_gap_days,
    }


def _event_history_metrics(record: dict[str, object]) -> dict[str, object]:
    dates = sorted(set(record.get("event_dates", [])))
    gaps = [(right - left).days for left, right in pairwise(dates)]
    amounts = [amount for amount in record.get("amounts", []) if isinstance(amount, Decimal)]
    return {
        "dates": dates,
        "gaps": gaps,
        "average_gap": sum(gaps) / len(gaps) if gaps else None,
        "median_amount": median(amounts) if amounts else None,
        "largest_amount": max(amounts) if amounts else None,
        "smallest_amount": min(amounts) if amounts else None,
        "longest_gap": max(gaps, default=0),
    }


def load_coverage_report(path: str | Path) -> DividendCoverageReport | None:
    target = Path(path)
    if not target.exists():
        return None
    return DividendCoverageReport.model_validate_json(target.read_text(encoding="utf-8"))


def write_coverage_report(report: DividendCoverageReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    temporary.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(target)


def _status_for(
    security: Security,
    event_count: int,
    previous: DividendCoverageRecord | None,
) -> str:
    if security.distribution_policy == DistributionPolicy.ACCUMULATING:
        return DividendCoverageStatus.KNOWN_ACCUMULATING
    if security.distribution_policy == DistributionPolicy.NON_DISTRIBUTING:
        return DividendCoverageStatus.KNOWN_NON_DISTRIBUTING
    if event_count:
        return (
            DividendCoverageStatus.DATA_AVAILABLE
            if security.distribution_policy == DistributionPolicy.DISTRIBUTING
            else DividendCoverageStatus.DATA_AVAILABLE_POLICY_UNKNOWN
        )
    if previous and previous.coverage_status == DividendCoverageStatus.PROVIDER_ERROR:
        return DividendCoverageStatus.PROVIDER_ERROR
    if previous and previous.provider_query_succeeded:
        return (
            DividendCoverageStatus.KNOWN_DISTRIBUTING_WITH_NO_EVENTS
            if security.distribution_policy == DistributionPolicy.DISTRIBUTING
            else DividendCoverageStatus.UNKNOWN
        )
    if security.distribution_policy == DistributionPolicy.DISTRIBUTING:
        return DividendCoverageStatus.DIVIDEND_DATA_MISSING
    return DividendCoverageStatus.UNKNOWN


def build_dividend_coverage(
    *,
    catalog: UniverseCatalog,
    store: ParquetStore,
    coverage_path: str | Path | None = None,
    generated_at: datetime | None = None,
) -> DividendCoverageReport:
    """Build a compact all-security coverage matrix from local state."""

    previous_report = load_coverage_report(coverage_path) if coverage_path else None
    previous = {
        str(record.security_id): record for record in previous_report.securities
    } if previous_report else {}
    entries: dict[str, tuple[Security, date]] = {}
    for entry in catalog.securities:
        key = str(entry.security.security_id)
        current = entries.get(key)
        if current is None or entry.effective_from < current[1]:
            entries[key] = (entry.security, entry.effective_from)

    stats, archive_ids = _archive_stats(store)
    records: list[DividendCoverageRecord] = []
    for security_id, (security, effective_from) in entries.items():
        event_stats = stats.get(security_id, {})
        event_count = int(event_stats.get("event_count", 0))
        event_metrics = _event_history_metrics(event_stats)
        prior = previous.get(security_id)
        warnings = list(prior.warnings) if prior else []
        event_currencies = sorted(event_stats.get("event_currencies", set()))
        if security.distribution_policy == DistributionPolicy.ACCUMULATING and event_count:
            warnings.append("Dividend rows exist but are not investor cash distributions for an accumulating security.")
        if security.distribution_policy == DistributionPolicy.NON_DISTRIBUTING and event_count:
            warnings.append("Dividend rows exist but this security is marked non-distributing; review the policy.")
        if any(currency != security.currency for currency in event_currencies):
            warnings.append(
                "At least one dividend event currency differs from the security currency; FX conversion is required."
            )
        records.append(
            DividendCoverageRecord(
                security_id=security.security_id,
                ticker=security.ticker,
                asset_type=security.asset_type.value,
                exchange=security.exchange,
                currency=security.currency,
                distribution_policy=security.distribution_policy,
                # Catalog membership dates are not necessarily security
                # inception dates; current-listing snapshots commonly use the
                # snapshot date.  Keep the required floor conservative and
                # let the provider's first event date reveal actual history.
                required_start_date=catalog.history_start,
                event_count=event_count,
                first_event_date=event_stats.get("first_event_date"),
                last_event_date=event_stats.get("last_event_date"),
                average_inter_event_gap_days=event_metrics["average_gap"],
                median_dividend_amount=event_metrics["median_amount"],
                largest_dividend_amount=event_metrics["largest_amount"],
                smallest_dividend_amount=event_metrics["smallest_amount"],
                longest_inter_event_gap_days=event_metrics["longest_gap"],
                queried_from=prior.queried_from if prior else None,
                queried_through=prior.queried_through if prior else None,
                provider_query_succeeded=prior.provider_query_succeeded if prior else False,
                coverage_status=_status_for(security, event_count, prior),
                sources=sorted(event_stats.get("sources", set())),
                event_currencies=event_currencies,
                last_attempt_at=prior.last_attempt_at if prior else None,
                error=prior.error if prior else None,
                warnings=sorted(set(warnings)),
            )
        )

    status_counts = Counter(record.coverage_status for record in records)
    policy_counts = Counter(record.distribution_policy.value for record in records)
    distributing = policy_counts[DistributionPolicy.DISTRIBUTING.value]
    covered = status_counts[DividendCoverageStatus.DATA_AVAILABLE]
    summary: dict[str, int | float] = {
        "tracked_securities": len(records),
        "distributing": distributing,
        "accumulating": policy_counts[DistributionPolicy.ACCUMULATING.value],
        "non_distributing": policy_counts[DistributionPolicy.NON_DISTRIBUTING.value],
        "unknown_policy": policy_counts[DistributionPolicy.UNKNOWN.value],
        "dividend_data_available": covered,
        "dividend_data_coverage_percent": round(100 * covered / distributing, 2) if distributing else 100.0,
        "dividend_event_rows": sum(record.event_count for record in records),
        "orphan_event_security_ids": len(archive_ids - set(entries)),
    }
    summary.update(_frequency_metrics(stats))
    for status, count in sorted(status_counts.items()):
        summary[f"status_{status}"] = count
    return DividendCoverageReport(
        generated_at=generated_at or datetime.now(UTC),
        history_start=catalog.history_start,
        summary=summary,
        securities=sorted(records, key=lambda record: record.ticker),
    )


def coverage_record_map(report: DividendCoverageReport) -> dict[str, DividendCoverageRecord]:
    return {str(record.security_id): record for record in report.securities}
