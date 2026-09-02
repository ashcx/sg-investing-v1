"""Incremental market-data updater (Sprint 7.5, Track B).

Refreshes the canonical store for ANY new date or date range in minutes,
without the ~6-hour full-catalog rebuild performed by ``update_data.py``:

- per security, the fetch window starts at the last stored price date minus a
  trailing reconciliation window (default 45 days) so late-arriving dividends,
  restated events and corporate actions are re-reconciled;
- ``--since <date>`` additionally widens the window back for gap backfill;
- FX tails for every required pair are refreshed through the existing
  ``update_fx_rates`` ingestion path;
- all writes go through the existing atomic storage upserts keyed by
  security + trading date (partition replacement only after validation);
- the resulting change set (sorted keys of rows that are new or restated)
  determines a deterministic incremental ``data_snapshot_id`` chain and an
  incremental ``data/update_summary.json``;
- with ``--build-packs`` (default) only touched security/year packs are
  rebuilt via ``build_data_packs.py --security/--years`` and the pack manifest
  is merged (untouched securities preserved).

Run with ``--dry-run`` to print exactly what WOULD be fetched (windows,
provider endpoints) and what would be rebuilt, without any network call or
write. The incremental contract is documented in
``docs/incremental-updates.md``; operator procedures live in
``docs/data-updates.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pyarrow.parquet as pq
import yaml

from sg_investing.data.dividend_backfill import backfill_dividends
from sg_investing.data.dividend_quality import record_coverage_snapshot
from sg_investing.data.ingestion import (
    SecurityUpdateResult,
    update_fx_rates,
    update_security_prices,
)
from sg_investing.data.providers.base import MarketDataProvider
from sg_investing.data.providers.yahoo import YahooFinanceProvider
from sg_investing.data.storage import ParquetStore
from sg_investing.data.validation import dividend_event_key
from sg_investing.models import CorporateAction, DataQualityStatus, Security
from sg_investing.universe.catalog import UniverseCatalog, load_catalog

ROOT = Path(__file__).resolve().parents[1]
RECONCILIATION_DAYS_DEFAULT = 45
# Defensive cap so a pathological run (for example a full-history backfill
# misused as an incremental update) still produces a bounded summary; the
# snapshot digest uses the capped key list.
CHANGE_SET_KEY_LIMIT = 10_000
# Mirrors sg_investing.data.packs.FX_LOOKBACK_CALENDAR_DAYS: a pack's FX
# window starts this many calendar days before its first price date.
FX_LOOKBACK_CALENDAR_DAYS = 10


@dataclass(frozen=True)
class SecurityPlan:
    """Resolved fetch plan for one security."""

    security: Security
    last_price_date: date | None
    price_start: date
    full_fetch: bool


@dataclass
class UpdatePlan:
    """What a run WOULD fetch; doubles as the dry-run payload."""

    end_date: date
    securities: list[SecurityPlan] = field(default_factory=list)
    fx_plans: list[dict] = field(default_factory=list)
    pack_command: list[str] | None = None


def _utc_today() -> date:
    return datetime.now(UTC).date()


def incremental_snapshot_id(base_snapshot_id: str, change_keys: list[str]) -> str:
    """Deterministic incremental snapshot id: hash of base id + change set.

    ``sha256(base_snapshot_id + "\\0" + each sorted change key + "\\x1f")``,
    reported as ``incr-<32 hex>``. An empty change set is a no-op that keeps
    the base id, so re-running an already-applied update never churns the
    snapshot chain. See docs/incremental-updates.md for the scheme.
    """

    if not change_keys:
        return base_snapshot_id
    digest = hashlib.sha256()
    digest.update(base_snapshot_id.encode("utf-8"))
    digest.update(b"\0")
    for key in sorted(change_keys):
        digest.update(key.encode("utf-8"))
        digest.update(b"\x1f")
    return f"incr-{digest.hexdigest()[:32]}"


def parse_since(raw: str) -> date | None:
    """Parse ``--since``: ``auto`` (None) or an ISO date."""

    if raw == "auto":
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as error:
        raise ValueError(f"Invalid --since {raw!r}: expected 'auto' or YYYY-MM-DD.") from error


def _store_chain_hash(data_root: Path) -> str:
    """Content hash of the canonical store for the incremental chain.

    Same digest scheme as ``compute_data_snapshot_id`` but excludes the
    root-level ``update_summary.json``: every run rewrites that file with
    fresh timestamps after hashing, so including it would make the
    base-id continuation check between runs impossible. Canonical datasets
    (prices, events, FX, manifests, coverage) all contribute; pack
    manifests keep carrying the full-store id computed at build time.
    """

    digest = hashlib.sha256()
    summary_path = data_root / "update_summary.json"
    for path in sorted(item for item in data_root.rglob("*") if item.is_file()):
        if path == summary_path:
            continue
        digest.update(path.relative_to(data_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    return f"sha256-{digest.hexdigest()}"


def _scan_price_last_dates(data_root: Path) -> dict[str, date]:
    """One projected pass over all price partitions: security_id -> last date.

    The storage layer has no cheap per-security last-date query (a full
    partition read per security is a large part of why the full rebuild takes
    ~6h), so this scan reads only two columns once per partition and reduces
    each partition with one Arrow group-by instead of materialising rows.
    """

    last: dict[str, date] = {}
    prices_root = data_root / "prices"
    if not prices_root.is_dir():
        return last
    for market_dir in sorted(prices_root.glob("market=*")):
        for path in sorted(market_dir.glob("year=*.parquet")):
            table = pq.read_table(path, columns=["security_id", "trading_date"])
            grouped = table.group_by("security_id").aggregate([("trading_date", "max")])
            for security_id, day in zip(
                grouped.column("security_id").to_pylist(),
                grouped.column("trading_date_max").to_pylist(),
                strict=True,
            ):
                current = last.get(security_id)
                if current is None or day > current:
                    last[security_id] = day
    return last


def _scan_price_values(
    data_root: Path, market: str, years: list[int]
) -> dict[tuple[str, date], tuple]:
    """``(security_id, date) -> (open, high, low, close, volume)`` for a market."""

    values: dict[tuple[str, date], tuple] = {}
    for year in years:
        path = data_root / "prices" / f"market={market.upper()}" / f"year={year}.parquet"
        if not path.exists():
            continue
        table = pq.read_table(
            path,
            columns=["security_id", "trading_date", "open", "high", "low", "close", "volume"],
        )
        sids = table.column("security_id").to_pylist()
        days = table.column("trading_date").to_pylist()
        columns = [table.column(name).to_pylist() for name in ("open", "high", "low", "close", "volume")]
        for index in range(table.num_rows):
            values[(sids[index], days[index])] = tuple(column[index] for column in columns)
    return values


def _stored_event_signatures(store: ParquetStore, dataset: str) -> dict[tuple, tuple]:
    """Stable value signatures for stored dividend/action rows.

    ``retrieved_at`` is deliberately excluded: a reconciliation refetch that
    returns identical economics must not register as a change.
    """

    signatures: dict[tuple, tuple] = {}
    directory = store.root / dataset
    if not directory.is_dir():
        return signatures
    years = sorted(int(path.stem.split("=")[1]) for path in directory.glob("year=*.parquet"))
    for year in years:
        rows = (
            store.read_dividends(year=year)
            if dataset == "dividends"
            else store.read_corporate_actions(year=year)
        )
        for row in rows:
            if dataset == "dividends":
                signatures[dividend_event_key(row)] = (
                    str(row.security_id),
                    row.ex_date.isoformat(),
                    str(row.amount),
                    row.currency,
                    row.source_id,
                )
            else:
                signatures[(str(row.security_id), row.effective_date, row.action_type)] = (
                    str(row.security_id),
                    row.effective_date.isoformat(),
                    row.action_type.value,
                    str(row.ratio),
                )
    return signatures


def _stored_fx_signatures(store: ParquetStore) -> dict[tuple[str, date], tuple]:
    signatures: dict[tuple[str, date], tuple] = {}
    fx_root = store.root / "fx"
    if not fx_root.is_dir():
        return signatures
    for pair_dir in sorted(fx_root.glob("pair=*")):
        currency = pair_dir.name.split("=", 1)[1].removesuffix("_SGD")
        years = sorted(int(path.stem.split("=")[1]) for path in pair_dir.glob("year=*.parquet"))
        for year in years:
            for row in store.read_fx(base_currency=currency, year=year):
                signatures[(row.base_currency, row.rate_date)] = (
                    row.base_currency,
                    row.rate_date.isoformat(),
                    str(row.rate_to_sgd),
                )
    return signatures


def _scan_last_action_dates(store: ParquetStore) -> dict[str, date]:
    last: dict[str, date] = {}
    directory = store.root / "corporate_actions"
    if not directory.is_dir():
        return last
    for path in sorted(directory.glob("year=*.parquet")):
        for row in store.read_corporate_actions(year=int(path.stem.split("=")[1])):
            security_id = str(row.security_id)
            current = last.get(security_id)
            if current is None or row.effective_date > current:
                last[security_id] = row.effective_date
    return last


def _security_ids_priced_in(data_root: Path, year: int) -> set[str]:
    ids: set[str] = set()
    prices_root = data_root / "prices"
    if not prices_root.is_dir():
        return ids
    for market_dir in sorted(prices_root.glob("market=*")):
        path = market_dir / f"year={year}.parquet"
        if not path.exists():
            continue
        table = pq.read_table(path, columns=["security_id"])
        ids.update(table.column("security_id").to_pylist())
    return ids


def _resolve_window_start(
    *,
    since: date | None,
    last_date: date | None,
    reconciliation_days: int,
    start_floor: date,
) -> tuple[date, bool]:
    """Fetch start for one series: tail + reconciliation window.

    ``auto`` (``since is None``) reconciles the default window behind the
    stored last date. An explicit ``since`` older than that widens the window
    back to it (gap backfill). No stored dates means a full fetch from the
    floor (reported as such).
    """

    if last_date is None:
        return start_floor, True
    window_start = last_date - timedelta(days=reconciliation_days)
    if since is not None and since < window_start:
        window_start = since
    return max(start_floor, window_start), False


def _years_between(start: date, end: date) -> list[int]:
    return list(range(start.year, end.year + 1))


def _select_securities(catalog: UniverseCatalog, selectors: list[str] | None) -> list[Security]:
    """Resolve catalog securities from tickers or security_ids, deduplicated."""

    if not selectors:
        selected: list[Security] = []
        seen: set[str] = set()
        for entry in catalog.securities:
            key = str(entry.security.security_id)
            if key not in seen:
                seen.add(key)
                selected.append(entry.security)
        return selected
    wanted = {selector.strip().upper() for selector in selectors if selector.strip()}
    selected = []
    seen: set[str] = set()
    for entry in catalog.securities:
        key = str(entry.security.security_id)
        if entry.security.ticker in wanted or key.upper() in wanted:
            wanted.discard(entry.security.ticker)
            wanted.discard(key.upper())
            if key not in seen:
                seen.add(key)
                selected.append(entry.security)
    if wanted:
        raise ValueError(f"Unknown security selector(s) not present in the catalog: {sorted(wanted)}")
    return selected


def _build_plan(
    *,
    catalog: UniverseCatalog,
    store: ParquetStore,
    selected: list[Security],
    last_dates: dict[str, date],
    since: date | None,
    reconciliation_days: int,
    end_date: date,
) -> UpdatePlan:
    plans: list[SecurityPlan] = []
    for security in selected:
        price_start, full_fetch = _resolve_window_start(
            since=since,
            last_date=last_dates.get(str(security.security_id)),
            reconciliation_days=reconciliation_days,
            start_floor=catalog.history_start,
        )
        plans.append(
            SecurityPlan(
                security=security,
                last_price_date=last_dates.get(str(security.security_id)),
                price_start=price_start,
                full_fetch=full_fetch,
            )
        )
    currencies = sorted({security.currency for security in selected if security.currency != "SGD"})
    fx_plans: list[dict] = []
    for currency in currencies:
        pair_dir = store.root / "fx" / f"pair={currency}_SGD"
        stored: list[date] = []
        if pair_dir.is_dir():
            for path in sorted(pair_dir.glob("year=*.parquet")):
                stored.extend(
                    row.rate_date
                    for row in store.read_fx(base_currency=currency, year=int(path.stem.split("=")[1]))
                )
        last_rate = max(stored) if stored else None
        # A pair with no stored history is fetched from the catalog floor
        # regardless of --since (packs need FX at every price date, matching
        # update_data.py behaviour); --since only widens an existing tail.
        fx_start, _ = _resolve_window_start(
            since=since if stored else None,
            last_date=last_rate,
            reconciliation_days=reconciliation_days,
            start_floor=catalog.history_start,
        )
        fx_plans.append(
            {
                "pair": f"{currency}_SGD",
                "base_currency": currency,
                "last_stored_date": last_rate.isoformat() if last_rate else None,
                "start": fx_start.isoformat(),
                "end": end_date.isoformat(),
                "reconciliation_days": (last_rate - fx_start).days if last_rate else reconciliation_days,
                "endpoint": (
                    f"yfinance:{currency}SGD=X:history(start={fx_start.isoformat()}, "
                    f"end={(end_date + timedelta(days=1)).isoformat()})"
                ),
            }
        )
    return UpdatePlan(end_date=end_date, securities=plans, fx_plans=fx_plans)


def _security_endpoint(security: Security, start: date, end_date: date) -> str:
    return (
        f"yfinance:{security.ticker}:history(start={start.isoformat()}, "
        f"end={(end_date + timedelta(days=1)).isoformat()})"
    )


def _fetch_price_rows(
    provider: MarketDataProvider, plans: list[SecurityPlan], end_date: date
) -> tuple[dict[str, list], dict[str, str], dict[str, str]]:
    """Batch price fetch plus per-security window filtering.

    Securities whose whole history must be fetched (no stored prices) are
    handled by the straggler path in :func:`run_incremental_update` instead.
    """

    batch = [plan for plan in plans if not plan.full_fetch]
    rows_by_security: dict[str, list] = {}
    errors: dict[str, str] = {}
    warnings: dict[str, str] = {}
    if batch:
        start = min(plan.price_start for plan in batch)
        if hasattr(provider, "get_prices_batch"):
            batch_rows, batch_errors, batch_warnings = provider.get_prices_batch(
                [plan.security for plan in batch], start, end_date
            )
            rows_by_security = {
                str(security_id): list(rows) for security_id, rows in batch_rows.items()
            }
            errors = {str(key): value for key, value in batch_errors.items()}
            warnings = {str(key): value for key, value in batch_warnings.items()}
        else:
            for plan in batch:
                try:
                    rows_by_security[str(plan.security.security_id)] = list(
                        provider.get_prices(plan.security, start, end_date)
                    )
                except Exception as error:  # noqa: BLE001 - retain failure per security
                    errors[str(plan.security.security_id)] = str(error)
    filtered: dict[str, list] = {}
    for plan in batch:
        rows = [
            row
            for row in rows_by_security.get(str(plan.security.security_id), [])
            if plan.price_start <= row.trading_date <= end_date
        ]
        if rows:
            filtered[str(plan.security.security_id)] = rows
    return filtered, errors, warnings


def _fetch_action_rows(
    provider: MarketDataProvider,
    starts: list[tuple[Security, date]],
    end_date: date,
    workers: int,
) -> tuple[list[CorporateAction], dict[str, str]]:
    """Threaded corporate-action reconciliation; rows are upserted after collection."""

    rows: list[CorporateAction] = []
    errors: dict[str, str] = {}

    def job(security: Security, start: date) -> list[CorporateAction]:
        fetched = list(provider.get_corporate_actions(security, start, end_date))
        for row in fetched:
            if row.security_id != security.security_id:
                raise ValueError("Provider returned a corporate action for another security.")
            if not start <= row.effective_date <= end_date:
                raise ValueError("Provider returned a corporate action outside the requested range.")
        return fetched

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [(str(security.security_id), executor.submit(job, security, start)) for security, start in starts]
        for security_id, future in futures:
            try:
                rows.extend(future.result())
            except Exception as error:  # noqa: BLE001 - retain failure per security
                errors[security_id] = str(error)
    return rows, errors


def _price_change_keys(
    before: dict[tuple[str, date], tuple], after: dict[tuple[str, date], tuple]
) -> tuple[list[str], int]:
    keys: list[str] = []
    restated = 0
    for (security_id, day), value in after.items():
        previous = before.get((security_id, day))
        if previous is None:
            keys.append(f"price:{security_id}:{day.isoformat()}")
        elif previous != value:
            restated += 1
            keys.append(f"price:{security_id}:{day.isoformat()}")
    return keys, restated


def _event_change_keys(
    dataset: str, before: dict[tuple, tuple], after: dict[tuple, tuple]
) -> tuple[list[str], int]:
    keys: list[str] = []
    restated = 0
    for key, signature in after.items():
        if before.get(key) == signature:
            continue
        security_id, event_date = signature[0], signature[1]
        tail = ":".join(str(part) if part is not None else "-" for part in signature[2:])
        keys.append(f"{dataset}:{security_id}:{event_date}:{tail}")
        if key in before:
            restated += 1
    return keys, restated


def _fx_change_keys(
    before: dict[tuple[str, date], tuple], after: dict[tuple[str, date], tuple]
) -> tuple[list[str], int]:
    keys: list[str] = []
    restated = 0
    for (currency, rate_date), signature in after.items():
        previous = before.get((currency, rate_date))
        if previous is None:
            keys.append(f"fx:new:{rate_date.isoformat()}:{currency}")
        elif previous != signature:
            restated += 1
            keys.append(f"fx:restated:{rate_date.isoformat()}:{currency}:{signature[2]}")
    return keys, restated


def _fx_touches(
    fx_change_keys: list[str],
    data_root: Path,
    currency_by_security: dict[str, str],
    last_price_dates: dict[str, date],
) -> set[tuple[str, int]]:
    """Map changed FX rates to ``(security_id, year)`` pack partitions.

    A pack's FX window spans ``[first price date - 10 days, last price date]``
    of its own year, so a changed rate only affects packs whose year window
    contains it. Restated rates always qualify; a NEW rate qualifies only when
    it lands on or before a priced security's stored last date (an FX gap that
    a ``--since`` backfill fills inside existing coverage). Tail FX beyond
    every stored price date enters packs through the accompanying price
    changes and does not, by itself, invalidate any pack.
    """

    touches: set[tuple[str, int]] = set()
    priced_cache: dict[int, set[str]] = {}
    for key in fx_change_keys:
        parts = key.split(":")
        if len(parts) < 4 or parts[0] != "fx" or parts[1] not in {"new", "restated"}:
            continue
        rate_date = date.fromisoformat(parts[2])
        currency = parts[3]
        for year in {rate_date.year, (rate_date + timedelta(days=FX_LOOKBACK_CALENDAR_DAYS)).year}:
            priced = priced_cache.get(year)
            if priced is None:
                priced = _security_ids_priced_in(data_root, year)
                priced_cache[year] = priced
            for security_id in priced:
                if currency_by_security.get(security_id) != currency:
                    continue
                if parts[1] == "restated" or (
                    rate_date <= last_price_dates.get(security_id, date.min)
                ):
                    touches.add((security_id, year))
    return touches


def _touched_pairs(
    change_keys: list[str],
    straggler_touches: list[tuple[str, int]],
    data_root: Path,
    currency_by_security: dict[str, str],
    last_price_dates: dict[str, date],
) -> dict[str, set[int]]:
    touched: dict[str, set[int]] = {}

    def add(security_id: str, year: int) -> None:
        touched.setdefault(security_id, set()).add(year)

    for key in change_keys:
        parts = key.split(":")
        if parts[0] == "price" or parts[0] in {"dividends", "corporate_actions"}:
            add(parts[1], int(parts[2][:4]))
    for security_id, year in straggler_touches:
        add(security_id, year)
    for security_id, year in sorted(
        _fx_touches(change_keys, data_root, currency_by_security, last_price_dates)
    ):
        add(security_id, year)
    return touched


def _pack_command(root: Path, touched: dict[str, set[int]] | None) -> list[str]:
    command = [sys.executable, str(root / "scripts" / "build_data_packs.py"), "--root", str(root)]
    if touched is not None:
        for security_id in sorted(touched):
            command.extend(["--security", security_id])
        years = sorted({year for years in touched.values() for year in years})
        if years:
            command.extend(["--years", ",".join(str(year) for year in years)])
    return command


def _load_previous_summary(root: Path) -> dict:
    path = root / "data" / "update_summary.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _dry_run_summary(
    *,
    root: Path,
    plan: UpdatePlan,
    since: str,
    reconciliation_days: int,
    selected_count: int,
) -> dict:
    securities_payload = []
    partition_paths: set[str] = set()
    for item in plan.securities:
        market = item.security.market
        fetch_years = _years_between(item.price_start, plan.end_date)
        would_write = [
            (root / "data" / "prices" / f"market={market.upper()}" / f"year={year}.parquet")
            for year in fetch_years
        ]
        for path in would_write:
            partition_paths.add(str(path))
        securities_payload.append(
            {
                "ticker": item.security.ticker,
                "security_id": str(item.security.security_id),
                "market": market,
                "currency": item.security.currency,
                "last_stored_price_date": (
                    item.last_price_date.isoformat() if item.last_price_date else None
                ),
                "full_history_fetch": item.full_fetch,
                "price_fetch_start": item.price_start.isoformat(),
                "price_fetch_end": plan.end_date.isoformat(),
                "fetch_years": fetch_years,
                "endpoint": _security_endpoint(item.security, item.price_start, plan.end_date),
                "would_reconcile_dividends": True,
                "would_reconcile_corporate_actions": True,
            }
        )
    for fx_plan in plan.fx_plans:
        partition_paths.add(
            str(root / "data" / "fx" / f"pair={fx_plan['pair']}" / "year={YYYY}.parquet")
        )
    partition_paths.add(str(root / "data" / "update_summary.json"))
    return {
        "mode": "dry-run",
        "note": "Nothing was fetched or written; windows below are what a real run would fetch.",
        "since": since,
        "end_date": plan.end_date.isoformat(),
        "reconciliation_days": reconciliation_days,
        "securities_selected_count": selected_count,
        "full_history_fetch_count": sum(1 for item in plan.securities if item.full_fetch),
        "securities": securities_payload,
        "fx": plan.fx_plans,
        "pack_rebuild": (
            {"command": plan.pack_command, "note": "estimated touched pairs; the applied run rebuilds exactly the changed security/year pairs"}
            if plan.pack_command
            else None
        ),
        "would_write_paths": sorted(partition_paths),
    }


def run_incremental_update(
    root: str | Path,
    *,
    since: str = "auto",
    securities: list[str] | None = None,
    dry_run: bool = False,
    build_packs: bool = True,
    skip_actions: bool = False,
    reconciliation_days: int = RECONCILIATION_DAYS_DEFAULT,
    end_date: date | None = None,
    provider: MarketDataProvider | None = None,
) -> dict:
    """Run one incremental update and return the JSON-serializable summary."""

    root_path = Path(root)
    settings = yaml.safe_load((root_path / "config" / "settings.yaml").read_text(encoding="utf-8"))
    catalog_path = root_path / "data" / "universe" / "current_catalog.json"
    if not catalog_path.exists():
        raise ValueError("Run scripts/refresh_universe.py before updating market data.")
    catalog = load_catalog(catalog_path)
    store = ParquetStore(root_path / settings["data_directory"])
    data_root = store.root
    end = end_date or _utc_today()
    since_date = parse_since(since)
    selected = _select_securities(catalog, securities)
    if not selected:
        raise ValueError("No securities selected.")
    if reconciliation_days < 0:
        raise ValueError("--reconciliation-days must be non-negative.")
    last_dates = _scan_price_last_dates(data_root)
    plan = _build_plan(
        catalog=catalog,
        store=store,
        selected=selected,
        last_dates=last_dates,
        since=since_date,
        reconciliation_days=reconciliation_days,
        end_date=end,
    )
    currency_by_security = {
        str(security.security_id): security.currency for security in selected
    }
    market_by_security = {
        str(security.security_id): security.market for security in selected
    }

    if dry_run:
        if build_packs:
            estimate = {
                str(item.security.security_id): {
                    year
                    for year in _years_between(item.price_start, end)
                    if item.last_price_date is None or year >= item.last_price_date.year
                }
                for item in plan.securities
                if item.last_price_date is None or item.last_price_date < end
            }
            estimate = {security_id: years for security_id, years in estimate.items() if years}
            plan.pack_command = _pack_command(root_path, estimate or None)
        return _dry_run_summary(
            root=root_path,
            plan=plan,
            since=since,
            reconciliation_days=reconciliation_days,
            selected_count=len(selected),
        )

    if provider is None:
        provider = YahooFinanceProvider()

    base_hash = _store_chain_hash(data_root)
    previous_summary = _load_previous_summary(root_path)
    # Snapshot chain: continue the previous incremental id when this run
    # starts from exactly the store that run produced; otherwise (full
    # rebuild, external change) restart the chain from the content hash.
    base_id = base_hash
    if (
        previous_summary.get("mode") == "incremental"
        and previous_summary.get("data_snapshot_id") == base_hash
        and isinstance(previous_summary.get("incremental_snapshot_id"), str)
    ):
        base_id = previous_summary["incremental_snapshot_id"]

    fetch_years = _years_between(
        min(item.price_start for item in plan.securities), end
    )
    markets = sorted({item.security.market for item in plan.securities})
    before_values = {market: _scan_price_values(data_root, market, fetch_years) for market in markets}

    straggler_plans = [item for item in plan.securities if item.full_fetch]
    straggler_results: dict[str, SecurityUpdateResult] = {}
    for item in straggler_plans:
        straggler_results[str(item.security.security_id)] = update_security_prices(
            store=store,
            provider=provider,
            security=item.security,
            end_date=end,
            start_floor=item.price_start,
            reconciliation_days=reconciliation_days,
            pipeline_version=settings["pipeline_version"],
            include_dividends=False,
        )

    price_rows, batch_errors, batch_warnings = _fetch_price_rows(provider, plan.securities, end)
    rows_by_market: dict[str, list] = {}
    for security_id, rows in price_rows.items():
        rows_by_market.setdefault(market_by_security[security_id], []).extend(rows)
    manifests_by_market: dict[str, list] = {}
    for market, rows in sorted(rows_by_market.items()):
        manifests_by_market[market] = store.upsert_prices(
            market=market, rows=rows, pipeline_version=settings["pipeline_version"]
        )
    after_values = {market: _scan_price_values(data_root, market, fetch_years) for market in markets}
    price_keys: list[str] = []
    price_restated = 0
    for market in markets:
        keys, restated = _price_change_keys(before_values[market], after_values[market])
        price_keys.extend(keys)
        price_restated += restated
    straggler_touches = [
        (security_id, int(manifest.first_date[:4]))
        for security_id, result in straggler_results.items()
        for manifest in result.manifests
        if manifest.first_date is not None
    ]

    before_dividends = _stored_event_signatures(store, "dividends")
    dividend_recon = reconciliation_days
    if since_date is not None:
        dividend_recon = max(dividend_recon, (end - since_date).days)
    dividend_report, dividend_results = backfill_dividends(
        catalog=catalog,
        store=store,
        provider=provider,
        coverage_path=data_root / "dividends" / "coverage_report.json",
        end_date=end,
        start_floor=catalog.history_start,
        reconciliation_days=dividend_recon,
        workers=settings.get("price_backfill_workers", 4),
        retries=2,
        include_unknown=True,
        tickers=[security.ticker for security in selected],
    )
    dividend_coverage_warnings = record_coverage_snapshot(
        dividend_report,
        data_root / "dividends" / "coverage_history.json",
    )
    dividend_keys, dividend_restated = _event_change_keys(
        "dividends", before_dividends, _stored_event_signatures(store, "dividends")
    )

    action_keys: list[str] = []
    action_restated = 0
    action_errors: dict[str, str] = {}
    if not skip_actions:
        before_actions = _stored_event_signatures(store, "corporate_actions")
        latest_actions = _scan_last_action_dates(store)
        action_starts: list[tuple[Security, date]] = []
        for item in plan.securities:
            latest = latest_actions.get(str(item.security.security_id))
            start, _ = _resolve_window_start(
                since=since_date,
                last_date=latest,
                reconciliation_days=reconciliation_days,
                start_floor=catalog.history_start,
            )
            action_starts.append((item.security, start))
        action_rows, action_errors = _fetch_action_rows(
            provider,
            action_starts,
            end,
            workers=settings.get("price_backfill_workers", 4),
        )
        if action_rows:
            store.upsert_corporate_actions(action_rows)
        action_keys, action_restated = _event_change_keys(
            "corporate_actions", before_actions, _stored_event_signatures(store, "corporate_actions")
        )

    before_fx = _stored_fx_signatures(store)
    fx_rows_written = 0
    fx_errors: dict[str, str] = {}
    for fx_plan in plan.fx_plans:
        try:
            rows = update_fx_rates(
                store=store,
                provider=provider,
                base_currency=fx_plan["base_currency"],
                end_date=end,
                start_floor=date.fromisoformat(fx_plan["start"]),
                reconciliation_days=fx_plan["reconciliation_days"],
            )
            fx_rows_written += len(rows)
        except Exception as error:  # noqa: BLE001 - retain failure per pair
            fx_errors[fx_plan["base_currency"]] = str(error)
    fx_keys, fx_restated = _fx_change_keys(before_fx, _stored_fx_signatures(store))

    change_keys = [*price_keys, *dividend_keys, *action_keys, *fx_keys]
    for security_id, result in straggler_results.items():
        if result.rows_written:
            change_keys.append(f"security:{security_id}:backfilled:{result.rows_written}")
    truncated = len(change_keys) > CHANGE_SET_KEY_LIMIT
    capped_keys = sorted(change_keys)[:CHANGE_SET_KEY_LIMIT]
    snapshot_id = incremental_snapshot_id(base_id, capped_keys)
    after_hash = _store_chain_hash(data_root)

    packs_payload: dict | None = None
    touched = _touched_pairs(
        change_keys, straggler_touches, data_root, currency_by_security, last_dates
    )
    if build_packs and touched:
        command = _pack_command(root_path, touched)
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            packs_payload = {
                "command": command,
                "error": completed.stderr.strip()[-2000:] or completed.stdout.strip()[-2000:],
            }
        else:
            try:
                packs_payload = {"command": command, "summary": json.loads(completed.stdout)}
            except json.JSONDecodeError:
                packs_payload = {"command": command, "error": "pack builder printed no JSON summary"}

    manifests_by_year_by_market = {
        market: {
            int(manifest.first_date[:4]): manifest
            for manifest in manifests
            if manifest.first_date is not None
        }
        for market, manifests in manifests_by_market.items()
    }
    results: list[SecurityUpdateResult] = []
    for item in plan.securities:
        security_id = str(item.security.security_id)
        if item.full_fetch:
            results.append(straggler_results[security_id])
            continue
        rows = price_rows.get(security_id, [])
        if security_id in batch_errors:
            results.append(
                SecurityUpdateResult(
                    security_id=security_id,
                    ticker=item.security.ticker,
                    status=DataQualityStatus.FAILED,
                    start_date=item.price_start,
                    end_date=end,
                    rows_written=0,
                    error=batch_errors[security_id],
                )
            )
            continue
        market_manifests = manifests_by_year_by_market.get(market_by_security[security_id], {})
        results.append(
            SecurityUpdateResult(
                security_id=security_id,
                ticker=item.security.ticker,
                status=DataQualityStatus.OK if rows else DataQualityStatus.WARNING,
                start_date=item.price_start,
                end_date=end,
                rows_written=len(rows),
                manifests=[
                    market_manifests[year]
                    for year in sorted({row.trading_date.year for row in rows})
                    if year in market_manifests
                ],
                error=None if rows else "Provider returned no price rows in the fetch window.",
            )
        )

    touched_years: dict[str, list[str]] = {}
    for security_id, years in sorted(touched.items()):
        for year in sorted(years):
            touched_years.setdefault(str(year), []).append(security_id)
    summary = {
        "mode": "incremental",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "since": since,
        "end_date": end.isoformat(),
        "reconciliation_days": reconciliation_days,
        "pipeline_version": settings["pipeline_version"],
        "provider": provider.name,
        "securities_selected_count": len(selected),
        "full_history_fetch_securities": sorted(
            item.security.ticker for item in plan.securities if item.full_fetch
        ),
        "base_data_snapshot_id": base_id,
        "data_snapshot_id": after_hash,
        "store_content_hash_unchanged": after_hash == base_hash,
        "incremental_snapshot_id": snapshot_id,
        "change_set": {
            "count": len(change_keys),
            "truncated": truncated,
            "keys": capped_keys,
        },
        "changed_securities": sorted(touched),
        "changed_years": dict(sorted(touched_years.items())),
        "price_rows_fetched": sum(len(rows) for rows in price_rows.values()),
        "price_dates_new": len(price_keys) - price_restated,
        "price_dates_restated": price_restated,
        "dividend_events_new_or_restated": len(dividend_keys),
        "dividend_events_restated": dividend_restated,
        "corporate_actions_new_or_restated": len(action_keys),
        "corporate_actions_restated": action_restated,
        "corporate_action_errors": action_errors,
        "fx_rows_new_or_restated": len(fx_keys),
        "fx_rows_restated": fx_restated,
        "fx_fetch_errors": fx_errors,
        "updated": sum(result.status == DataQualityStatus.OK for result in results),
        "warnings": sum(result.status == DataQualityStatus.WARNING for result in results),
        "failed": sum(result.status == DataQualityStatus.FAILED for result in results),
        "dividends": dividend_report.model_dump(mode="json"),
        "dividend_coverage_warnings": dividend_coverage_warnings,
        "dividend_updates": [result.model_dump(mode="json") for result in dividend_results],
        "fx_rows_written": fx_rows_written,
        "provider_warnings": batch_warnings,
        "results": [
            {
                **result.model_dump(mode="json", exclude={"manifests"}),
                "partitions_written": len(result.manifests),
            }
            for result in results
        ],
        "packs": packs_payload,
    }
    (root_path / "data" / "update_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root (default: script parent).")
    parser.add_argument(
        "--since",
        default="auto",
        help="'auto' (per-security last stored date) or YYYY-MM-DD for gap backfill.",
    )
    parser.add_argument(
        "--securities",
        default=None,
        help="Comma-separated tickers or security_ids (default: all catalog securities).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what WOULD be fetched and rebuilt; no network calls, no writes.",
    )
    parser.add_argument(
        "--no-build-packs",
        action="store_true",
        help="Skip the scoped pack rebuild and manifest merge.",
    )
    parser.add_argument(
        "--skip-actions",
        action="store_true",
        help="Skip corporate-action reconciliation (yfinance .actions is an unbounded per-ticker fetch).",
    )
    parser.add_argument(
        "--reconciliation-days",
        type=int,
        default=RECONCILIATION_DAYS_DEFAULT,
        help=f"Trailing reconciliation window (default: {RECONCILIATION_DAYS_DEFAULT}).",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Documented but NOT implemented: CI auto-commit. See docs/data-updates.md.",
    )
    args = parser.parse_args(argv)
    if args.commit:
        print(
            "NOTE: --commit is documented but intentionally not implemented; "
            "see docs/data-updates.md ('Applying CI artifacts').",
            file=sys.stderr,
        )
    selectors = (
        [item.strip() for item in args.securities.split(",") if item.strip()]
        if args.securities
        else None
    )
    try:
        summary = run_incremental_update(
            args.root,
            since=args.since,
            securities=selectors,
            dry_run=args.dry_run,
            build_packs=not args.no_build_packs,
            skip_actions=args.skip_actions,
            reconciliation_days=args.reconciliation_days,
        )
    except ValueError as error:
        parser.error(str(error))
        return 2  # pragma: no cover - parser.error exits
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
