# Browser data-pack schema — `schema_version: 1`

Status: Frozen for Sprint 1 (Todo/sprint-1-data-packs.md, orchestration plan
freeze point 1: pack schema + support manifest). Any change that breaks
consumers must bump `schema_version`.

Producer: `scripts/build_data_packs.py` (module
`src/sg_investing/data/packs.py`). Consumer: the browser engine (Sprints 2+)
and the support-status check required before any calculation.

## Layout

```text
frontend/data/packs/
  manifest.json                                   # one per snapshot
  security=<security_id>/year=<YYYY>.json         # one pack per security-year
```

Packs are partitioned per security and calendar year so a browser lazy-loads
only the securities and date ranges a user requests. `security_id` is the
catalog UUID (tickers are provider identifiers and are never the key). JSON
is minified (`", "`/`": "` separators removed, keys sorted); the examples
below are pretty-printed for readability only.

## Value encoding

| Kind | Encoding | Example |
| --- | --- | --- |
| Money / prices / FX rates / ratios | JSON string holding an exact decimal numeral (storage decimals with trailing zeros stripped). The browser parses it with decimal.js; `Number` is never used for money. | `"471.2500152587891"` |
| Dates | ISO-8601 `YYYY-MM-DD` string | `"2024-01-02"` |
| Timestamps | ISO-8601 UTC with offset | `"2026-08-30T13:33:14.234998+00:00"` |
| Volumes / counts / bytes / years | JSON integer | `252` |
| Absent values | `null` (or empty array for list sections) | `null` |

## Snapshot identity fields (present in every pack and the manifest)

| Field | Meaning |
| --- | --- |
| `schema_version` | Pack schema version, `1`. |
| `data_snapshot_id` | `sha256-<hex>` content hash of every file under `data/` at build time. Identical stores produce identical ids; any store change produces a new id. |
| `catalog_version` | `sha256-<16 hex>` of `data/universe/current_catalog.json`. |
| `catalog_as_of` | `as_of` from `data/universe/summary.json` (catalog import date). |
| `methodology_version` | Financial methodology version, `1.0` (matches `AnalysisScenario.methodology_version`). |
| `generated_at` | Build timestamp, UTC. |
| `source` (manifest) / `provenance` (packs) | Data source, e.g. `yahoo_finance`; packs list every source that contributed rows. |

---

## Pack type: `security_year`

One file per security and calendar year of price data. Contains daily native
(unadjusted) OHLCV prices, the FX window needed to translate them to SGD,
dividend events whose ex-date falls in the year, corporate actions whose
effective date falls in the year, coverage, provenance and data-quality
warnings. Files exist only for years with at least one price row.

| Field | Meaning |
| --- | --- |
| `pack_type` | `"security_year"`. |
| `partition` | `{security_id, market, year}` of this pack. |
| `security` | Security master row from the catalog (`ticker`, `name`, `exchange`, `market`, `currency`, `asset_type`, `domicile`, `isin`, `timezone`, `distribution_policy`, `expense_ratio`, `universes[]`). Fields are `null` for a priced security that is absent from the catalog snapshot (`in_current_catalog: false`). |
| `coverage` | `first_date`, `last_date`, `row_count` for this pack; `native_currency`; `requires_fx` (true unless the native currency is SGD); `fx_base_currency`. |
| `provenance` | `source` (single source or `"multiple"`), `sources[]`, `retrieved_at{first,last}`, `pipeline_version` (from the store partition manifest), `partition_manifest` (store manifest path), `builder`. |
| `data_quality` | `status` (see classification below), `missing_fx_dates`, `stale_fx_dates`, `max_fx_staleness_days`, `missing_calendar_dates`. |
| `warnings` | Human-readable data-quality warnings; empty when clean. |
| `prices` | Column arrays: `dates`, `open`, `high`, `low`, `close` (exact decimal strings), `volume` (integers), sorted by date. |
| `fx` | `null` when `requires_fx` is false; otherwise `{base_currency, quote_currency: "SGD", dates, rates, series_first_date, series_last_date}` covering `[first price date − 10 calendar days, last price date]` so the browser can apply the engine's previous-trading-day rule at window edges. Empty arrays mean the FX series does not exist in the snapshot. |
| `dividends` | Events with `ex_date` in this year: `{ex_date, amount, currency, pay_date, record_date, dividend_type, source_id, source_country, source, retrieved_at}`. |
| `corporate_actions` | `{effective_date, action_type, ratio, source, retrieved_at}`. |

