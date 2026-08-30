"""Restart-safe dividend backfill and incremental refresh orchestration."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from itertools import islice
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from sg_investing.data.dividend_quality import (
    DividendCoverageReport,
    DividendCoverageStatus,
    build_dividend_coverage,
    coverage_record_map,
    write_coverage_report,
)
from sg_investing.data.providers.base import MarketDataProvider
from sg_investing.data.storage import ParquetStore
from sg_investing.data.validation import validate_dividends
from sg_investing.models import DistributionPolicy, DividendEvent, Security
from sg_investing.universe.catalog import UniverseCatalog


class DividendBackfillResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    security_id: str
    ticker: str
    start_date: date
    end_date: date
    status: str
    rows_fetched: int = Field(ge=0)
    error: str | None = None


def _unique_securities(catalog: UniverseCatalog) -> dict[str, tuple[Security, date]]:
    result: dict[str, tuple[Security, date]] = {}
    for entry in catalog.securities:
        key = str(entry.security.security_id)
        current = result.get(key)
        if current is None or entry.effective_from < current[1]:
            result[key] = (entry.security, entry.effective_from)
    return result


def _fetch_dividends(
    provider: MarketDataProvider,
    security: Security,
    start_date: date,
    end_date: date,
    retries: int,
) -> tuple[list[DividendEvent], str | None]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            rows = list(provider.get_dividends(security, start_date, end_date))
            for row in rows:
                if row.security_id != security.security_id:
                    raise ValueError("Provider returned a dividend for another security.")
                if not start_date <= row.ex_date <= end_date:
                    raise ValueError("Provider returned a dividend outside the requested range.")
            validation = validate_dividends(rows)
            if not validation.is_valid:
                raise ValueError("; ".join(validation.errors))
            return rows, None
        except Exception as error:  # noqa: BLE001 - retain failure per security
            last_error = error
            if attempt < retries:
                continue
    return [], str(last_error or "Unknown provider error")


def _query_start(
    security: Security,
    effective_from: date,
    previous: object | None,
    start_floor: date,
    reconciliation_days: int,
    *,
    full_history: bool = False,
) -> date:
    # Membership snapshots are not listing dates.  A current-universe import
    # can have an ``effective_from`` of today even when the security has a
    # much older provider history (for example, a re-imported listing).  The
    # provider's bounded query from the global history floor is therefore the
    # conservative way to capture "since 2000 or inception" data.
    start = start_floor
    if not full_history and previous is not None and getattr(previous, "provider_query_succeeded", False):
        through = getattr(previous, "queried_through", None)
        if isinstance(through, date):
            start = max(start, through - timedelta(days=reconciliation_days))
    return start


def _result(
    security: Security,
    start_date: date,
    end_date: date,
    *,
    status: str,
    rows_fetched: int = 0,
    error: str | None = None,
) -> DividendBackfillResult:
    return DividendBackfillResult(
        security_id=str(security.security_id),
        ticker=security.ticker,
        start_date=start_date,
        end_date=end_date,
        status=status,
        rows_fetched=rows_fetched,
        error=error,
    )


def backfill_dividends(
    *,
    catalog: UniverseCatalog,
    store: ParquetStore,
    provider: MarketDataProvider,
    coverage_path: str | Path,
    end_date: date,
    start_floor: date | None = None,
    reconciliation_days: int = 7,
    workers: int = 4,
    retries: int = 2,
    include_unknown: bool = True,
    tickers: Iterable[str] | None = None,
    max_securities: int | None = None,
    full_history: bool = False,
    retry_provider_errors: bool = False,
    refresh_existing_events: bool = False,
) -> tuple[DividendCoverageReport, list[DividendBackfillResult]]:
    """Fetch, validate, merge, and report dividend history for the catalog.

    Accumulating securities are intentionally skipped.  Unknown-policy
    securities are fetched when ``include_unknown`` is true, but an empty
    response remains ``unknown`` rather than being promoted to zero dividends.
    All Parquet writes happen after provider results are collected, avoiding
    concurrent partition races.
    """

    start_floor = start_floor or catalog.history_start
    initial_report = build_dividend_coverage(
        catalog=catalog,
        store=store,
        coverage_path=coverage_path,
    )
    previous = coverage_record_map(initial_report)
    selected_tickers = {ticker.upper() for ticker in tickers} if tickers else None
    securities = [
        (security, effective_from)
        for security, effective_from in _unique_securities(catalog).values()
        if selected_tickers is None or security.ticker.upper() in selected_tickers
    ]
    if retry_provider_errors:
        securities = [
            (security, effective_from)
            for security, effective_from in securities
            if previous.get(str(security.security_id))
            and previous[str(security.security_id)].coverage_status
            == DividendCoverageStatus.PROVIDER_ERROR
        ]
    if refresh_existing_events:
        securities = [
            (security, effective_from)
            for security, effective_from in securities
            if previous.get(str(security.security_id))
            and previous[str(security.security_id)].event_count > 0
        ]
    if max_securities is not None:
        securities = list(islice(securities, max_securities))

    results: list[DividendBackfillResult] = []
    jobs: dict[object, tuple[Security, date, date]] = {}
    all_rows: list[DividendEvent] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        for security, effective_from in securities:
            start_date = _query_start(
                security,
                effective_from,
                previous.get(str(security.security_id)),
                start_floor,
                reconciliation_days,
                full_history=full_history,
            )
            if security.distribution_policy in {
                DistributionPolicy.ACCUMULATING,
                DistributionPolicy.NON_DISTRIBUTING,
            }:
                results.append(
                    _result(
                        security,
                        start_date,
                        end_date,
                        status=(
                            DividendCoverageStatus.KNOWN_ACCUMULATING
                            if security.distribution_policy == DistributionPolicy.ACCUMULATING
                            else DividendCoverageStatus.KNOWN_NON_DISTRIBUTING
                        ),
                    )
                )
                continue
            if security.distribution_policy == DistributionPolicy.UNKNOWN and not include_unknown:
                results.append(
                    _result(
                        security,
                        start_date,
                        end_date,
                        status=DividendCoverageStatus.UNKNOWN,
                        error="Distribution policy is unknown; provider query was skipped.",
                    )
                )
                continue
            future = executor.submit(
                _fetch_dividends,
                provider,
                security,
                start_date,
                end_date,
                retries,
            )
            jobs[future] = (security, start_date, end_date)

        for future in as_completed(jobs):
            security, start_date, requested_end = jobs[future]
            try:
                rows, error = future.result()
            except Exception as error:  # noqa: BLE001 - defensive worker boundary
                rows, error = [], str(error)
            if error:
                results.append(
                    _result(
                        security,
                        start_date,
                        requested_end,
                        status=DividendCoverageStatus.PROVIDER_ERROR,
                        error=error,
                    )
                )
            else:
                all_rows.extend(rows)
                results.append(
                    _result(
                        security,
                        start_date,
                        requested_end,
                        status=DividendCoverageStatus.DATA_AVAILABLE if rows else "query_succeeded_empty",
                        rows_fetched=len(rows),
                    )
                )

    if all_rows:
        store.upsert_dividends(all_rows)

    generated_at = datetime.now(UTC)
    report = build_dividend_coverage(
        catalog=catalog,
        store=store,
        coverage_path=coverage_path,
        generated_at=generated_at,
    )
    records = coverage_record_map(report)
    for result in results:
        record = records[result.security_id]
        queried = result.status not in {
            DividendCoverageStatus.UNKNOWN,
            DividendCoverageStatus.KNOWN_ACCUMULATING,
            DividendCoverageStatus.KNOWN_NON_DISTRIBUTING,
        }
        updates = {
                "provider_query_succeeded": queried and result.status != DividendCoverageStatus.PROVIDER_ERROR,
            "last_attempt_at": generated_at if queried else record.last_attempt_at,
            "error": result.error if queried else record.error,
        }
        if queried:
            updates.update(
                {
                    "queried_from": result.start_date,
                    "queried_through": result.end_date,
                }
            )
        warnings = list(record.warnings)
        if result.status == "query_succeeded_empty":
            if record.event_count:
                updates["coverage_status"] = (
                    DividendCoverageStatus.DATA_AVAILABLE
                    if record.distribution_policy == DistributionPolicy.DISTRIBUTING
                    else DividendCoverageStatus.DATA_AVAILABLE_POLICY_UNKNOWN
                )
            else:
                updates["coverage_status"] = (
                    DividendCoverageStatus.KNOWN_DISTRIBUTING_WITH_NO_EVENTS
                    if record.distribution_policy == DistributionPolicy.DISTRIBUTING
                    else DividendCoverageStatus.UNKNOWN
                )
                warnings.append(
                    "Provider returned no dividend events; this is not proof that the security pays no dividends."
                )
        elif result.status == DividendCoverageStatus.PROVIDER_ERROR:
            updates["coverage_status"] = DividendCoverageStatus.PROVIDER_ERROR
        elif result.status == DividendCoverageStatus.KNOWN_ACCUMULATING:
            updates["coverage_status"] = DividendCoverageStatus.KNOWN_ACCUMULATING
        elif result.status == DividendCoverageStatus.KNOWN_NON_DISTRIBUTING:
            updates["coverage_status"] = DividendCoverageStatus.KNOWN_NON_DISTRIBUTING
        elif record.event_count:
            updates["coverage_status"] = (
                DividendCoverageStatus.DATA_AVAILABLE
                if record.distribution_policy == DistributionPolicy.DISTRIBUTING
                else DividendCoverageStatus.DATA_AVAILABLE_POLICY_UNKNOWN
            )
        updates["warnings"] = sorted(set(warnings))
        records[result.security_id] = record.model_copy(update=updates)

    final_records = sorted(records.values(), key=lambda item: item.ticker)
    status_counts = Counter(record.coverage_status for record in final_records)
    policy_counts = Counter(record.distribution_policy.value for record in final_records)
    distributing = policy_counts[DistributionPolicy.DISTRIBUTING.value]
    summary = {key: value for key, value in report.summary.items() if not key.startswith("status_")}
    summary.update(
        {
            "tracked_securities": len(final_records),
            "distributing": distributing,
            "accumulating": policy_counts[DistributionPolicy.ACCUMULATING.value],
            "unknown_policy": policy_counts[DistributionPolicy.UNKNOWN.value],
            "dividend_data_available": status_counts[DividendCoverageStatus.DATA_AVAILABLE],
            "dividend_data_coverage_percent": (
                round(100 * status_counts[DividendCoverageStatus.DATA_AVAILABLE] / distributing, 2)
                if distributing
                else 100.0
            ),
            "dividend_event_rows": sum(record.event_count for record in final_records),
        }
    )
    summary.update({f"status_{status}": count for status, count in sorted(status_counts.items())})
    final_report = report.model_copy(
        update={"generated_at": generated_at, "summary": summary, "securities": final_records}
    )
    write_coverage_report(final_report, coverage_path)
    return final_report, sorted(results, key=lambda item: item.ticker)
