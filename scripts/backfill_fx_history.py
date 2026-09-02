"""Backfill FX history (2000-01-01 to 2003-11-30) for the pairs that pre-2003-12
securities need.

Sprint 7.5 Track A, decision A0: MAS is the primary source, ECB (via
frankfurter.app) is the cross-check, and the pull is minimal — only dates that
are missing before each pair's existing first stored date are written, and no
existing 2003+ Yahoo FX row is touched. The MAS window is scaled by a
normalization ratio computed over the last month that overlaps the existing FX
series, so no level seam enters SGD returns.

Sourcing order (per A1): (a) the MAS datastore API on eservices.mas.gov.sg
(api.mas.gov.sg does not resolve); (b) MAS website statistical-table downloads;
(c) the data.gov.sg mirror of MAS datasets. Every attempted path and its
blocker is recorded in the summary — a failed path is never silently
substituted, and per-pair window coverage (first/last observation, longest
date gap) is reported so an under-covering source cannot pass unnoticed.

Row contract (src/sg_investing/models.py::FxRate, unchanged):
``rate_date`` (ISO string), ``base_currency`` (3 letters), ``rate_to_sgd``
(decimal string; one unit foreign = X SGD), ``source``. Backfilled rows carry
``source: "mas"``. The model has no retrieved_at/normalized columns; adding one
would change the canonical schema (out of Track A scope), so normalization is
documented in docs/adr/0002-fx-sources.md and this script's summary instead.

Usage:
    .venv/bin/python scripts/backfill_fx_history.py            # dry run
    .venv/bin/python scripts/backfill_fx_history.py --write

Network is only touched by the fetch_* helpers (MAS/data.gov.sg/frankfurter
endpoints); tests drive the pure functions with synthetic fixtures.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import pyarrow.parquet as pq

from sg_investing.data.storage import ParquetStore
from sg_investing.models import FxRate

ROOT = Path(__file__).resolve().parents[1]

WINDOW_START = date(2000, 1, 1)
WINDOW_END = date(2003, 11, 30)
PAIR_CUTOFF = date(2003, 12, 1)
# The normalization month is the last month covered by BOTH the MAS pull and
# the existing store. Yahoo USD/SGD starts 2003-12-01 and the backfill window
# ends 2003-11-30, so there is no overlap inside the write window itself: the
# MAS pull extends through this date purely to measure the seam, and those
# rows are never written.
NORMALIZATION_PULL_END = date(2003, 12, 31)
MIN_OVERLAP_DATES = 5
# Divergences above this many basis points (1%) are flagged, never silently
# accepted (A1).
DIVERGENCE_FLAG_BPS = Decimal(100)
# A median MAS/ECB ratio in [50, 150] means MAS quotes S$ per 100 foreign units.
PER_100_RATIO_LOW = Decimal(50)
PER_100_RATIO_HIGH = Decimal(150)

SOURCE_NAME = "mas"
# api.mas.gov.sg does not resolve (NXDOMAIN, verified 2026-09-02 via Google and
# Cloudflare DoH). The real MAS CKAN datastore host is eservices.mas.gov.sg.
MAS_API_HOST = "https://eservices.mas.gov.sg/api"
# Legacy data.gov.sg resource id for MAS "Exchange Rates - Daily" (multi-currency).
MAS_API_RESOURCE_ID = "10bafb02-4b53-4b59-9f8b-35f2c4a4b62f"
MAS_WEBSITE_TABLE_URL = "https://www.mas.gov.sg/statistics/exchange-rates/daily-exchange-rates"
DATAGOVSG_LIST_ROWS_URL = (
    "https://api-production.data.gov.sg/v2/public/api/datasets/{dataset_id}/list-rows"
)
# data.gov.sg v2 id of the MAS daily exchange-rates dataset (verified against
# the live catalog 2026-09-02: "Exchange Rates, SGD per unit of USD, Daily",
# Monetary Authority of Singapore). The mirror survived the 2015->2018 data.gov.sg
# migration only partially: the list-rows view serves 1,000 weekly rows for USD
# (1988-01-08 -> 2003-11-12) and no other currency column.
DATAGOVSG_EXCHANGE_RATES_DAILY = "d_046ff8d521a218d9178178cfbfc45c2c"
DATAGOVSG_PACE_SECONDS = 5.0  # anonymous quota: 2-4 calls per 10s window
# Hard stop for cursor paging: a healthy dataset page never repeats itself.
DATAGOVSG_MAX_PAGES = 200


@dataclass(frozen=True)
class Divergence:
    mean_bps: Decimal
    max_bps: Decimal
    max_bps_date: date | None
    common_dates: int

    def as_dict(self) -> dict:
        return {
            "mean_bps": str(self.mean_bps.quantize(Decimal("0.1"))),
            "max_bps": str(self.max_bps.quantize(Decimal("0.1"))),
            "max_bps_date": self.max_bps_date.isoformat() if self.max_bps_date else None,
            "common_dates": self.common_dates,
            "flagged": self.max_bps > DIVERGENCE_FLAG_BPS,
        }


@dataclass
class PairSummary:
    currency: str
    required_reason: str
    existing_first_date: date | None
    mas_source_used: str | None = None
    mas_blockers: list[str] = field(default_factory=list)
    unit_scale: Decimal = Decimal(1)
    normalization_ratio: Decimal = Decimal(1)
    normalization_month: str | None = None
    mas_dates_fetched: int = 0
    rows_written: int = 0
    coverage: dict | None = None
    divergence: Divergence | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "currency": self.currency,
            "required_reason": self.required_reason,
            "existing_first_date": (
                self.existing_first_date.isoformat() if self.existing_first_date else None
            ),
            "mas_source_used": self.mas_source_used,
            "mas_blockers": self.mas_blockers,
            "unit_scale": str(self.unit_scale),
            "normalization_ratio": str(self.normalization_ratio.quantize(Decimal("0.000001"))),
            "normalization_month": self.normalization_month,
            "mas_dates_fetched": self.mas_dates_fetched,
            "rows_written": self.rows_written,
            "coverage": self.coverage,
            "divergence": self.divergence.as_dict() if self.divergence else None,
            "error": self.error,
        }


class MasUnavailable(RuntimeError):
    """A MAS sourcing path is unreachable; the reason is reported, never hidden."""


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested; no network)
# ---------------------------------------------------------------------------


def derive_required_pairs(data_root: Path) -> dict[str, date]:
    """Currencies of securities with price data before 2003-12-01.

    Returns currency -> earliest pre-cutoff price date. SGD is excluded (no FX
    needed) and markets without pre-cutoff rows contribute nothing.
    """

    earliest: dict[str, date] = {}
    prices_root = data_root / "prices"
    if not prices_root.is_dir():
        return earliest
    for market_dir in sorted(prices_root.glob("market=*")):
        for path in sorted(
            market_dir.glob("year=*.parquet"), key=lambda p: int(p.stem.split("=")[1])
        ):
            year = int(path.stem.split("=")[1])
            if year > PAIR_CUTOFF.year:
                continue
            table = pq.read_table(path, columns=["currency", "trading_date"])
            for currency, trading_date in zip(
                table.column("currency").to_pylist(),
                table.column("trading_date").to_pylist(),
                strict=True,
            ):
                if currency == "SGD" or trading_date >= PAIR_CUTOFF:
                    continue
                if currency not in earliest or trading_date < earliest[currency]:
                    earliest[currency] = trading_date
    return earliest


def existing_fx_series(data_root: Path, currency: str) -> dict[date, Decimal]:
    """All stored dates/rates for ``currency``/SGD across every year partition."""

    pair_dir = data_root / "fx" / f"pair={currency.upper()}_SGD"
    series: dict[date, Decimal] = {}
    if not pair_dir.is_dir():
        return series
    for path in sorted(pair_dir.glob("year=*.parquet")):
        table = pq.read_table(path, columns=["rate_date", "rate_to_sgd"])
        for row in table.to_pylist():
            series[date.fromisoformat(row["rate_date"])] = Decimal(str(row["rate_to_sgd"]))
    return series


def detect_unit_scale(
    mas_by_date: dict[date, Decimal], ecb_by_date: dict[date, Decimal]
) -> Decimal:
    """1 or 100: whether MAS quotes S$ per 1 or per 100 foreign units.

    Some MAS statistical tables quote selected currencies per 100 units. The
    scale is detected against the ECB cross-check so a mis-read of the table's
    units cannot silently corrupt levels.
    """

    ratios = [
        mas_by_date[d] / ecb_by_date[d]
        for d in sorted(set(mas_by_date) & set(ecb_by_date))
        if ecb_by_date[d] != 0
    ]
    if not ratios:
        return Decimal(1)
    ratios.sort()
    median = ratios[len(ratios) // 2]
    if PER_100_RATIO_LOW <= median <= PER_100_RATIO_HIGH:
        return Decimal(100)
    return Decimal(1)


def compute_normalization_ratio(
    mas_by_date: dict[date, Decimal],
    existing_by_date: dict[date, Decimal],
    min_overlap_dates: int = MIN_OVERLAP_DATES,
) -> tuple[Decimal, str | None]:
    """Mean ``existing / mas`` over the last month present in both series.

    Returns ``(Decimal("1"), None)`` when the two series never share a month
    (e.g. a pair with no stored history at all): with no reference level there
    is no seam to remove, so the MAS rates are written as-is.
    """

    by_month_mas: dict[str, list[date]] = defaultdict(list)
    for day in mas_by_date:
        by_month_mas[day.strftime("%Y-%m")].append(day)
    best_month: str | None = None
    best_dates: list[date] = []
    for month, days in sorted(by_month_mas.items(), reverse=True):
        common = [d for d in days if d in existing_by_date]
        if len(common) >= min_overlap_dates:
            best_month = month
            best_dates = common
            break
    if best_month is None:
        return Decimal(1), None
    ratios = [existing_by_date[d] / mas_by_date[d] for d in best_dates]
    mean = sum(ratios, Decimal(0)) / Decimal(len(ratios))
    return mean.quantize(Decimal("0.000000000001")), best_month


def build_fx_rows(
    mas_by_date: dict[date, Decimal],
    *,
    currency: str,
    unit_scale: Decimal,
    normalization_ratio: Decimal,
    existing_dates: set[date],
    window_end: date = WINDOW_END,
) -> list[FxRate]:
    """Convert raw MAS observations to store rows, keeping only missing dates.

    Rows are scaled by ``unit_scale * normalization_ratio`` and restricted to
    dates at or before ``window_end`` that the store does not already have, so
    the existing 2003+ Yahoo series is never rewritten.
    """

    rows: list[FxRate] = []
    seen: set[date] = set()
    for day in sorted(mas_by_date):
        if day > window_end or day in existing_dates:
            continue
        if day in seen:
            continue
        seen.add(day)
        rate = mas_by_date[day] * unit_scale * normalization_ratio
        rows.append(
            FxRate(
                rate_date=day,
                base_currency=currency,
                rate_to_sgd=rate,
                source=SOURCE_NAME,
            )
        )
    return rows


def coverage_gaps(
    rates_by_date: dict[date, Decimal], window_start: date, window_end: date
) -> dict:
    """Quantify how completely ``rates_by_date`` covers the backfill window.

    A1 requires the exact gap to be reported when a source cannot cover the
    window: the first/last observed date and the longest calendar stretch with
    no observation (including the head/tail against the window bounds).
    """

    days = sorted(day for day in rates_by_date if window_start <= day <= window_end)
    if not days:
        return {
            "first": None,
            "last": None,
            "observations": 0,
            "longest_gap_days": (window_end - window_start).days,
            "longest_gap": [window_start.isoformat(), window_end.isoformat()],
        }
    # Boundary gaps count every day without an observation; interior gaps count
    # the days strictly between two consecutive observations.
    head_days = (days[0] - window_start).days
    tail_days = (window_end - days[-1]).days
    longest_days = max(head_days, tail_days)
    longest_span = (window_start, days[0]) if head_days >= tail_days else (days[-1], window_end)
    for left, right in pairwise(days):
        missing_days = (right - left).days - 1
        if missing_days > longest_days:
            longest_days = missing_days
            longest_span = (left, right)
    return {
        "first": days[0].isoformat(),
        "last": days[-1].isoformat(),
        "observations": len(days),
        "longest_gap_days": longest_days,
        "longest_gap": [longest_span[0].isoformat(), longest_span[1].isoformat()],
    }


def cross_check_divergence(
    mas_by_date: dict[date, Decimal], ecb_by_date: dict[date, Decimal]
) -> Divergence | None:
    """Mean/max divergence in basis points between the two sources."""

    common = sorted(set(mas_by_date) & set(ecb_by_date))
    if not common:
        return None
    bps = [abs(mas_by_date[d] - ecb_by_date[d]) / ecb_by_date[d] * Decimal(10000) for d in common]
    worst_index = max(range(len(bps)), key=lambda i: bps[i])
    mean = sum(bps, Decimal(0)) / Decimal(len(bps))
    return Divergence(
        mean_bps=mean,
        max_bps=bps[worst_index],
        max_bps_date=common[worst_index],
        common_dates=len(common),
    )


# ---------------------------------------------------------------------------
# Fetchers (network). Only MAS/data.gov.sg/frankfurter endpoints are used.
# ---------------------------------------------------------------------------


def _http_get(url: str, timeout: int = 60) -> str:
    # data.gov.sg's WAF rejects requests without browser-like Accept headers
    # (HTTP 403 for bare urllib/Python clients; verified 2026-09-02).
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "sg-investing-fx-backfill/1.0",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-SG,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        # utf-8-sig: some government endpoints (eservices.mas.gov.sg failover
        # pages) prepend a UTF-8 BOM; decoding it away is harmless otherwise.
        return response.read().decode("utf-8-sig", errors="replace")


def _http_get_json(url: str, timeout: int = 60) -> dict:
    return json.loads(_http_get(url, timeout=timeout))


def fetch_mas_api(base_currency: str, start: date, end: date) -> dict[date, Decimal]:
    """(a) eservices.mas.gov.sg datastore API, "Exchange Rates - Daily" dataset.

    The legacy CKAN datastore caps a single search at 32,000 rows, which covers
    the 2000-2003 daily window for every currency many times over, so one call
    suffices.
    """

    url = (
        f"{MAS_API_HOST}/action/datastore/search.json"
        f"?resource_id={MAS_API_RESOURCE_ID}&limit=32000"
    )
    payload = _http_get_json(url)
    records = payload.get("result", {}).get("records", [])
    return _parse_mas_records(records, base_currency, start, end)


def fetch_mas_website_tables(base_currency: str, start: date, end: date) -> dict[date, Decimal]:
    """(b) MAS website statistical-table downloads."""

    text = _http_get(MAS_WEBSITE_TABLE_URL)
    if "Maintenance" in text:
        raise MasUnavailable("www.mas.gov.sg statistical-table endpoint serves a maintenance page")
    raise MasUnavailable("no downloadable daily exchange-rate table found on www.mas.gov.sg")


def fetch_datagovsg_mirror(base_currency: str, start: date, end: date) -> dict[date, Decimal]:
    """(c) data.gov.sg mirror of the MAS daily exchange-rates dataset.

    The v2 list-rows endpoint pages with an opaque ``idCursor`` link. For this
    dataset the cursor has been observed to cycle back to the first page once
    the (small) row view is exhausted, so pages that contain only already-seen
    ``vault_id`` values terminate the loop instead of looping forever.
    """

    rows: list[dict] = []
    seen_ids: set[str] = set()
    url: str | None = (
        DATAGOVSG_LIST_ROWS_URL.format(dataset_id=DATAGOVSG_EXCHANGE_RATES_DAILY) + "?limit=1000"
    )
    pages = 0
    while url and pages < DATAGOVSG_MAX_PAGES:
        payload = _http_get_json(url)
        data = payload.get("data", {})
        page_rows = data.get("rows", [])
        page_ids = {str(row.get("vault_id")) for row in page_rows}
        if page_rows and page_ids <= seen_ids:
            break  # server restarted the cursor; the view is exhausted
        rows.extend(page_rows)
        seen_ids |= page_ids
        pages += 1
        url = (data.get("links") or {}).get("next")
        if url:
            # The v2 API returns the cursor as a bare query fragment
            # ("idCursor%5Bvalue%5D=…"), a root-relative path, or an absolute
            # URL depending on deployment; normalise all three.
            if url.startswith("/"):
                url = f"https://api-production.data.gov.sg{url}"
            elif not url.startswith("http"):
                url = (
                    DATAGOVSG_LIST_ROWS_URL.format(dataset_id=DATAGOVSG_EXCHANGE_RATES_DAILY)
                    + "?"
                    + url
                )
            time.sleep(DATAGOVSG_PACE_SECONDS)
    return _parse_mirror_rows(rows, base_currency, start, end)


def _parse_mas_records(
    records: list[dict],
    base_currency: str,
    start: date | None = None,
    end: date | None = None,
) -> dict[date, Decimal]:
    """Parse legacy CKAN datastore rows into {date: rate} for one currency.

    MAS datastore rows carry one row per end-of-day date with per-currency rate
    columns (e.g. ``end_of_day_usd_sgd``). Units per 100 foreign units are NOT
    corrected here — detect_unit_scale() handles that against the ECB series.
    """

    key = f"end_of_day_{base_currency.lower()}_sgd"
    rates: dict[date, Decimal] = {}
    for record in records:
        rate_date = record.get("end_of_day")
        raw = record.get(key)
        if rate_date is None or raw in (None, "", "-"):
            continue
        try:
            day = date.fromisoformat(str(rate_date)[:10])
        except ValueError:
            continue
        if (start is not None and day < start) or (end is not None and day > end):
            continue
        try:
            rates[day] = Decimal(str(raw))
        except (ValueError, ArithmeticError):
            continue
    return rates


def _parse_mirror_rows(
    rows: list[dict],
    base_currency: str,
    start: date | None = None,
    end: date | None = None,
) -> dict[date, Decimal]:
    """Parse data.gov.sg v2 list-rows rows for the MAS exchange-rates dataset.

    The migrated schema is ``{"date": "...", "exchange_rate_usd": "..."}`` —
    one rate column per currency, suffixed with the ISO code only (no
    ``_sgd``), and no ``end_of_day`` column. Rows for currencies the dataset
    does not publish simply lack the column.
    """

    key = f"exchange_rate_{base_currency.lower()}"
    rates: dict[date, Decimal] = {}
    for record in rows:
        rate_date = record.get("date")
        raw = record.get(key)
        if rate_date is None or raw in (None, "", "-"):
            continue
        try:
            day = date.fromisoformat(str(rate_date)[:10])
        except ValueError:
            continue
        if (start is not None and day < start) or (end is not None and day > end):
            continue
        try:
            rates[day] = Decimal(str(raw))
        except (ValueError, ArithmeticError):
            continue
    return rates


def fetch_mas_rates(
    base_currency: str, start: date, end: date, blockers: list[str]
) -> tuple[dict[date, Decimal], str]:
    """Try MAS sourcing paths in order, recording each blocker."""

    paths = (
        ("eservices.mas.gov.sg datastore API", fetch_mas_api),
        ("www.mas.gov.sg statistical tables", fetch_mas_website_tables),
        ("data.gov.sg mirror of MAS dataset", fetch_datagovsg_mirror),
    )
    for name, fetcher in paths:
        try:
            rates = fetcher(base_currency, start, end)
        except (MasUnavailable, urllib.error.URLError, OSError, ValueError, KeyError) as error:
            blockers.append(f"{name}: {error}")
            continue
        if rates:
            return rates, name
        blockers.append(f"{name}: no rates returned for {base_currency}")
    raise MasUnavailable("; ".join(blockers))


def fetch_ecb_rates(base_currency: str, start: date, end: date) -> dict[date, Decimal]:
    """ECB daily reference rates via frankfurter.app (no key), EUR-cross derived."""

    url = f"https://api.frankfurter.dev/v1/{start:%Y-%m-%d}..{end:%Y-%m-%d}?base={base_currency}&symbols=SGD"
    payload = _http_get_json(url)
    rates: dict[date, Decimal] = {}
    for day, values in payload.get("rates", {}).items():
        if base_currency == "EUR" and "SGD" not in values:
            continue
        rates[date.fromisoformat(day)] = Decimal(str(values["SGD"]))
    return rates


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def backfill_pair(
    *,
    store: ParquetStore,
    data_root: Path,
    currency: str,
    earliest_price_date: date,
    write: bool,
) -> tuple[PairSummary, list[FxRate]]:
    existing = existing_fx_series(data_root, currency)
    summary = PairSummary(
        currency=currency,
        required_reason=f"securities priced in {earliest_price_date.isoformat()} (pre-2003-12)",
        existing_first_date=min(existing) if existing else None,
    )

    try:
        mas_raw, mas_source = fetch_mas_rates(
            currency, WINDOW_START, NORMALIZATION_PULL_END, summary.mas_blockers
        )
    except MasUnavailable as error:
        summary.error = str(error)
        return summary, []
    summary.mas_source_used = mas_source
    summary.mas_dates_fetched = len(mas_raw)

    ecb_raw = fetch_ecb_rates(currency, WINDOW_START, NORMALIZATION_PULL_END)
    summary.unit_scale = detect_unit_scale(mas_raw, ecb_raw)
    mas_scaled = {day: rate * summary.unit_scale for day, rate in mas_raw.items()}

    summary.coverage = coverage_gaps(mas_scaled, WINDOW_START, WINDOW_END)
    summary.divergence = cross_check_divergence(mas_scaled, ecb_raw)

    ratio, month = compute_normalization_ratio(mas_scaled, existing)
    summary.normalization_ratio = ratio
    summary.normalization_month = month

    rows = build_fx_rows(
        mas_raw,
        currency=currency,
        unit_scale=summary.unit_scale,
        normalization_ratio=ratio,
        existing_dates=set(existing),
    )
    if write and rows:
        deduped: dict[tuple[str, date], FxRate] = {}
        for row in rows:
            deduped[(row.base_currency, row.rate_date)] = row
        store.upsert_fx(deduped.values())
    summary.rows_written = len(rows)
    return summary, rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--write", action="store_true", help="write to the store (default: dry run)"
    )
    parser.add_argument("--pairs", nargs="*", default=None, help="restrict to these currencies")
    args = parser.parse_args(argv)

    data_root = args.root / "data"
    required = derive_required_pairs(data_root)
    currencies = sorted(required) if args.pairs is None else sorted(set(args.pairs))

    store = ParquetStore(data_root)
    summaries: list[dict] = []
    total_written = 0
    for currency in currencies:
        summary, _rows = backfill_pair(
            store=store,
            data_root=data_root,
            currency=currency,
            earliest_price_date=required.get(currency, WINDOW_START),
            write=args.write,
        )
        total_written += summary.rows_written
        summaries.append(summary.as_dict())

    payload = {
        "window": {"start": WINDOW_START.isoformat(), "end": WINDOW_END.isoformat()},
        "normalization_pull_end": NORMALIZATION_PULL_END.isoformat(),
        "mode": "write" if args.write else "dry-run",
        "total_rows_written": total_written,
        "pairs": summaries,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    blocked = [s for s in summaries if s["error"]]
    return 1 if len(blocked) == len(summaries) and summaries else 0


if __name__ == "__main__":
    sys.exit(main())
