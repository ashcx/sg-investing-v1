"""Versioned browser data-pack construction from the canonical Parquet store.

Sprint 1 (Todo/sprint-1-data-packs.md): publish partitioned, lazy-loadable
JSON packs under ``security=<security_id>/year=<YYYY>.json`` plus a manifest
that answers, before any calculation, whether a security/date range is fully
supported, incomplete or unavailable. This module only republishes canonical
store data; it performs no financial calculations.

Value encoding (see docs/data-pack-schema.md): monetary amounts and FX rates
are JSON strings holding exact decimal numerals (the browser engine parses
them with decimal.js); dates are ISO-8601 strings; volumes are integers.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import median

import pyarrow.parquet as pq

from sg_investing.models import CorporateAction, DividendEvent

PACK_SCHEMA_VERSION = 1
MANIFEST_VERSION = 1
METHODOLOGY_VERSION = "1.0"
# Mirrors analysis.py: the engine warns when a resolved FX rate is older.
MAX_FX_STALENESS_DAYS = 7
# Extra FX history included before a pack's first price date so the browser
# can apply the engine's previous-trading-day rule at window edges.
FX_LOOKBACK_CALENDAR_DAYS = 10
SGD = "SGD"
STATUS_FULLY_SUPPORTED = "fully_supported"
STATUS_INCOMPLETE = "incomplete"
STATUS_UNAVAILABLE = "unavailable"
PACK_PATH_TEMPLATE = "security={security_id}/year={year}.json"
MANIFEST_NAME = "manifest.json"
_MAX_SHOWN_DATES = 5


def pack_path(security_id: str, year: int) -> str:
    return PACK_PATH_TEMPLATE.format(security_id=security_id, year=year)


def decimal_text(value: Decimal) -> str:
    """Exact decimal numeral with trailing storage zeros stripped."""

    return format(value.normalize(), "f")


def compute_data_snapshot_id(data_root: str | Path) -> str:
    """Content hash identifying one validated canonical snapshot.

    Every file under the data directory contributes its relative path and
    bytes to one SHA-256 digest, so identical store contents always produce
    the same id and any store change produces a new one.
    """

    root = Path(data_root)
    if not root.is_dir():
        raise ValueError(f"Data directory does not exist: {root}")
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    return f"sha256-{digest.hexdigest()}"


@dataclass(frozen=True)
class CatalogSnapshot:
    """Validated catalog metadata plus a content-derived version string."""

    securities: dict[str, dict]
    universes: dict[str, list[dict]]
    version: str
    as_of: str | None
    history_start: str | None


def load_catalog_snapshot(root: str | Path) -> CatalogSnapshot:
    root_path = Path(root)
    catalog_path = root_path / "data" / "universe" / "current_catalog.json"
    if not catalog_path.exists():
        raise ValueError(f"Catalog snapshot not found: {catalog_path}")
    from sg_investing.universe.catalog import load_catalog

    catalog = load_catalog(catalog_path)
    securities: dict[str, dict] = {}
    universes: dict[str, list[dict]] = {}
    for entry in catalog.securities:
        identifier = str(entry.security.security_id)
        securities[identifier] = entry.security.model_dump(mode="json")
        universes.setdefault(identifier, []).append(
            {
                "universe": entry.universe,
                "effective_from": entry.effective_from.isoformat(),
                "source": entry.source,
            }
        )
    version = "sha256-" + hashlib.sha256(catalog_path.read_bytes()).hexdigest()[:16]
    summary_path = root_path / "data" / "universe" / "summary.json"
    as_of = None
    if summary_path.exists():
        as_of = json.loads(summary_path.read_text(encoding="utf-8")).get("as_of")
    return CatalogSnapshot(
        securities=securities,
        universes=universes,
        version=version,
        as_of=as_of,
        history_start=catalog.history_start.isoformat(),
    )


class StoreContext:
    """Lazy accessors for FX, dividends and corporate actions of a snapshot."""

    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root)
        self._fx_series: dict[str, tuple[list[date], list[Decimal]]] = {}
        self._dividends: dict[str, list[dict]] | None = None
        self._actions: dict[str, list[dict]] | None = None
        self._dividend_coverage: dict[str, dict] | None = None

    def dividend_coverage_for(self, security_id: str) -> dict | None:
        """Slimmed dividend-coverage record for a security, or ``None``.

        Sourced from the dividend coverage report so the browser can explain
        zero-dividend results the same way the Python artifacts do (e.g.
        ``known_distributing_with_no_events`` vs ``dividend_data_missing``).
        """

        if self._dividend_coverage is None:
            report_path = self.data_root / "dividends" / "coverage_report.json"
            records: dict[str, dict] = {}
            if report_path.exists():
                report = json.loads(report_path.read_text(encoding="utf-8"))
                fields = (
                    "coverage_status",
                    "distribution_policy",
                    "event_count",
                    "first_event_date",
                    "last_event_date",
                    "event_currencies",
                    "provider_query_succeeded",
                    "queried_from",
                    "queried_through",
                    "error",
                )
                for record in report.get("securities", []):
                    identifier = record.get("security_id")
                    if identifier:
                        records[identifier] = {field: record.get(field) for field in fields}
            self._dividend_coverage = records
        return self._dividend_coverage.get(security_id)

    def fx_series(self, currency: str) -> tuple[list[date], list[Decimal]]:
        """Sorted (dates, rates) for ``currency``/SGD; empty when absent."""

        if currency not in self._fx_series:
            dates: list[date] = []
            rates: list[Decimal] = []
            pair_dir = self.data_root / "fx" / f"pair={currency.upper()}_SGD"
            if pair_dir.is_dir():
                for path in sorted(pair_dir.glob("year=*.parquet")):
                    table = pq.read_table(path, columns=["rate_date", "rate_to_sgd"])
                    for row in table.to_pylist():
                        dates.append(date.fromisoformat(row["rate_date"]))
                        rates.append(Decimal(str(row["rate_to_sgd"])))
            ordered = sorted(zip(dates, rates, strict=True))
            self._fx_series[currency] = (
                [item[0] for item in ordered],
                [item[1] for item in ordered],
            )
        return self._fx_series[currency]

    def available_fx_pairs(self) -> list[str]:
        fx_root = self.data_root / "fx"
        if not fx_root.is_dir():
            return []
        return sorted(item.name.split("=", 1)[1] for item in fx_root.iterdir() if item.is_dir())

    def dividends_for(self, security_id: str) -> list[dict]:
        if self._dividends is None:
            self._dividends = _load_dividends(self.data_root)
        return self._dividends.get(security_id, [])

    def actions_for(self, security_id: str) -> list[dict]:
        if self._actions is None:
            self._actions = _load_corporate_actions(self.data_root)
        return self._actions.get(security_id, [])


def _load_dividends(data_root: Path) -> dict[str, list[dict]]:
    by_security: dict[str, list[dict]] = {}
    for path in sorted((data_root / "dividends").glob("year=*.parquet")):
        for row in pq.read_table(path).to_pylist():
            event = DividendEvent.model_validate(row)
            payload = {
                "ex_date": event.ex_date.isoformat(),
                "amount": decimal_text(event.amount),
                "currency": event.currency,
                "pay_date": event.pay_date.isoformat() if event.pay_date else None,
                "record_date": event.record_date.isoformat() if event.record_date else None,
                "dividend_type": event.dividend_type.value,
                "source_id": event.source_id,
                "source_country": event.source_country,
                "source": event.source,
                "retrieved_at": event.retrieved_at.isoformat(),
            }
            by_security.setdefault(str(event.security_id), []).append(payload)
    return by_security


def _load_corporate_actions(data_root: Path) -> dict[str, list[dict]]:
    by_security: dict[str, list[dict]] = {}
    for path in sorted((data_root / "corporate_actions").glob("year=*.parquet")):
        for row in pq.read_table(path).to_pylist():
            action = CorporateAction.model_validate(row)
            payload = {
                "effective_date": action.effective_date.isoformat(),
                "action_type": action.action_type.value,
                "ratio": decimal_text(action.ratio),
                "source": action.source,
                "retrieved_at": action.retrieved_at.isoformat(),
            }
            by_security.setdefault(str(action.security_id), []).append(payload)
    return by_security


def classify_price_dates(
    price_dates: list[date], fx_dates: list[date] | None
) -> tuple[int, int, int]:
    """Classify FX resolvability using the engine's previous-trading-day rule.

    Returns ``(missing_fx_dates, stale_fx_dates, max_staleness_days)``. A date
    with no rate on or before it cannot be resolved by the engine at all; a
    date resolving with a lag beyond ``MAX_FX_STALENESS_DAYS`` corresponds to
    the engine's staleness warning.
    """

    if not fx_dates:
        return len(price_dates), 0, 0
    missing = 0
    stale = 0
    max_lag = 0
    for requested in price_dates:
        index = bisect_right(fx_dates, requested) - 1
        if index < 0:
            missing += 1
            continue
        lag = (requested - fx_dates[index]).days
        max_lag = max(max_lag, lag)
        if lag > MAX_FX_STALENESS_DAYS:
            stale += 1
    return missing, stale, max_lag


def classify_range(entry: dict, start: str | date, end: str | date) -> dict:
    """Resolve support status for ``[start, end]`` from one manifest entry.

    Rules (frozen in docs/data-pack-schema.md): the status is the worst of the
    intersecting in-window years, where a mix of statuses is ``incomplete``;
    a range intersecting no data year is ``unavailable``. Range edges before
    or after the security's own price window are tolerated (the engine
    resolves purchases and valuations to the nearest trading day) and are
    surfaced as informational reasons.
    """

    start_day = date.fromisoformat(start) if isinstance(start, str) else start
    end_day = date.fromisoformat(end) if isinstance(end, str) else end
    if end_day < start_day:
        raise ValueError(f"Invalid range: {start_day} > {end_day}")
    years = entry.get("years") or {}
    first_date = entry.get("first_date")
    last_date = entry.get("last_date")
    if not years or not first_date or not last_date:
        return {
            "status": STATUS_UNAVAILABLE,
            "reasons": ["security has no price data in this snapshot"],
            "packs": [],
            "years": {},
        }
    first_day = date.fromisoformat(first_date)
    last_day = date.fromisoformat(last_date)
    if end_day < first_day or start_day > last_day:
        return {
            "status": STATUS_UNAVAILABLE,
            "reasons": [
                f"requested range does not overlap available coverage {first_date}..{last_date}"
            ],
            "packs": [],
            "years": {},
        }
    first_year = int(first_date[:4])
    last_year = int(last_date[:4])
    reasons: list[str] = []
    statuses: set[str] = set()
    year_status: dict[str, str] = {}
    packs: list[str] = []
    for year in range(max(start_day.year, first_year), min(end_day.year, last_year) + 1):
        key = str(year)
        detail = years.get(key)
        if detail is None:
            statuses.add(STATUS_UNAVAILABLE)
            year_status[key] = STATUS_UNAVAILABLE
            reasons.append(f"year {year} has no price data inside the security window")
            continue
        status = detail["status"]
        statuses.add(status)
        year_status[key] = status
        if "pack" in detail:
            packs.append(detail["pack"])
        if status == STATUS_INCOMPLETE:
            reasons.append(f"year {year} is incomplete: {'; '.join(detail.get('warnings', []))}")
    if start_day < first_day:
        reasons.append(
            f"requested start precedes first available price date {first_date}; "
            "the engine resolves the purchase to the next trading day"
        )
    if end_day > last_day:
        reasons.append(
            f"requested end follows last available price date {last_date}; "
            "the engine resolves the valuation to the previous trading day"
        )
    if not statuses:
        status = STATUS_UNAVAILABLE
    elif statuses == {STATUS_FULLY_SUPPORTED}:
        status = STATUS_FULLY_SUPPORTED
    elif statuses == {STATUS_UNAVAILABLE}:
        status = STATUS_UNAVAILABLE
    else:
        status = STATUS_INCOMPLETE
    return {"status": status, "reasons": reasons, "packs": packs, "years": year_status}


def _pack_metadata(
    catalog: CatalogSnapshot, security_id: str, rows: list[dict], market: str
) -> dict:
    known = catalog.securities.get(security_id)
    first_row = rows[0]
    metadata = {
        "security_id": security_id,
        "ticker": None,
        "name": None,
        "exchange": first_row.get("exchange"),
        "market": market,
        "currency": first_row.get("currency"),
        "asset_type": None,
        "domicile": None,
        "income_source_country": None,
        "isin": None,
        "cusip": None,
        "timezone": first_row.get("timezone"),
        "active": None,
        "distribution_policy": None,
        "expense_ratio": None,
        "universes": [],
        "in_current_catalog": False,
    }
    if known is not None:
        metadata.update(known)
        metadata["universes"] = catalog.universes.get(security_id, [])
        metadata["in_current_catalog"] = True
        metadata["market"] = known.get("market") or market
    return metadata


def _fx_block(rows: list[dict], currency: str, series: tuple[list[date], list[Decimal]]) -> dict:
    lookback = rows[0]["trading_date"] - timedelta(days=FX_LOOKBACK_CALENDAR_DAYS)
    horizon = rows[-1]["trading_date"]
    fx_dates, fx_rates = series
    start = bisect_left(fx_dates, lookback)
    stop = bisect_right(fx_dates, horizon)
    return {
        "base_currency": currency,
        "quote_currency": SGD,
        "dates": [fx_dates[index].isoformat() for index in range(start, stop)],
        "rates": [decimal_text(fx_rates[index]) for index in range(start, stop)],
        "series_first_date": fx_dates[0].isoformat() if fx_dates else None,
        "series_last_date": fx_dates[-1].isoformat() if fx_dates else None,
    }


def _classify_year(
    rows: list[dict], calendar: set[date], currency: str, series: tuple[list[date], list[Decimal]]
) -> dict:
    dates = [row["trading_date"] for row in rows]
    first_date = dates[0]
    last_date = dates[-1]
    requires_fx = currency != SGD
    missing_fx = stale_fx = max_lag = 0
    if requires_fx:
        missing_fx, stale_fx, max_lag = classify_price_dates(dates, series[0] or None)
    security_dates = set(dates)
    missing_calendar = sorted(
        day for day in calendar if first_date <= day <= last_date and day not in security_dates
    )
    status = STATUS_INCOMPLETE if (missing_fx or missing_calendar) else STATUS_FULLY_SUPPORTED
    warnings: list[str] = []
    if missing_fx:
        warnings.append(
            f"{missing_fx} price dates have no {currency}/{SGD} rate on or before them; "
            "SGD analysis would fail for these dates."
        )
    if stale_fx:
        warnings.append(
            f"{stale_fx} price dates resolve with {currency}/{SGD} FX staleness up to "
            f"{max_lag} days (engine limit {MAX_FX_STALENESS_DAYS})."
        )
    if missing_calendar:
        shown = ", ".join(day.isoformat() for day in missing_calendar[:_MAX_SHOWN_DATES])
        suffix = "…" if len(missing_calendar) > _MAX_SHOWN_DATES else ""
        warnings.append(
            f"{len(missing_calendar)} market-calendar dates lack price bars in "
            f"{first_date.isoformat()}..{last_date.isoformat()}: {shown}{suffix}"
        )
    return {
        "status": status,
        "rows": len(rows),
        "first_date": first_date.isoformat(),
        "last_date": last_date.isoformat(),
        "requires_fx": requires_fx,
        "missing_fx_dates": missing_fx,
        "stale_fx_dates": stale_fx,
        "max_fx_staleness_days": max_lag,
        "missing_calendar_dates": len(missing_calendar),
        "warnings": warnings,
    }


def _build_security_year_pack(
    *,
    security_id: str,
    market: str,
    year: int,
    rows: list[dict],
    calendar: set[date],
    catalog: CatalogSnapshot,
    context: StoreContext,
    data_snapshot_id: str,
    catalog_version: str,
    generated_at: str,
    partition_manifest: dict | None,
) -> tuple[dict, dict]:
    metadata = _pack_metadata(catalog, security_id, rows, market)
    coverage_record = context.dividend_coverage_for(security_id)
    if coverage_record is not None:
        metadata["dividend_coverage"] = coverage_record
    currency = metadata["currency"]
    requires_fx = currency != SGD
    series = context.fx_series(currency) if requires_fx else ([], [])
    classification = _classify_year(rows, calendar, currency, series)
    sources = sorted({row["source"] for row in rows})
    retrieved = [row["retrieved_at"] for row in rows]
    dividend_events = sorted(
        (
            event
            for event in context.dividends_for(security_id)
            if event["ex_date"][:4] == str(year)
        ),
        key=lambda item: (item["ex_date"], item["amount"]),
    )
    actions = sorted(
        context.actions_for(security_id), key=lambda item: item["effective_date"]
    )
    pack_warnings = list(classification["warnings"])
    if not metadata["in_current_catalog"]:
        pack_warnings.append(
            "security is priced in the store but absent from the current catalog snapshot"
        )
    pack = {
        "schema_version": PACK_SCHEMA_VERSION,
        "pack_type": "security_year",
        "generated_at": generated_at,
        "data_snapshot_id": data_snapshot_id,
        "catalog_version": catalog_version,
        "catalog_as_of": catalog.as_of,
        "methodology_version": METHODOLOGY_VERSION,
        "partition": {"security_id": security_id, "market": market, "year": year},
        "security": metadata,
        "coverage": {
            "first_date": classification["first_date"],
            "last_date": classification["last_date"],
            "row_count": classification["rows"],
            "native_currency": currency,
            "requires_fx": requires_fx,
            "fx_base_currency": currency if requires_fx else None,
        },
        "provenance": {
            "source": sources[0] if len(sources) == 1 else "multiple",
            "sources": sources,
            "retrieved_at": {
                "first": min(retrieved).isoformat(),
                "last": max(retrieved).isoformat(),
            },
            "pipeline_version": (partition_manifest or {}).get("pipeline_version"),
            "partition_manifest": (
                f"manifests/prices/market={market.upper()}/year={year}.json"
                if partition_manifest is not None
                else None
            ),
            "builder": "sg_investing.data.packs",
        },
        "data_quality": {
            "status": classification["status"],
            "missing_fx_dates": classification["missing_fx_dates"],
            "stale_fx_dates": classification["stale_fx_dates"],
            "max_fx_staleness_days": classification["max_fx_staleness_days"],
            "missing_calendar_dates": classification["missing_calendar_dates"],
        },
        "warnings": pack_warnings,
        "prices": {
            "dates": [row["trading_date"].isoformat() for row in rows],
            "open": [decimal_text(row["open"]) for row in rows],
            "high": [decimal_text(row["high"]) for row in rows],
            "low": [decimal_text(row["low"]) for row in rows],
            "close": [decimal_text(row["close"]) for row in rows],
            "volume": [row["volume"] for row in rows],
        },
        "fx": _fx_block(rows, currency, series) if requires_fx else None,
        "dividends": dividend_events,
        "corporate_actions": actions,
    }
    entry = {
        "status": classification["status"],
        "rows": classification["rows"],
        "first_date": classification["first_date"],
        "last_date": classification["last_date"],
        "missing_fx_dates": classification["missing_fx_dates"],
        "stale_fx_dates": classification["stale_fx_dates"],
        "max_fx_staleness_days": classification["max_fx_staleness_days"],
        "missing_calendar_dates": classification["missing_calendar_dates"],
        "warnings": classification["warnings"],
    }
    return pack, entry


def _rollup_status(years: dict[str, dict]) -> str:
    if not years:
        return STATUS_UNAVAILABLE
    first_year = min(int(key) for key in years)
    last_year = max(int(key) for key in years)
    incomplete = any(detail["status"] == STATUS_INCOMPLETE for detail in years.values())
    hole = (last_year - first_year + 1) != len(years)
    if incomplete or hole:
        return STATUS_INCOMPLETE
    return STATUS_FULLY_SUPPORTED


def _reset_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict, *, pretty: bool = False) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if pretty:
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    else:
        text = json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    return path.stat().st_size


def _read_partition_manifest(data_root: Path, market: str, year: int) -> dict | None:
    path = data_root / "manifests" / "prices" / f"market={market.upper()}" / f"year={year}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_price_partitions(
    data_root: Path, markets: frozenset[str] | None
) -> Iterator[tuple[str, int, Path]]:
    prices_root = data_root / "prices"
    if not prices_root.is_dir():
        return
    for market_dir in sorted(prices_root.glob("market=*")):
        market = market_dir.name.split("=", 1)[1]
        if markets is not None and market not in markets:
            continue
        for path in sorted(market_dir.glob("year=*.parquet")):
            yield market, int(path.stem.split("=", 1)[1]), path


def _manifest_entry(
    security_id: str,
    years: dict[str, dict],
    native_currency: str | None,
    catalog: CatalogSnapshot,
    context: StoreContext,
) -> dict:
    known = catalog.securities.get(security_id)
    row_total = sum(detail["rows"] for detail in years.values())
    first_dates = [detail["first_date"] for detail in years.values()]
    last_dates = [detail["last_date"] for detail in years.values()]
    warnings: list[str] = []
    if known is None:
        warnings.append("priced in the store but absent from the current catalog snapshot")
    elif not years:
        warnings.append("no price data in the canonical store")
    elif known.get("distribution_policy") == "distributing" and not any(
        context.dividends_for(security_id)
    ):
        warnings.append("no dividend events recorded for a distributing security")
    return {
        "security_id": security_id,
        "ticker": (known or {}).get("ticker"),
        "name": (known or {}).get("name"),
        "market": (known or {}).get("market"),
        "exchange": (known or {}).get("exchange"),
        "native_currency": native_currency or (known or {}).get("currency"),
        "asset_type": (known or {}).get("asset_type"),
        "domicile": (known or {}).get("domicile"),
        "isin": (known or {}).get("isin"),
        "distribution_policy": (known or {}).get("distribution_policy"),
        "universes": catalog.universes.get(security_id, []),
        "in_current_catalog": known is not None,
        "status": _rollup_status(years),
        "first_date": min(first_dates) if first_dates else None,
        "last_date": max(last_dates) if last_dates else None,
        "first_year": min((int(key) for key in years), default=None),
        "last_year": max((int(key) for key in years), default=None),
        "row_count": row_total,
        "years": years,
        "warnings": warnings,
    }


def _fx_coverage(context: StoreContext, entries: list[dict]) -> dict:
    coverage: dict[str, dict] = {}
    for entry in entries:
        currency = entry.get("native_currency")
        if not currency or currency == SGD or currency in coverage:
            continue
        dates, _ = context.fx_series(currency)
        if dates:
            coverage[currency] = {
                "first_date": dates[0].isoformat(),
                "last_date": dates[-1].isoformat(),
                "available": True,
            }
        else:
            coverage[currency] = {"first_date": None, "last_date": None, "available": False}
    return coverage


def _manifest_warnings(entries: list[dict], context: StoreContext) -> list[str]:
    warnings: list[str] = []
    unavailable = sum(1 for entry in entries if entry["status"] == STATUS_UNAVAILABLE)
    outside = sum(1 for entry in entries if not entry["in_current_catalog"])
    if unavailable:
        warnings.append(f"{unavailable} catalog securities have no price data in this snapshot.")
    if outside:
        warnings.append(
            f"{outside} priced securities are not present in the current catalog snapshot."
        )
    required_pairs = {
        entry["native_currency"]
        for entry in entries
        if entry["status"] != STATUS_UNAVAILABLE
        and entry["native_currency"]
        and entry["native_currency"] != SGD
    }
    missing_pairs = sorted(currency for currency in required_pairs if not context.fx_series(currency)[0])
    if missing_pairs:
        warnings.append(f"No FX history is available for required pairs: {', '.join(missing_pairs)}.")
    distributing_without_dividends = sum(
        1
        for entry in entries
        if entry["in_current_catalog"]
        and entry.get("distribution_policy") == "distributing"
        and not any(context.dividends_for(entry["security_id"]))
    )
    if distributing_without_dividends:
        warnings.append(
            f"{distributing_without_dividends} distributing securities have no dividend events recorded."
        )
    return warnings


def build_data_packs(
    root: str | Path,
    output_dir: str | Path | None = None,
    *,
    security_ids: Iterable[str] | None = None,
    markets: Iterable[str] | None = None,
    pretty_manifest: bool = False,
) -> dict:
    """Build every security/year pack plus the manifest for one snapshot.

    Returns a deterministic summary (no timestamps) for logging and tests.
    """

    root_path = Path(root)
    data_root = root_path / "data"
    target = (
        Path(output_dir) if output_dir is not None else root_path / "frontend" / "data" / "packs"
    )
    if target == data_root or data_root in target.parents or target in data_root.parents:
        raise ValueError("Refusing to build packs inside the canonical data directory.")
    wanted_ids = frozenset(security_ids) if security_ids is not None else None
    wanted_markets = frozenset(markets) if markets is not None else None

    data_snapshot_id = compute_data_snapshot_id(data_root)
    catalog = load_catalog_snapshot(root_path)
    context = StoreContext(data_root)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")

    _reset_output_dir(target)
    years_by_security: dict[str, dict[str, dict]] = {}
    currency_by_security: dict[str, str] = {}
    pack_count = 0
    total_bytes = 0
    price_rows = 0
    source_counts: dict[str, int] = {}
    pack_sizes: list[int] = []

    for market, year, path in _iter_price_partitions(data_root, wanted_markets):
        table = pq.read_table(path)
        if table.num_rows == 0:
            continue
        partition_manifest = _read_partition_manifest(data_root, market, year)
        security_column = table.column("security_id").to_pylist()
        indices: dict[str, list[int]] = {}
        for index, security_id in enumerate(security_column):
            indices.setdefault(security_id, []).append(index)
        calendar = set(table.column("trading_date").to_pylist())
        for security_id in sorted(indices):
            if wanted_ids is not None and security_id not in wanted_ids:
                continue
            rows = sorted(
                table.take(indices[security_id]).to_pylist(),
                key=lambda row: row["trading_date"],
            )
            pack, entry = _build_security_year_pack(
                security_id=security_id,
                market=market,
                year=year,
                rows=rows,
                calendar=calendar,
                catalog=catalog,
                context=context,
                data_snapshot_id=data_snapshot_id,
                catalog_version=catalog.version,
                generated_at=generated_at,
                partition_manifest=partition_manifest,
            )
            relative = pack_path(security_id, year)
            written = _write_json(target / relative, pack)
            entry["pack"] = relative
            entry["bytes"] = written
            years_by_security.setdefault(security_id, {})[str(year)] = entry
            currency_by_security[security_id] = pack["coverage"]["native_currency"]
            pack_count += 1
            total_bytes += written
            pack_sizes.append(written)
            price_rows += len(rows)
            for source in pack["provenance"]["sources"]:
                source_counts[source] = source_counts.get(source, 0) + 1
        del table

    manifest_source = max(source_counts, key=lambda key: source_counts[key]) if source_counts else None
    catalog_ids = (
        {
            security_id
            for security_id, known in catalog.securities.items()
            if wanted_markets is None or known.get("market") in wanted_markets
        }
        if wanted_ids is None
        else set()
    )
    manifest_securities = [
        _manifest_entry(
            security_id,
            years_by_security.get(security_id, {}),
            currency_by_security.get(security_id),
            catalog,
            context,
        )
        for security_id in sorted(set(years_by_security) | catalog_ids)
        if wanted_ids is None or security_id in wanted_ids
    ]
    support_counts = {STATUS_FULLY_SUPPORTED: 0, STATUS_INCOMPLETE: 0, STATUS_UNAVAILABLE: 0}
    for entry in manifest_securities:
        support_counts[entry["status"]] += 1

    manifest = {
        "schema_version": PACK_SCHEMA_VERSION,
        "manifest_version": MANIFEST_VERSION,
        "pack_type": "manifest",
        "generated_at": generated_at,
        "data_snapshot_id": data_snapshot_id,
        "catalog_version": catalog.version,
        "catalog_as_of": catalog.as_of,
        "history_start": catalog.history_start,
        "methodology_version": METHODOLOGY_VERSION,
        "source": manifest_source,
        "scope": {
            "security_ids": sorted(wanted_ids) if wanted_ids is not None else None,
            "markets": sorted(wanted_markets) if wanted_markets is not None else None,
        },
        "pack_layout": {
            "path_template": PACK_PATH_TEMPLATE,
            "partition_by": ["security_id", "year"],
            "pack_types": {
                "security_year": (
                    "daily native prices, FX window, dividend events, corporate "
                    "actions, coverage and provenance for one security-year"
                )
            },
        },
        "support": {
            "counts": support_counts,
            "range_query": (
                "classify_range(security_entry, start, end); "
                "see docs/data-pack-schema.md for the frozen rules"
            ),
        },
        "fx": {
            "available_pairs": context.available_fx_pairs(),
            "quote_currency": SGD,
            "coverage": _fx_coverage(context, manifest_securities),
        },
        "summary": {
            "securities": len(manifest_securities),
            "pack_count": pack_count,
            "total_bytes": total_bytes,
            "price_rows": price_rows,
            "pack_bytes": {
                "min": min(pack_sizes) if pack_sizes else None,
                "median": int(median(pack_sizes)) if pack_sizes else None,
                "max": max(pack_sizes) if pack_sizes else None,
            },
        },
        "warnings": _manifest_warnings(manifest_securities, context),
        "securities": manifest_securities,
    }
    manifest["summary"]["manifest_bytes"] = _write_json(
        target / MANIFEST_NAME, manifest, pretty=pretty_manifest
    )
    manifest["summary"]["total_bytes"] += manifest["summary"]["manifest_bytes"]

    return {
        "output_dir": str(target),
        "data_snapshot_id": data_snapshot_id,
        "catalog_version": catalog.version,
        "catalog_as_of": catalog.as_of,
        "pack_count": pack_count,
        "securities": len(manifest_securities),
        "price_rows": price_rows,
        "total_bytes": manifest["summary"]["total_bytes"],
        "manifest_bytes": manifest["summary"]["manifest_bytes"],
        "support_counts": support_counts,
        "warnings": manifest["warnings"],
    }
