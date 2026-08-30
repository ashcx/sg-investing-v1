"""Fast, local-only quality checks for stored price histories.

The full-universe audit intentionally works on Parquet columns rather than
constructing one ``PriceBar`` model per observation.  This keeps the audit
usable for thousands of securities and millions of rows.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


_REQUIRED_COLUMNS = (
    "security_id",
    "trading_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "currency",
    "exchange",
    "timezone",
)
_KEY_COLUMNS = ("security_id", "trading_date")
_MAX_REASONABLE_PRICE = 1_000_000


@dataclass(frozen=True)
class PriceCoverageExpectation:
    """Local expectation for one security's stored price history.

    ``expected_start`` should be a first valid trading date, not an IPO
    announcement date.  It is optional because the current security master
    does not yet store first-trading dates.  ``expected_end`` is also optional;
    when omitted, active securities are compared with the latest observed
    session for their market.
    """

    security_id: str
    market: str
    currency: str
    exchange: str
    expected_start: date | None = None
    expected_end: date | None = None
    active: bool = True


@dataclass(frozen=True)
class PriceAuditIssue:
    code: str
    message: str
    security_id: str | None = None
    market: str | None = None


@dataclass
class PriceSecurityStats:
    security_id: str
    row_count: int = 0
    first_date: date | None = None
    last_date: date | None = None
    markets: set[str] = field(default_factory=set)
    currencies: set[str | None] = field(default_factory=set)
    exchanges: set[str | None] = field(default_factory=set)
    timezones: set[str | None] = field(default_factory=set)
    duplicate_rows: int = 0
    duplicate_keys: int = 0
    invalid_ohlc_rows: int = 0
    invalid_price_rows: int = 0
    invalid_volume_rows: int = 0
    invalid_identifier_rows: int = 0
    suspicious_price_rows: int = 0
    unsorted_rows: int = 0
    internal_gap_sessions: int = 0
    max_internal_gap_sessions: int = 0


@dataclass(frozen=True)
class PriceAuditReport:
    issues: tuple[PriceAuditIssue, ...]
    security_stats: Mapping[str, PriceSecurityStats]
    market_sessions: Mapping[str, tuple[date, ...]]

    @property
    def is_valid(self) -> bool:
        return not self.issues

    def format_issues(self, *, limit: int = 100) -> str:
        """Format a bounded failure summary suitable for test output."""

        messages = [issue.message for issue in self.issues[:limit]]
        remaining = len(self.issues) - len(messages)
        if remaining > 0:
            messages.append(
                f"... and {remaining} additional issue(s); inspect the report object for details."
            )
        return "\n".join(messages)


@dataclass
class _MutableSecurityStats(PriceSecurityStats):
    """Internal mutable representation used while scanning partitions."""


def _market_from_path(path: Path) -> str:
    for part in path.parts:
        if part.startswith("market="):
            return part.split("=", 1)[1].upper()
    return ""


def _year_from_path(path: Path) -> int | None:
    stem = path.stem
    if not stem.startswith("year="):
        return None
    try:
        return int(stem.split("=", 1)[1])
    except ValueError:
        return None


def _or_masks(*masks: pa.Array) -> pa.Array:
    result = pc.fill_null(masks[0], True)
    for mask in masks[1:]:
        result = pc.or_(result, pc.fill_null(mask, True))
    return pc.fill_null(result, True)


def _bad_price_masks(table: pa.Table) -> tuple[pa.Array, pa.Array, pa.Array, pa.Array, pa.Array]:
    open_price = table["open"]
    high_price = table["high"]
    low_price = table["low"]
    close_price = table["close"]
    zero = pa.scalar(0, type=open_price.type)

    non_finite = [
        pc.invert(pc.fill_null(pc.is_finite(column), False))
        for column in (open_price, high_price, low_price, close_price)
    ]
    relationship = pc.and_(
        pc.and_(pc.less_equal(low_price, open_price), pc.less_equal(open_price, high_price)),
        pc.and_(pc.less_equal(low_price, close_price), pc.less_equal(close_price, high_price)),
    )
    bad_ohlc = _or_masks(*non_finite, pc.invert(pc.fill_null(relationship, False)))
    bad_price = _or_masks(
        bad_ohlc,
        pc.less_equal(open_price, zero),
        pc.less_equal(high_price, zero),
        pc.less_equal(low_price, zero),
        pc.less_equal(close_price, zero),
    )
    suspicious_price = _or_masks(
        pc.greater(open_price, pa.scalar(_MAX_REASONABLE_PRICE, type=open_price.type)),
        pc.greater(high_price, pa.scalar(_MAX_REASONABLE_PRICE, type=high_price.type)),
        pc.greater(low_price, pa.scalar(_MAX_REASONABLE_PRICE, type=low_price.type)),
        pc.greater(close_price, pa.scalar(_MAX_REASONABLE_PRICE, type=close_price.type)),
    )
    volume = table["volume"]
    bad_volume = _or_masks(pc.is_null(volume), pc.less(volume, pa.scalar(0, type=volume.type)))
    bad_identifier = _or_masks(
        pc.is_null(table["security_id"]),
        pc.is_null(table["trading_date"]),
        pc.is_null(table["currency"]),
        pc.is_null(table["exchange"]),
        pc.is_null(table["timezone"]),
    )
    return bad_ohlc, bad_price, bad_volume, bad_identifier, suspicious_price


def _sum_by_security(table: pa.Table, mask: pa.Array, name: str) -> dict[str | None, int]:
    values = pc.cast(mask, pa.int64())
    payload = table.select(["security_id"]).append_column(name, values)
    grouped = payload.group_by("security_id").aggregate([(name, "sum")])
    return {
        row["security_id"]: int(row[f"{name}_sum"] or 0)
        for row in grouped.to_pylist()
    }


def _stats_for(
    stats: dict[str, _MutableSecurityStats], security_id: str, market: str
) -> _MutableSecurityStats:
    item = stats.get(security_id)
    if item is None:
        item = _MutableSecurityStats(security_id=security_id)
        stats[security_id] = item
    item.markets.add(market)
    return item


def audit_price_files(
    paths: Iterable[str | Path],
    *,
    expectations: Mapping[str, PriceCoverageExpectation] | None = None,
    history_floor: date | None = None,
    start_tolerance_sessions: int = 0,
    end_tolerance_sessions: int = 5,
    max_internal_gap_sessions: int = 5,
) -> PriceAuditReport:
    """Audit stored price partitions in two streaming passes.

    The first pass reads each partition once to validate values and build
    compact per-security summaries.  The second pass reads only the two key
    columns to check ordering and gaps against the market-session calendar
    observed in the same local files.  No network or provider calls occur.

    Missing-session checks are deliberately market-relative: a date observed
    for at least one security in a market is treated as an observed market
    session.  This avoids a hard-coded exchange calendar, but cannot detect a
    market-wide missing date without an external calendar.
    """

    if (
        start_tolerance_sessions < 0
        or end_tolerance_sessions < 0
        or max_internal_gap_sessions < 0
    ):
        raise ValueError("Session tolerances cannot be negative.")

    file_paths = sorted(Path(path) for path in paths)
    expectations = expectations or {}
    stats: dict[str, _MutableSecurityStats] = {}
    market_dates: dict[str, set[date]] = defaultdict(set)
    issues: list[PriceAuditIssue] = []
    global_invalid: dict[str, int] = defaultdict(int)
    seen_unknown: set[str] = set()

    for path in file_paths:
        market = _market_from_path(path)
        if not market:
            issues.append(
                PriceAuditIssue("invalid_partition_path", f"Cannot infer market from {path}.")
            )
            continue
        try:
            schema = pq.read_schema(path)
        except (FileNotFoundError, OSError, ValueError) as error:
            issues.append(
                PriceAuditIssue("unreadable_partition", f"Cannot read {path}: {error}")
            )
            continue
        missing_columns = sorted(set(_REQUIRED_COLUMNS) - set(schema.names))
        if missing_columns:
            issues.append(
                PriceAuditIssue(
                    "missing_columns",
                    f"{path}: missing required price columns: {', '.join(missing_columns)}.",
                    market=market,
                )
            )
            continue

        try:
            table = pq.read_table(path, columns=list(_REQUIRED_COLUMNS))
        except (FileNotFoundError, OSError, ValueError) as error:
            issues.append(
                PriceAuditIssue("unreadable_partition", f"Cannot read {path}: {error}")
            )
            continue

        valid_date_mask = pc.fill_null(pc.invert(pc.is_null(table["trading_date"])), False)
        market_dates[market].update(
            table.filter(valid_date_mask)["trading_date"].unique().to_pylist()
        )

        key_table = table.select(list(_KEY_COLUMNS))
        duplicate_groups = key_table.group_by(list(_KEY_COLUMNS)).aggregate(
            [("trading_date", "count")]
        )
        for row in duplicate_groups.to_pylist():
            count = int(row["trading_date_count"] or 0)
            if count <= 1:
                continue
            security_id = row["security_id"]
            if security_id is None:
                global_invalid["duplicate_null_security_id"] += count - 1
                continue
            item = _stats_for(stats, str(security_id), market)
            item.duplicate_rows += count - 1
            item.duplicate_keys += 1

        row_table = table.append_column("_row", pa.array([1] * table.num_rows, type=pa.int64()))
        summary = row_table.group_by("security_id").aggregate(
            [("_row", "sum"), ("trading_date", "min"), ("trading_date", "max")]
        )
        for row in summary.to_pylist():
            security_id = row["security_id"]
            if security_id is None:
                global_invalid["null_security_id"] += int(row["_row_sum"] or 0)
                continue
            item = _stats_for(stats, str(security_id), market)
            item.row_count += int(row["_row_sum"] or 0)
            first_date = row["trading_date_min"]
            last_date = row["trading_date_max"]
            if first_date is not None:
                item.first_date = (
                    first_date if item.first_date is None else min(item.first_date, first_date)
                )
            if last_date is not None:
                item.last_date = (
                    last_date if item.last_date is None else max(item.last_date, last_date)
                )

        metadata_groups = table.select(
            ["security_id", "currency", "exchange", "timezone"]
        ).group_by(["security_id", "currency", "exchange", "timezone"]).aggregate(
            [("security_id", "count")]
        )
        for row in metadata_groups.to_pylist():
            security_id = row["security_id"]
            if security_id is None:
                continue
            item = _stats_for(stats, str(security_id), market)
            item.currencies.add(row["currency"])
            item.exchanges.add(row["exchange"])
            item.timezones.add(row["timezone"])

        bad_ohlc, bad_price, bad_volume, bad_identifier, suspicious_price = _bad_price_masks(table)
        for name, mask, field_name in (
            ("invalid_ohlc", bad_ohlc, "invalid_ohlc_rows"),
            ("invalid_price", bad_price, "invalid_price_rows"),
            ("invalid_volume", bad_volume, "invalid_volume_rows"),
            ("invalid_identifier", bad_identifier, "invalid_identifier_rows"),
            ("suspicious_price", suspicious_price, "suspicious_price_rows"),
        ):
            for security_id, count in _sum_by_security(table, mask, name).items():
                if security_id is None:
                    global_invalid[name] += count
                    continue
                item = _stats_for(stats, str(security_id), market)
                setattr(item, field_name, getattr(item, field_name) + count)

        partition_year = _year_from_path(path)
        if partition_year is not None:
            years = pc.year(table["trading_date"])
            same_year = pc.equal(years, pa.scalar(partition_year, type=pa.int64()))
            wrong_year = pc.sum(
                pc.cast(
                    pc.and_(valid_date_mask, pc.invert(pc.fill_null(same_year, False))),
                    pa.int64(),
                )
            ).as_py()
            if wrong_year:
                global_invalid["wrong_partition_year"] += wrong_year

    market_sessions = {
        market: tuple(sorted(dates)) for market, dates in sorted(market_dates.items())
    }
    session_indexes = {
        market: {session: index for index, session in enumerate(sessions)}
        for market, sessions in market_sessions.items()
    }

    # Second pass: key-only scan for ordering and market-relative gaps.
    previous_by_security: dict[tuple[str, str], date] = {}
    for path in file_paths:
        market = _market_from_path(path)
        if not market or not path.exists():
            continue
        schema = pq.read_schema(path)
        if any(column not in schema.names for column in _KEY_COLUMNS):
            continue
        index_by_date = session_indexes.get(market, {})
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(columns=list(_KEY_COLUMNS), batch_size=100_000):
            for row in batch.to_pylist():
                security_id = row["security_id"]
                trading_date = row["trading_date"]
                if security_id is None or trading_date is None:
                    continue
                security_id = str(security_id)
                item = _stats_for(stats, security_id, market)
                key = (security_id, market)
                previous = previous_by_security.get(key)
                if previous is not None:
                    if trading_date < previous:
                        item.unsorted_rows += 1
                    previous_index = index_by_date.get(previous)
                    current_index = index_by_date.get(trading_date)
                    if (
                        trading_date > previous
                        and previous_index is not None
                        and current_index is not None
                        and current_index - previous_index > 1
                    ):
                        gap = current_index - previous_index - 1
                        item.internal_gap_sessions += gap
                        item.max_internal_gap_sessions = max(item.max_internal_gap_sessions, gap)
                previous_by_security[key] = trading_date

    def add_issue(
        code: str,
        message: str,
        security_id: str | None = None,
        market: str | None = None,
    ) -> None:
        issues.append(PriceAuditIssue(code, message, security_id=security_id, market=market))

    for code, count in sorted(global_invalid.items()):
        if count:
            add_issue(
                code,
                f"Downloaded price data contains {count} row(s) failing {code.replace('_', ' ')}.",
            )

    expected_ids = set(expectations)
    for security_id, item in sorted(stats.items()):
        expectation = expectations.get(security_id)
        if expectation is None:
            if security_id not in seen_unknown:
                add_issue(
                    "unknown_security_id",
                    f"Price data for {security_id} has no matching local security expectation.",
                    security_id=security_id,
                )
                seen_unknown.add(security_id)
            continue

        if item.duplicate_rows:
            add_issue(
                "duplicate_price_observations",
                f"{security_id}: {item.duplicate_rows} duplicate price row(s) across "
                f"{item.duplicate_keys} key(s).",
                security_id,
                expectation.market,
            )
        if item.invalid_ohlc_rows:
            add_issue(
                "invalid_ohlc",
                f"{security_id}: {item.invalid_ohlc_rows} row(s) have non-finite or "
                "invalid OHLC relationships.",
                security_id,
                expectation.market,
            )
        if item.invalid_price_rows:
            add_issue(
                "invalid_prices",
                f"{security_id}: {item.invalid_price_rows} row(s) have negative or "
                "non-positive prices.",
                security_id,
                expectation.market,
            )
        if item.invalid_volume_rows:
            add_issue(
                "invalid_volume",
                f"{security_id}: {item.invalid_volume_rows} row(s) have null or negative volume.",
                security_id,
                expectation.market,
            )
        if item.invalid_identifier_rows:
            add_issue(
                "invalid_identifiers",
                f"{security_id}: {item.invalid_identifier_rows} row(s) have null identifiers "
                "or metadata.",
                security_id,
                expectation.market,
            )
        if item.suspicious_price_rows:
            add_issue(
                "suspicious_price_levels",
                f"{security_id}: {item.suspicious_price_rows} row(s) exceed the "
                f"configured price ceiling of {_MAX_REASONABLE_PRICE:,}.",
                security_id,
                expectation.market,
            )
        if item.unsorted_rows:
            add_issue(
                "dates_not_ordered",
                f"{security_id}: {item.unsorted_rows} price row(s) are out of trading-date order.",
                security_id,
                expectation.market,
            )
        if item.max_internal_gap_sessions > max_internal_gap_sessions:
            add_issue(
                "internal_price_gaps",
                f"{security_id}: {item.internal_gap_sessions} total missing market session(s), "
                f"largest gap {item.max_internal_gap_sessions}; "
                f"allowed maximum is {max_internal_gap_sessions}.",
                security_id,
                expectation.market,
            )

        if item.markets != {expectation.market.upper()}:
            add_issue(
                "market_mismatch",
                f"{security_id}: stored market(s) {sorted(item.markets)} do not match "
                f"{expectation.market.upper()}.",
                security_id,
                expectation.market,
            )
        if item.currencies != {expectation.currency.upper()}:
            add_issue(
                "currency_mismatch",
                f"{security_id}: stored currency value(s) {sorted(map(str, item.currencies))} "
                f"do not match {expectation.currency.upper()}.",
                security_id,
                expectation.market,
            )
        if item.exchanges != {expectation.exchange.upper()}:
            add_issue(
                "exchange_mismatch",
                f"{security_id}: stored exchange value(s) {sorted(map(str, item.exchanges))} "
                f"do not match {expectation.exchange.upper()}.",
                security_id,
                expectation.market,
            )
        if not item.timezones or None in item.timezones:
            add_issue(
                "timezone_missing",
                f"{security_id}: timezone metadata is missing.",
                security_id,
                expectation.market,
            )

        if (
            history_floor is not None
            and item.first_date is not None
            and item.first_date < history_floor
        ):
            add_issue(
                "history_before_floor",
                f"{security_id}: first price date {item.first_date} is before configured "
                f"history floor {history_floor}.",
                security_id,
                expectation.market,
            )

        sessions = market_sessions.get(expectation.market.upper(), ())
        indexes = session_indexes.get(expectation.market.upper(), {})
        if not sessions:
            add_issue(
                "missing_market_calendar",
                f"{security_id}: no observed market sessions for {expectation.market.upper()}.",
                security_id,
                expectation.market,
            )
            continue

        if expectation.expected_start is not None and item.first_date is not None:
            expected_index = bisect_left(sessions, expectation.expected_start)
            actual_index = indexes.get(item.first_date, bisect_left(sessions, item.first_date))
            if item.first_date < expectation.expected_start:
                add_issue(
                    "price_before_expected_start",
                    f"{security_id}: first price date {item.first_date} precedes expected start "
                    f"{expectation.expected_start}.",
                    security_id,
                    expectation.market,
                )
            elif actual_index - expected_index > start_tolerance_sessions:
                add_issue(
                    "missing_start_history",
                    f"{security_id}: first price date {item.first_date} is "
                    f"{actual_index - expected_index} observed session(s) after expected start "
                    f"{expectation.expected_start}; "
                    f"allowed tolerance is {start_tolerance_sessions}.",
                    security_id,
                    expectation.market,
                )

        expected_end = expectation.expected_end
        if expected_end is None and expectation.active:
            expected_end = sessions[-1]
        if expected_end is not None and item.last_date is not None:
            expected_index = bisect_right(sessions, expected_end) - 1
            actual_index = indexes.get(item.last_date, bisect_right(sessions, item.last_date) - 1)
            if expected_index >= 0 and expected_index - actual_index > end_tolerance_sessions:
                add_issue(
                    "missing_end_history",
                    f"{security_id}: last price date {item.last_date} is "
                    f"{expected_index - actual_index} observed session(s) before expected end "
                    f"{expected_end}; "
                    f"allowed tolerance is {end_tolerance_sessions}.",
                    security_id,
                    expectation.market,
                )

    for security_id in sorted(expected_ids - set(stats)):
        expectation = expectations[security_id]
        add_issue(
            "missing_security_history",
            f"{security_id}: no downloaded price rows were found.",
            security_id,
            expectation.market,
        )

    return PriceAuditReport(
        issues=tuple(issues),
        security_stats={key: value for key, value in sorted(stats.items())},
        market_sessions=market_sessions,
    )