### Filled example — `security_year`

Excerpt of a real pack (QQQ, year 2024; arrays truncated with `…`):

```json
{
  "schema_version": 1,
  "pack_type": "security_year",
  "generated_at": "2026-08-31T04:52:35+00:00",
  "data_snapshot_id": "sha256-2612cdfaf81fa2847369a9752b4dfa288bc5eec4ead26f2f377d985f9d342c5b",
  "catalog_version": "sha256-d336a7d1369c60d4",
  "catalog_as_of": "2026-08-30",
  "methodology_version": "1.0",
  "partition": {
    "security_id": "6cfd001d-07dc-44d9-aff8-d6c99b0ee80b",
    "market": "US",
    "year": 2024
  },
  "security": {
    "security_id": "6cfd001d-07dc-44d9-aff8-d6c99b0ee80b",
    "ticker": "QQQ",
    "name": "Invesco QQQ Trust",
    "exchange": "NASDAQ",
    "market": "US",
    "currency": "USD",
    "asset_type": "ETF",
    "domicile": "US",
    "income_source_country": "US",
    "isin": null,
    "cusip": null,
    "timezone": "America/New_York",
    "active": true,
    "distribution_policy": "distributing",
    "expense_ratio": null,
    "universes": [
      {
        "universe": "major_global_etfs",
        "effective_from": "1999-03-10",
        "source": "configured_seed"
      }
    ],
    "in_current_catalog": true
  },
  "coverage": {
    "first_date": "2024-01-02",
    "last_date": "2024-12-31",
    "row_count": 252,
    "native_currency": "USD",
    "requires_fx": true,
    "fx_base_currency": "USD"
  },
  "provenance": {
    "source": "yahoo_finance",
    "sources": ["yahoo_finance"],
    "retrieved_at": {
      "first": "2026-08-30T13:33:14.234998+00:00",
      "last": "2026-08-30T13:33:14.234998+00:00"
    },
    "pipeline_version": "0.1.0",
    "partition_manifest": "manifests/prices/market=US/year=2024.json",
    "builder": "sg_investing.data.packs"
  },
  "data_quality": {
    "status": "fully_supported",
    "missing_fx_dates": 0,
    "stale_fx_dates": 0,
    "max_fx_staleness_days": 0,
    "missing_calendar_dates": 0
  },
  "warnings": [],
  "prices": {
    "dates": ["2024-01-02", "2024-01-03", "…"],
    "open": ["36.09000015258789", "36.430000305175781", "…"],
    "high": ["37.290000915527344", "36.659999847412109", "…"],
    "low": ["36.069999694824219", "34.990001678466797", "…"],
    "close": ["36.450000762939453", "35.040000915527344", "…"],
    "volume": [256400, 333300]
  },
  "fx": {
    "base_currency": "USD",
    "quote_currency": "SGD",
    "dates": ["2023-12-22", "2023-12-26", "…", "2024-12-31"],
    "rates": ["1.3296400308609009", "1.3276399374008179", "…"],
    "series_first_date": "2003-12-01",
    "series_last_date": "2026-08-30"
  },
  "dividends": [
    {
      "ex_date": "2024-03-20",
      "amount": "0.3799999952316284",
      "currency": "USD",
      "pay_date": "2024-04-30",
      "record_date": null,
      "dividend_type": "regular",
      "source_id": null,
      "source_country": null,
      "source": "yahoo_finance",
      "retrieved_at": "2026-08-30T16:02:08+00:00"
    }
  ],
  "corporate_actions": []
}
```

---

## Pack type: `manifest`

`manifest.json` — one per snapshot. Answers, before any calculation, whether
a security/date range is fully supported, incomplete or unavailable, and
where to lazy-load packs.

