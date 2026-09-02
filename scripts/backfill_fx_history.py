"""Backfill FX history (2000-01-01 to 2003-11-30) for the pairs that pre-2003-12
securities need.

Sprint 7.5 Track A, decision A0 (updated 2026-09-02): MAS is DROPPED as a
source (api.mas.gov.sg does not resolve, eservices.mas.gov.sg serves a
maintenance failover page, the data.gov.sg mirror is weekly, USD-only and ends
2003-11-12 — evidence in docs/adr/0002-fx-sources.md). **ECB is the primary
source.** The pull is minimal — only dates that are missing before each pair's
existing first stored date are written, and no existing 2003+ Yahoo FX row is
touched. The ECB window is scaled by a normalization ratio computed over the
last month that overlaps the existing FX series, so no level seam enters SGD
returns.

Sourcing order (ECB daily reference rates, published since 1999, no key):

(a) ECB SDMX Data Portal API (data-api.ecb.europa.eu, series
    ``EXR.D.<CCY>.EUR.SP00.A``, requested as CSV);
(b) the eurofxref historical CSV (www.ecb.europa.eu/stats/eurofxref/
    eurofxref-hist.zip — one CSV, all currencies, daily since 1999);
(c) frankfurter.app (api.frankfurter.dev, an ECB mirror, no key).

Cross-check: at least one additional ECB flavor is always fetched for every
pair and the divergence (mean/max bps) is reported; the weekly MAS data.gov.sg
mirror (resource d_046ff8d521a218d9178178cfbfc45c2c) may serve as an optional
tertiary sanity check where it has a column (USD only) — it is never blocking
and its rows are never written. Every attempted path and its blocker is
recorded in the summary — a failed path is never silently substituted, and
per-pair window coverage (first/last observation, longest date gap) is
reported so an under-covering source cannot pass unnoticed.

Derivation: the ECB publishes reference rates as **per 1 EUR**. The SGD cross
is derived exactly, with no float intermediate and no precision loss beyond
the interpreter default Decimal context (28 significant digits):

    SGD per 1 unit of <CCY> = (SGD per 1 EUR) / (<CCY> per 1 EUR)

e.g. USD/SGD on 2000-01-03 = 1.7358 / 1.0090. All values are parsed straight
into ``Decimal`` from the API/CSV text (frankfurter JSON is parsed with
``parse_float=Decimal``); normalized to one unit foreign = X SGD.

Row contract (src/sg_investing/models.py::FxRate, unchanged):
``rate_date`` (ISO string), ``base_currency`` (3 letters), ``rate_to_sgd``
(decimal string; one unit foreign = X SGD), ``source``. Backfilled rows carry
``source: "ecb"``. The model has no retrieved_at/normalized columns; adding
one would change the canonical schema (out of Track A scope), so normalization
is documented in docs/adr/0002-fx-sources.md and this script's summary.

Usage:
    .venv/bin/python scripts/backfill_fx_history.py            # dry run
    .venv/bin/python scripts/backfill_fx_history.py --write

Network is only touched by the fetch_* helpers (ECB/frankfurter/data.gov.sg
endpoints); tests drive the pure functions with synthetic fixtures.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import urllib.error
import urllib.request
import zipfile
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
# The normalization month is the last month covered by BOTH the ECB pull and
# the existing store. Yahoo USD/SGD starts 2003-12-01 and the backfill window
# ends 2003-11-30, so there is no overlap inside the write window itself: the
# ECB pull extends through this date purely to measure the seam, and those
# rows are never written.
NORMALIZATION_PULL_END = date(2003, 12, 31)
MIN_OVERLAP_DATES = 5
# Divergences above this many basis points (1%) are flagged, never silently
# accepted.
DIVERGENCE_FLAG_BPS = Decimal(100)
# A median mirror/ECB ratio in [50, 150] means the mirror quotes S$ per 100
# foreign units.
PER_100_RATIO_LOW = Decimal(50)
PER_100_RATIO_HIGH = Decimal(150)

SOURCE_NAME = "ecb"

# (a) ECB SDMX Data Portal: daily reference rates since 1999-01-04, no key.
# Series key: EXR.D.<CCY>.EUR.SP00.A — daily, <CCY> per EUR, spot, average.
ECB_SDMX_SERIES_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D.{currency}.EUR.SP00.A"
)
# (b) eurofxref historical: one zipped CSV, all currencies, daily since 1999.
ECB_EUROFXREF_HIST_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
# (c) frankfurter.app: ECB mirror, no key, JSON.
FRANKFURTER_API_URL = "https://api.frankfurter.dev/v1/{start:%Y-%m-%d}..{end:%Y-%m-%d}"

# Tertiary sanity check only (never blocking, never written): the weekly MAS
# data.gov.sg mirror. USD-only, ~1,000-row view ending 2003-11-12 — see ADR
# 0002 for why it cannot be a primary source.
DATAGOVSG_LIST_ROWS_URL = (
    "https://api-production.data.gov.sg/v2/public/api/datasets/{dataset_id}/list-rows"
)
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
    source_used: str | None = None
    blockers: list[str] = field(default_factory=list)
    cross_checks: dict[str, dict] = field(default_factory=dict)
    cross_check_blockers: list[str] = field(default_factory=list)
    unit_scale: Decimal = Decimal(1)
    normalization_ratio: Decimal = Decimal(1)
    normalization_month: str | None = None
    dates_fetched: int = 0
    rows_written: int = 0
    coverage: dict | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "currency": self.currency,
            "required_reason": self.required_reason,
            "existing_first_date": (
                self.existing_first_date.isoformat() if self.existing_first_date else None
            ),
            "source_used": self.source_used,
            "blockers": self.blockers,
            "cross_checks": self.cross_checks,
            "cross_check_blockers": self.cross_check_blockers,
            "unit_scale": str(self.unit_scale),
            "normalization_ratio": str(self.normalization_ratio.quantize(Decimal("0.000001"))),
            "normalization_month": self.normalization_month,
            "dates_fetched": self.dates_fetched,
            "rows_written": self.rows_written,
            "coverage": self.coverage,
            "error": self.error,
        }


class EcbUnavailable(RuntimeError):
    """No ECB sourcing path is reachable; the reason is reported, never hidden."""


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


def derive_cross_from_eur(
    base_currency: str,
    sgd_per_eur: dict[date, Decimal],
    ccy_per_eur: dict[date, Decimal],
) -> dict[date, Decimal]:
    """Exact SGD cross: SGD per 1 base = (SGD per EUR) / (base per EUR).

    Both inputs are Decimal throughout (parsed from source text); the division
    runs at the interpreter default Decimal context (28 significant digits) —
    there is no float intermediate anywhere. For base EUR the SGD series is
    the answer directly.
    """

    if base_currency == "EUR":
        return dict(sgd_per_eur)
    cross: dict[date, Decimal] = {}
    for day in sorted(set(sgd_per_eur) & set(ccy_per_eur)):
        if ccy_per_eur[day] == 0:
            continue
        cross[day] = sgd_per_eur[day] / ccy_per_eur[day]
    return cross


def detect_unit_scale(
    mirror_by_date: dict[date, Decimal], ecb_by_date: dict[date, Decimal]
) -> Decimal:
    """1 or 100: whether the tertiary mirror quotes S$ per 1 or per 100 units.

    Some MAS statistical tables quote selected currencies per 100 units. The
    scale is detected against the ECB series so a mis-read of the mirror's
    units cannot corrupt the reported sanity check. Never applied to written
    rows (those are ECB-native, one unit foreign = X SGD).
    """

    ratios = [
        mirror_by_date[d] / ecb_by_date[d]
        for d in sorted(set(mirror_by_date) & set(ecb_by_date))
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
    new_by_date: dict[date, Decimal],
    existing_by_date: dict[date, Decimal],
    min_overlap_dates: int = MIN_OVERLAP_DATES,
) -> tuple[Decimal, str | None]:
    """Mean ``existing / new`` over the last month present in both series.

    Returns ``(Decimal("1"), None)`` when the two series never share a month
    (e.g. a pair with no stored history at all): with no reference level there
    is no seam to remove, so the new rates are written as-is.
    """

    by_month_new: dict[str, list[date]] = defaultdict(list)
    for day in new_by_date:
        by_month_new[day.strftime("%Y-%m")].append(day)
    best_month: str | None = None
    best_dates: list[date] = []
    for month, days in sorted(by_month_new.items(), reverse=True):
        common = [d for d in days if d in existing_by_date]
        if len(common) >= min_overlap_dates:
            best_month = month
            best_dates = common
            break
    if best_month is None:
        return Decimal(1), None
    ratios = [existing_by_date[d] / new_by_date[d] for d in best_dates]
    mean = sum(ratios, Decimal(0)) / Decimal(len(ratios))
    return mean.quantize(Decimal("0.000000000001")), best_month


def build_fx_rows(
    rates_by_date: dict[date, Decimal],
    *,
    currency: str,
    unit_scale: Decimal,
    normalization_ratio: Decimal,
    existing_dates: set[date],
    window_end: date = WINDOW_END,
) -> list[FxRate]:
    """Convert raw ECB observations to store rows, keeping only missing dates.

    Rows are scaled by ``unit_scale * normalization_ratio`` and restricted to
    dates at or before ``window_end`` that the store does not already have, so
    the existing 2003+ Yahoo series is never rewritten.
    """

    rows: list[FxRate] = []
    seen: set[date] = set()
    for day in sorted(rates_by_date):
        if day > window_end or day in existing_dates:
            continue
        if day in seen:
            continue
        seen.add(day)
        rate = rates_by_date[day] * unit_scale * normalization_ratio
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

    The exact gap is reported (first/last observation and the longest calendar
    stretch with no observation, including the head/tail against the window
    bounds) so an under-covering source cannot pass unnoticed.
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
    candidate_by_date: dict[date, Decimal], reference_by_date: dict[date, Decimal]
) -> Divergence | None:
    """Mean/max divergence in basis points between two sourced series."""

    common = sorted(set(candidate_by_date) & set(reference_by_date))
    if not common:
        return None
    bps = [
        abs(candidate_by_date[d] - reference_by_date[d]) / reference_by_date[d] * Decimal(10000)
        for d in common
    ]
    worst_index = max(range(len(bps)), key=lambda i: bps[i])
    mean = sum(bps, Decimal(0)) / Decimal(len(bps))
    return Divergence(
        mean_bps=mean,
        max_bps=bps[worst_index],
        max_bps_date=common[worst_index],
        common_dates=len(common),
    )


# ---------------------------------------------------------------------------
# Source parsers (pure; unit-tested with synthetic payloads)
# ---------------------------------------------------------------------------


def _parse_sdmx_csv(
    text: str,
    currency: str,
    start: date | None = None,
    end: date | None = None,
) -> dict[date, Decimal]:
    """Parse an ECB SDMX ``csvdata`` response into {date: rate per EUR}."""

    rates: dict[date, Decimal] = {}
    for row in csv.DictReader(io.StringIO(text)):
        if (row.get("CURRENCY") or "").strip() != currency:
            continue
        raw = (row.get("OBS_VALUE") or "").strip()
        day = (row.get("TIME_PERIOD") or "").strip()
        if not raw or not day:
            continue
        try:
            parsed_day = date.fromisoformat(day[:10])
        except ValueError:
            continue
        if (start is not None and parsed_day < start) or (end is not None and parsed_day > end):
            continue
        try:
            rates[parsed_day] = Decimal(raw)
        except (ValueError, ArithmeticError):
            continue
    return rates


def _parse_eurofxref_csv(
    text: str,
    base_currency: str,
    start: date | None = None,
    end: date | None = None,
) -> dict[date, Decimal]:
    """Parse eurofxref-hist.csv into the SGD cross for ``base_currency``.

    One row per date (descending), one column per currency, values per 1 EUR,
    ``N/A`` for missing quotes. The cross is derived exactly per
    :func:`derive_cross_from_eur`.
    """

    reader = csv.DictReader(io.StringIO(text))
    sgd_per_eur: dict[date, Decimal] = {}
    ccy_per_eur: dict[date, Decimal] = {}
    for row in reader:
        day_raw = (row.get("Date") or "").strip()
        if not day_raw:
            continue
        try:
            day = date.fromisoformat(day_raw[:10])
        except ValueError:
            continue
        if (start is not None and day < start) or (end is not None and day > end):
            continue
        sgd_raw = (row.get("SGD") or "").strip()
        try:
            sgd_per_eur[day] = Decimal(sgd_raw)
        except (ValueError, ArithmeticError):
            sgd_per_eur.pop(day, None)
            continue
        if base_currency == "EUR":
            continue
        ccy_raw = (row.get(base_currency) or "").strip()
        try:
            ccy_per_eur[day] = Decimal(ccy_raw)
        except (ValueError, ArithmeticError):
            sgd_per_eur.pop(day, None)
            ccy_per_eur.pop(day, None)
    return derive_cross_from_eur(base_currency, sgd_per_eur, ccy_per_eur)


def _parse_mirror_rows(
    rows: list[dict],
    base_currency: str,
    start: date | None = None,
    end: date | None = None,
) -> dict[date, Decimal]:
    """Parse data.gov.sg v2 list-rows rows for the (weekly) MAS mirror.

    The migrated schema is ``{"date": "...", "exchange_rate_usd": "..."}`` —
    one rate column per currency, suffixed with the ISO code only. Rows for
    currencies the dataset does not publish (HKD, JPY) simply lack the
    column. Units per 100 are NOT corrected here — detect_unit_scale()
    handles that against the ECB series.
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


