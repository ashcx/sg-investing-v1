"""Durable, per-security state for price-history backfills.

The backfill must be restart-safe: a process interruption must never turn an
unknown ticker into a silently skipped ticker, nor cause already-stored
histories to be downloaded again just because another market closed later.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from itertools import islice
from pathlib import Path
from typing import Iterable, Mapping

import pyarrow.parquet as pq

from sg_investing.data.providers.base import MarketDataProvider
from sg_investing.data.storage import ParquetStore
from sg_investing.models import Security


STATE_VERSION = 2
MAX_ATTEMPTS = 3
MAX_ACTIVE_PRICE_STALENESS_BUSINESS_DAYS = 7
MIN_ACTIVE_PRICE_BARS = 20
MAX_INTERNAL_PRICE_GAP_SESSIONS = 5


def batches(items: Iterable[Security], size: int) -> Iterable[list[Security]]:
    """Yield fixed-size batches without materialising an extra copy."""

    iterator = iter(items)
    while batch := list(islice(iterator, size)):
        yield batch


def _atomic_json_write(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def scan_price_coverage(store: ParquetStore) -> dict[str, dict[str, object]]:
    """Return stored coverage and market-relative gap stats for each security.

    The first pass counts rows and builds the observed session calendar for
    each market.  The second pass uses only the security/date columns to
    calculate ordering and internal gaps.  This is intentionally local and
    streaming so reconciliation remains practical for the full store.
    """

    coverage: dict[str, dict[str, object]] = {}
    market_dates: dict[str, set[date]] = defaultdict(set)
    paths = sorted((store.root / "prices").glob("market=*/year=*.parquet"))
    for path in paths:
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(
            columns=["security_id", "trading_date"], batch_size=50_000
        ):
            for security_id, trading_date in zip(
                batch.column(0).to_pylist(),
                batch.column(1).to_pylist(),
                strict=True,
            ):
                market = path.parent.name.split("=", 1)[1].upper()
                if trading_date is not None:
                    market_dates[market].add(trading_date)
                if security_id is None or trading_date is None:
                    continue
                record = coverage.setdefault(
                    security_id,
                    {"bars": 0, "first_price_date": trading_date, "last_price_date": trading_date},
                )
                record["bars"] = int(record["bars"]) + 1
                if trading_date < record["first_price_date"]:
                    record["first_price_date"] = trading_date
                if trading_date > record["last_price_date"]:
                    record["last_price_date"] = trading_date

    sessions_by_market = {
        market: tuple(sorted(sessions)) for market, sessions in market_dates.items()
    }
    session_indexes = {
        market: {session: index for index, session in enumerate(sessions)}
        for market, sessions in sessions_by_market.items()
    }
    previous_by_security: dict[tuple[str, str], date] = {}
    gap_totals: dict[str, int] = defaultdict(int)
    max_gaps: dict[str, int] = defaultdict(int)
    unsorted_rows: dict[str, int] = defaultdict(int)
    for path in paths:
        market = path.parent.name.split("=", 1)[1].upper()
        index_by_date = session_indexes.get(market, {})
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(
            columns=["security_id", "trading_date"], batch_size=100_000
        ):
            for security_id, trading_date in zip(
                batch.column(0).to_pylist(),
                batch.column(1).to_pylist(),
                strict=True,
            ):
                if security_id is None or trading_date is None:
                    continue
                key = (security_id, market)
                previous = previous_by_security.get(key)
                if previous is not None:
                    if trading_date < previous:
                        unsorted_rows[security_id] += 1
                    previous_index = index_by_date.get(previous)
                    current_index = index_by_date.get(trading_date)
                    if (
                        trading_date > previous
                        and previous_index is not None
                        and current_index is not None
                        and current_index - previous_index > 1
                    ):
                        gap = current_index - previous_index - 1
                        gap_totals[security_id] += gap
                        max_gaps[security_id] = max(max_gaps[security_id], gap)
                previous_by_security[key] = trading_date

    for security_id, record in coverage.items():
        record["internal_gap_sessions"] = gap_totals[security_id]
        record["max_internal_gap_sessions"] = max_gaps[security_id]
        record["unsorted_rows"] = unsorted_rows[security_id]
    return coverage


def _business_days_between(start: date, end: date) -> int:
    """Count weekday sessions after ``start`` through ``end`` inclusively."""

    return sum(
        current.weekday() < 5
        for current in (start + timedelta(days=offset) for offset in range(1, (end - start).days + 1))
    )


def _coverage_status(
    coverage: Mapping[str, object], *, as_of: date
) -> tuple[str, str | None]:
    """Classify active-listing coverage before it can be called stored."""

    bars = int(coverage["bars"])
    last_price_date = coverage["last_price_date"]
    assert isinstance(last_price_date, date)
    if bars < MIN_ACTIVE_PRICE_BARS:
        return (
            "incomplete",
            f"Only {bars} stored price bars; at least {MIN_ACTIVE_PRICE_BARS} are required for an active security.",
        )
    max_internal_gap = int(coverage.get("max_internal_gap_sessions", 0))
    if max_internal_gap > MAX_INTERNAL_PRICE_GAP_SESSIONS:
        total_internal_gap = int(coverage.get("internal_gap_sessions", max_internal_gap))
        return (
            "incomplete",
            f"Stored price history contains {total_internal_gap} missing market session(s); "
            f"largest internal gap is {max_internal_gap}, above the allowed maximum of "
            f"{MAX_INTERNAL_PRICE_GAP_SESSIONS}.",
        )
    stale_days = _business_days_between(last_price_date, as_of)
    if stale_days > MAX_ACTIVE_PRICE_STALENESS_BUSINESS_DAYS:
        return (
            "incomplete",
            f"Last stored price date {last_price_date.isoformat()} is {stale_days} business days before "
            f"as-of {as_of.isoformat()}; allowed maximum is {MAX_ACTIVE_PRICE_STALENESS_BUSINESS_DAYS}.",
        )
    return "stored", None


def _new_record(
    security: Security,
    coverage: Mapping[str, object] | None = None,
    *,
    as_of: date | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "ticker": security.ticker,
        "market": security.market,
        "attempts": 0,
        "last_error": None,
        "last_attempt_at": None,
        "warning": None,
    }
    if coverage:
        status, warning = _coverage_status(coverage, as_of=as_of) if as_of else ("stored", None)
        record.update(
            {
                "status": status,
                "bars": int(coverage["bars"]),
                "first_price_date": str(coverage["first_price_date"]),
                "last_price_date": str(coverage["last_price_date"]),
                "internal_gap_sessions": int(coverage.get("internal_gap_sessions", 0)),
                "max_internal_gap_sessions": int(coverage.get("max_internal_gap_sessions", 0)),
                "unsorted_rows": int(coverage.get("unsorted_rows", 0)),
                "warning": warning,
            }
        )
    else:
        record.update(
            {
                "status": "pending",
                "bars": 0,
                "first_price_date": None,
                "last_price_date": None,
                "internal_gap_sessions": 0,
                "max_internal_gap_sessions": 0,
                "unsorted_rows": 0,
            }
        )
    return record


def load_or_reconcile_state(
    path: Path,
    securities: Iterable[Security],
    coverage: Mapping[str, Mapping[str, object]],
    *,
    as_of: date | None = None,
) -> dict[str, object]:
    """Load state and reconcile it against the canonical store and catalog."""

    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") == 1:
            payload["version"] = STATE_VERSION
        elif payload.get("version") != STATE_VERSION:
            raise RuntimeError(f"Unsupported backfill state version in {path}.")
    else:
        payload = {"version": STATE_VERSION, "securities": {}}
    records = payload.setdefault("securities", {})
    if not isinstance(records, dict):
        raise RuntimeError(f"Invalid backfill state in {path}.")

    catalog_ids: set[str] = set()
    for security in securities:
        security_id = str(security.security_id)
        catalog_ids.add(security_id)
        stored = coverage.get(security_id)
        existing = records.get(security_id)
        if stored:
            # A crash after writing Parquet but before state persistence is
            # safely recovered here without another download.
            fresh = _new_record(security, stored, as_of=as_of)
            fresh["in_current_catalog"] = True
            if isinstance(existing, dict):
                fresh["attempts"] = int(existing.get("attempts", 0))
                fresh["last_attempt_at"] = existing.get("last_attempt_at")
                if fresh["warning"] is None:
                    fresh["warning"] = existing.get("warning")
            records[security_id] = fresh
        elif isinstance(existing, dict):
            # A previously stored record can become stale if the canonical
            # partition is replaced or removed.  Do not let old bar counts
            # or a former ``stored`` status survive that reconciliation.
            existing["ticker"] = security.ticker
            existing["market"] = security.market
            existing["in_current_catalog"] = True
            existing["bars"] = 0
            existing["first_price_date"] = None
            existing["last_price_date"] = None
            existing["internal_gap_sessions"] = 0
            existing["max_internal_gap_sessions"] = 0
            existing["unsorted_rows"] = 0
            if existing.get("status") == "stored":
                existing["status"] = "pending"
                existing["warning"] = "No stored price rows were found during reconciliation."
            existing.setdefault("status", "pending")
            existing.setdefault("attempts", 0)
            existing.setdefault("last_error", None)
            existing.setdefault("last_attempt_at", None)
            existing.setdefault("warning", None)
        else:
            records[security_id] = _new_record(security, as_of=as_of)

    for security_id, record in records.items():
        if security_id not in catalog_ids and isinstance(record, dict):
            record["in_current_catalog"] = False
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    return payload


def reconcile_price_backfill_state(
    *,
    securities: Iterable[Security],
    store: ParquetStore,
    state_path: Path,
    summary_path: Path,
    as_of: date,
) -> dict[str, object]:
    """Rebuild persisted coverage fields from the canonical Parquet store.

    This is a local-only maintenance operation.  It does not download data
    or modify price partitions; it corrects derived state after interrupted,
    overlapping, or otherwise stale backfill runs.
    """

    security_list = list({str(security.security_id): security for security in securities}.values())
    state = load_or_reconcile_state(
        state_path,
        security_list,
        scan_price_coverage(store),
        as_of=as_of,
    )
    run = {"attempted": 0, "succeeded": 0, "failed": 0, "rows_written": 0, "batches_completed": 0}
    _atomic_json_write(state_path, state)
    summary = _state_summary(state, run=run)
    _atomic_json_write(summary_path, summary)
    return summary


def _state_summary(state: Mapping[str, object], *, run: Mapping[str, int]) -> dict[str, object]:
    records = state["securities"]
    assert isinstance(records, dict)
    status_counts = Counter(
        str(record.get("status", "pending"))
        for record in records.values()
        if isinstance(record, dict) and record.get("in_current_catalog", True)
    )
    return {
        "as_of": date.today().isoformat(),
        "state_file": "price_backfill_state.json",
        "total_securities": sum(status_counts.values()),
        "by_status": dict(sorted(status_counts.items())),
        "run": dict(run),
        "updated_at": state.get("updated_at"),
    }


def backfill_missing_prices(
    *,
    securities: Iterable[Security],
    store: ParquetStore,
    provider: MarketDataProvider,
    start_date: date,
    end_date: date,
    workers: int,
    state_path: Path,
    summary_path: Path,
    batch_size: int = 40,
) -> dict[str, object]:
    """Download missing prices and persist an auditable outcome per security.

    Existing stored histories are recognised from Parquet. Failed requests are
    retried up to ``MAX_ATTEMPTS`` across separate process invocations, then
    retained as explicit ``unavailable`` records instead of disappearing.
    """

    security_list = list({str(security.security_id): security for security in securities}.values())
    coverage = scan_price_coverage(store)
    state = load_or_reconcile_state(state_path, security_list, coverage, as_of=end_date)
    records = state["securities"]
    assert isinstance(records, dict)
    candidates = [
        security
        for security in security_list
        if isinstance(records.get(str(security.security_id)), dict)
        and records[str(security.security_id)]["status"] in {"pending", "failed", "incomplete"}
        and int(records[str(security.security_id)]["attempts"]) < MAX_ATTEMPTS
    ]
    by_market: dict[str, list[Security]] = defaultdict(list)
    for security in candidates:
        by_market[security.market].append(security)
    run = {"attempted": 0, "succeeded": 0, "failed": 0, "rows_written": 0, "batches_completed": 0}
    _atomic_json_write(state_path, state)
    _atomic_json_write(summary_path, _state_summary(state, run=run))

    for market, market_securities in sorted(by_market.items()):
        for batch in batches(sorted(market_securities, key=lambda security: security.ticker), batch_size):
            rows_by_security, errors, warnings = provider.get_prices_batch(
                batch, start_date, end_date, workers=workers
            )
            rows = [row for security_rows in rows_by_security.values() for row in security_rows]
            if rows:
                store.upsert_prices(market=market, rows=rows, pipeline_version="backfill-v2")
            attempted_at = datetime.now(timezone.utc).isoformat()
            for security in batch:
                security_id = str(security.security_id)
                record = records[security_id]
                assert isinstance(record, dict)
                record["attempts"] = int(record["attempts"]) + 1
                record["last_attempt_at"] = attempted_at
                if security.security_id in rows_by_security:
                    result_rows = rows_by_security[security.security_id]
                    previous_coverage = coverage.get(security_id)
                    fetched_coverage = {
                        "bars": (int(previous_coverage["bars"]) if previous_coverage else 0) + len(result_rows),
                        "first_price_date": min(
                            [row.trading_date for row in result_rows]
                            + ([previous_coverage["first_price_date"]] if previous_coverage else [])
                        ),
                        "last_price_date": max(
                            [row.trading_date for row in result_rows]
                            + ([previous_coverage["last_price_date"]] if previous_coverage else [])
                        ),
                    }
                    coverage[security_id] = fetched_coverage
                    status, completeness_warning = _coverage_status(fetched_coverage, as_of=end_date)
                    record.update(
                        {
                            "status": status,
                            "bars": fetched_coverage["bars"],
                            "first_price_date": str(fetched_coverage["first_price_date"]),
                            "last_price_date": str(fetched_coverage["last_price_date"]),
                            "last_error": None,
                            "warning": completeness_warning or warnings.get(security.security_id),
                        }
                    )
                    run["succeeded"] += status == "stored"
                    run["rows_written"] += len(result_rows)
                else:
                    record["last_error"] = errors.get(
                        security.security_id, "Provider did not return an outcome for this security."
                    )
                    record["warning"] = warnings.get(security.security_id)
                    record["status"] = (
                        "unavailable" if int(record["attempts"]) >= MAX_ATTEMPTS else "failed"
                    )
                    run["failed"] += 1
                run["attempted"] += 1
            run["batches_completed"] += 1
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            _atomic_json_write(state_path, state)
            _atomic_json_write(summary_path, _state_summary(state, run=run))
    # The provider result count is not authoritative: it can overlap rows
    # already present in Parquet, and the store deduplicates by
    # (security_id, trading_date).  Reconcile once more after all writes so
    # persisted bars, dates, and quality status describe the canonical store.
    coverage = scan_price_coverage(store)
    state = load_or_reconcile_state(state_path, security_list, coverage, as_of=end_date)
    _atomic_json_write(state_path, state)
    _atomic_json_write(summary_path, _state_summary(state, run=run))
    return _state_summary(state, run=run)