| Field | Meaning |
| --- | --- |
| `manifest_version` | Manifest-only revision, `1`. |
| `history_start` | Universe data horizon (catalog), e.g. `2000-01-01`. |
| `source` | Dominant provider across the built packs. |
| `scope` | `{security_ids, markets}` filters used for the build; `null` = full universe. A filtered build's manifest only answers for its scope. |
| `pack_layout` | `path_template` `security={security_id}/year={year}.json`, `partition_by`, and pack-type descriptions. |
| `support.counts` | Securities per status: `fully_supported` / `incomplete` / `unavailable`. |
| `support.range_query` | Pointer to the frozen range-classification rules below. |
| `fx` | `available_pairs[]` (e.g. `["USD_SGD"]`), `quote_currency`, `coverage` per required native currency with `first_date`/`last_date` and `available`. |
| `summary` | `securities`, `pack_count`, `total_bytes`, `price_rows`, `pack_bytes{min,median,max}`, `manifest_bytes`. |
| `warnings` | Snapshot-level warnings (unavailable counts, securities outside the catalog, missing FX pairs, distributing securities without dividend events). |
| `securities[]` | One entry per catalog security (status `unavailable` when never priced) plus any priced security missing from the catalog. Sorted by `security_id`. |

Each `securities[]` entry:

| Field | Meaning |
| --- | --- |
| `security_id`, `ticker`, `name`, `market`, `exchange`, `native_currency`, `asset_type`, `domicile`, `isin`, `distribution_policy` | Security metadata (catalog values; `null` outside the catalog). |
| `universes[]` | `{universe, effective_from, source}` memberships. |
| `in_current_catalog` | `false` for priced securities missing from the catalog snapshot. |
| `status` | `fully_supported`, `incomplete` or `unavailable` (roll-up rules below). |
| `first_date`, `last_date` | First/last price date across all years. |
| `first_year`, `last_year` | First/last year with price data. |
| `row_count` | Total price rows across all years. |
| `years` | Map `YYYY` → `{status, rows, first_date, last_date, missing_fx_dates, stale_fx_dates, max_fx_staleness_days, missing_calendar_dates, warnings[], pack, bytes}`. Only years with price data appear; a calendar year inside `first_year..last_year` that is absent has no price data. |
| `warnings` | Security-level warnings (e.g. distributing with no dividend events, absent from catalog, no price data). |

### Filled example — manifest excerpt

```json
{
  "schema_version": 1,
  "manifest_version": 1,
  "pack_type": "manifest",
  "generated_at": "2026-08-31T04:52:35+00:00",
  "data_snapshot_id": "sha256-2612cdfaf81fa2847369a9752b4dfa288bc5eec4ead26f2f377d985f9d342c5b",
  "catalog_version": "sha256-d336a7d1369c60d4",
  "catalog_as_of": "2026-08-30",
  "history_start": "2000-01-01",
  "methodology_version": "1.0",
  "source": "yahoo_finance",
  "scope": {"security_ids": null, "markets": null},
  "pack_layout": {
    "path_template": "security={security_id}/year={year}.json",
    "partition_by": ["security_id", "year"]
  },
  "support": {
    "counts": {"fully_supported": 1437, "incomplete": 1747, "unavailable": 4}
  },
  "fx": {
    "available_pairs": ["USD_SGD"],
    "quote_currency": "SGD",
    "coverage": {
      "USD": {"first_date": "2003-12-01", "last_date": "2026-08-30", "available": true}
    }
  },
  "summary": {
    "securities": 3188,
    "pack_count": 55574,
    "total_bytes": 1793006115,
    "price_rows": 13422888,
    "pack_bytes": {"min": 1609, "median": 35155, "max": 40492}
  },
  "warnings": [
    "4 catalog securities have no price data in this snapshot.",
    "16 priced securities are not present in the current catalog snapshot.",
    "No FX history is available for required pairs: CNY, EUR, GBP, HKD, JPY."
  ],
  "securities": [
    {
      "security_id": "6cfd001d-07dc-44d9-aff8-d6c99b0ee80b",
      "ticker": "QQQ",
      "name": "Invesco QQQ Trust",
      "market": "US",
      "exchange": "NASDAQ",
      "native_currency": "USD",
      "asset_type": "ETF",
      "domicile": "US",
      "isin": null,
      "distribution_policy": "distributing",
      "universes": [
        {"universe": "major_global_etfs", "effective_from": "1999-03-10", "source": "configured_seed"}
      ],
      "in_current_catalog": true,
      "status": "incomplete",
      "first_date": "2000-01-03",
      "last_date": "2026-08-27",
      "first_year": 2000,
      "last_year": 2026,
      "row_count": 6703,
      "years": {
        "2001": {
          "status": "incomplete",
          "rows": 248,
          "first_date": "2001-01-02",
          "last_date": "2001-12-31",
          "missing_fx_dates": 248,
          "stale_fx_dates": 0,
          "max_fx_staleness_days": 0,
          "missing_calendar_dates": 0,
          "warnings": [
            "248 price dates have no USD/SGD rate on or before them; SGD analysis would fail for these dates."
          ],
          "pack": "security=6cfd001d-07dc-44d9-aff8-d6c99b0ee80b/year=2001.json",
          "bytes": 25511
        },
        "2024": {
          "status": "fully_supported",
          "rows": 252,
          "first_date": "2024-01-02",
          "last_date": "2024-12-31",
          "missing_fx_dates": 0,
          "stale_fx_dates": 0,
          "max_fx_staleness_days": 0,
          "missing_calendar_dates": 0,
          "warnings": [],
          "pack": "security=6cfd001d-07dc-44d9-aff8-d6c99b0ee80b/year=2024.json",
          "bytes": 37315
        }
      },
      "warnings": []
    }
  ]
}
```