# ---------------------------------------------------------------------------
# Fetchers (network). Only ECB/frankfurter/data.gov.sg endpoints are used.
# ---------------------------------------------------------------------------


def _http_get_bytes(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "sg-investing-fx-backfill/1.0",
            "Accept": "application/csv,text/csv,application/json,text/plain,*/*",
            "Accept-Language": "en-SG,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _http_get(url: str, timeout: int = 60) -> str:
    return _http_get_bytes(url, timeout=timeout).decode("utf-8-sig", errors="replace")


def _http_get_json(url: str, timeout: int = 60, parse_float=None) -> dict:
    # parse_float=Decimal keeps frankfurter's JSON numbers out of float
    # entirely (the JSON text is handed to Decimal verbatim).
    return json.loads(_http_get(url, timeout=timeout), parse_float=parse_float)


def _fetch_sdmx_series(currency: str, start: date, end: date) -> dict[date, Decimal]:
    """One ECB SDMX series (daily reference rate: ``currency`` per 1 EUR)."""

    url = (
        f"{ECB_SDMX_SERIES_URL.format(currency=currency)}"
        f"?startPeriod={start:%Y-%m-%d}&endPeriod={end:%Y-%m-%d}&format=csvdata"
    )
    return _parse_sdmx_csv(_http_get(url, timeout=90), currency, start, end)


def fetch_ecb_sdmx(base_currency: str, start: date, end: date) -> dict[date, Decimal]:
    """(a) ECB SDMX Data Portal API — SGD series + base series, exact cross."""

    sgd_per_eur = _fetch_sdmx_series("SGD", start, end)
    if not sgd_per_eur:
        raise EcbUnavailable("SDMX returned no SGD/EUR observations")
    if base_currency == "EUR":
        return sgd_per_eur
    ccy_per_eur = _fetch_sdmx_series(base_currency, start, end)
    if not ccy_per_eur:
        raise EcbUnavailable(f"SDMX returned no {base_currency}/EUR observations")
    return derive_cross_from_eur(base_currency, sgd_per_eur, ccy_per_eur)


def fetch_ecb_eurofxref(base_currency: str, start: date, end: date) -> dict[date, Decimal]:
    """(b) eurofxref-hist.zip — one CSV, all currencies, exact cross."""

    payload = _http_get_bytes(ECB_EUROFXREF_HIST_URL, timeout=120)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        member = next(name for name in archive.namelist() if name.endswith(".csv"))
        text = archive.read(member).decode("utf-8-sig", errors="replace")
    return _parse_eurofxref_csv(text, base_currency, start, end)


def fetch_frankfurter(base_currency: str, start: date, end: date) -> dict[date, Decimal]:
    """(c) frankfurter.app ECB mirror — JSON, parsed with parse_float=Decimal."""

    url = f"{FRANKFURTER_API_URL.format(start=start, end=end)}?base={base_currency}&symbols=SGD"
    payload = _http_get_json(url, parse_float=Decimal)
    rates: dict[date, Decimal] = {}
    for day, values in payload.get("rates", {}).items():
        if "SGD" not in values:
            continue
        rates[date.fromisoformat(day)] = Decimal(str(values["SGD"]))
    return rates


PRIMARY_PATHS: tuple[tuple[str, object], ...] = (
    ("ecb_sdmx_data_portal", fetch_ecb_sdmx),
    ("ecb_eurofxref_hist_csv", fetch_ecb_eurofxref),
    ("frankfurter.app", fetch_frankfurter),
)
CROSS_CHECK_SOURCES: tuple[tuple[str, object], ...] = (
    ("ecb_eurofxref_hist_csv", fetch_ecb_eurofxref),
    ("frankfurter.app", fetch_frankfurter),
)


def fetch_ecb_rates(
    base_currency: str, start: date, end: date, blockers: list[str]
) -> tuple[dict[date, Decimal], str]:
    """Try the ECB sourcing paths in order, recording each blocker."""

    for name, fetcher in PRIMARY_PATHS:
        try:
            rates = fetcher(base_currency, start, end)
        except (EcbUnavailable, urllib.error.URLError, OSError, ValueError, KeyError) as error:
            blockers.append(f"{name}: {error}")
            continue
        if rates:
            return rates, name
        blockers.append(f"{name}: no rates returned for {base_currency}")
    raise EcbUnavailable("; ".join(blockers))


def fetch_datagovsg_mirror(base_currency: str, start: date, end: date) -> dict[date, Decimal]:
    """Tertiary sanity check: data.gov.sg mirror of the MAS daily dataset.

    Weekly cadence, USD-only, 1,000-row view ending 2003-11-12 — reported as
    a divergence sanity check where dates overlap; never blocking, never
    written. The v2 list-rows endpoint pages with an opaque ``idCursor`` link
    that has been observed to cycle back to the first page once the (small)
    row view is exhausted, so pages that contain only already-seen
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
        rates_raw, source_used = fetch_ecb_rates(
            currency, WINDOW_START, NORMALIZATION_PULL_END, summary.blockers
        )
    except EcbUnavailable as error:
        summary.error = str(error)
        return summary, []
    summary.source_used = source_used
    summary.dates_fetched = len(rates_raw)

    # Cross-check: every additional ECB flavor that can be fetched is compared
    # against the primary over the whole window; divergence is reported in bps
    # (flagged above DIVERGENCE_FLAG_BPS), never silently accepted.
    for name, fetcher in CROSS_CHECK_SOURCES:
        if name == source_used:
            continue
        try:
            other = fetcher(currency, WINDOW_START, NORMALIZATION_PULL_END)
            divergence = cross_check_divergence(rates_raw, other) if other else None
        except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
            summary.cross_check_blockers.append(f"{name}: {error}")
            continue
        if divergence is not None:
            summary.cross_checks[name] = divergence.as_dict()

    # Tertiary MAS-mirror sanity check (USD only): never blocking, never written.
    try:
        mirror_raw = fetch_datagovsg_mirror(currency, WINDOW_START, NORMALIZATION_PULL_END)
        if mirror_raw:
            scale = detect_unit_scale(mirror_raw, rates_raw)
            summary.unit_scale = scale
            scaled = {day: rate * scale for day, rate in mirror_raw.items()}
            divergence = cross_check_divergence(scaled, rates_raw)
            if divergence is not None:
                summary.cross_checks["data.gov.sg MAS mirror (tertiary)"] = divergence.as_dict()
    except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
        summary.cross_check_blockers.append(f"data.gov.sg MAS mirror: {error}")

    summary.coverage = coverage_gaps(rates_raw, WINDOW_START, WINDOW_END)

    ratio, month = compute_normalization_ratio(rates_raw, existing)
    summary.normalization_ratio = ratio
    summary.normalization_month = month

    rows = build_fx_rows(
        rates_raw,
        currency=currency,
        unit_scale=Decimal(1),  # ECB quotes one unit foreign natively
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