---

## Support-status classification (frozen rules)

Per **security-year** (only years with at least one price bar appear in
`years`):

- `fully_supported` — every price date resolves: FX is either not required
  (SGD-native) or every price date has a rate on or before it, and no market
  calendar date inside the security's own `first_date..last_date` window
  lacks a price bar.
- `incomplete` — price data exists, but the engine could not compute every
  date: some price dates have no `currency`/SGD rate on or before them
  (`missing_fx_dates` > 0, the engine's `AnalysisDataError` case), or some
  market-calendar dates lack price bars (`missing_calendar_dates` > 0, e.g.
  suspended SGX securities). FX staleness beyond the engine's 7-day limit is
  surfaced as `stale_fx_dates` plus a warning: the engine still computes
  such ranges, so they remain `fully_supported`.
- Years with zero price rows are simply absent from `years`; one inside
  `first_year..last_year` means unavailable data for that year.

Per **security** (roll-up): `unavailable` with no data years; `incomplete`
if any year is incomplete or a year is missing inside the security's own
year window; otherwise `fully_supported`.

Per **date range** `classify_range(entry, start, end)`:

1. No data years at all, or the range does not overlap
   `first_date..last_date` → `unavailable`.
2. Intersect every calendar year of the range with the security's year
   window: years present in `years` contribute their year status; years
   absent inside the window contribute `unavailable`; years before/after the
   window are ignored.
3. Range status: all intersecting years `fully_supported` →
   `fully_supported`; all `unavailable` → `unavailable`; otherwise
   `incomplete`.
4. Range edges before the first / after the last price date are tolerated
   (the engine resolves purchases to the next, valuations to the previous
   trading day) and returned as informational `reasons`.

The market calendar used for gap detection is the union of trading dates
observed for all securities in the same market/year partition — the best
available proxy for the exchange calendar in this snapshot.

## Versioning and merge behavior

- Rebuilding from an unchanged store reproduces the same
  `data_snapshot_id` and `catalog_version`; only `generated_at` differs.
- Any canonical store change (new bars, restated dividends, FX updates)
  produces a new `data_snapshot_id`, and every rebuilt pack and manifest
  carries it, so a browser cache can invalidate stale packs by comparing the
  id in `manifest.json` against the id stored with each cached pack.
- Packs are regenerated wholesale; there is no partial pack update. The
  build resets `frontend/data/packs/` before writing.

## Known limitations

- Dividend events whose ex-date year has no price rows for that security are
  not published in any pack (packs exist only for price years).
- The FX window in a pack spans `[first price date − 10 days, last price
  date]`; analysis ranges reaching further back must consult an earlier
  year's pack for the rate.
- Pack files are minified JSON (compact separators); examples here are
  pretty-printed.
