# ADR 0002 — FX history sources: backfill to 2000-01-01, cross-check and splice

- Status: Accepted (decision A0); execution deferred — MAS sourcing blocked
  (verified 2026-09-02, see "A1 verification")
- Date: 2026-09-01 (A0), 2026-09-02 (A1 verification and deferral)
- Decides: Todo/sprint-7.5-fx-incremental-reactive.md Track A tasks A0–A3
- Related: docs/fx-sources.md, scripts/backfill_fx_history.py,
  src/sg_investing/data/packs.py (support classification), Todo/sprint-7.5

## Context

The FX store holds one pair, `USD_SGD`, sourced from Yahoo Finance, starting
2003-12-01. Every security priced before 2003-12-01 in a foreign currency is
therefore FX-locked: 1,092 of 3,188 securities have pre-2003-12 price rows, and
the manifest classifies their pre-2003-12 years as `incomplete` (1,747 total;
1,437 `fully_supported`, 4 `unavailable` at the 2026-09-02 baseline). The
affected currencies actually present in the pre-cutoff price data are USD
(earliest 2000-01-03), HKD (2000-01-03) and JPY (2003-09-17) — derived from the
store, not assumed.

The store row contract is fixed by `FxRate`
(src/sg_investing/models.py): `rate_date`, `base_currency`,
`rate_to_sgd` (decimal string; **one unit foreign = X SGD**), `source`. The
storage layer (`ParquetStore.upsert_fx`) replaces whole
`data/fx/pair=<BASE>_SGD/year=<YYYY>.parquet` partitions atomically after
validation, merging on `(base_currency, rate_date)`.

## Decision (A0, recorded 2026-09-01)

**MAS is the primary backfill source; ECB is the cross-check. The pull is
minimal and spliced: only dates before each pair's existing first stored date,
over 2000-01-01 → 2003-11-30, and no existing 2003+ Yahoo row is rewritten.**

1. **Sourcing order (A1):** (a) the MAS datastore API on
   `eservices.mas.gov.sg/api` (resource `10bafb02-4b53-4b59-9f8b-35f2c4a4b62f`,
   "Exchange Rates - Daily"); (b) MAS website statistical-table downloads;
   (c) the data.gov.sg mirror of the MAS datasets. Every attempted path and its
   blocker is recorded in the run summary; a failed path is never silently
   substituted. (`api.mas.gov.sg`, named in earlier drafts, does not exist —
   NXDOMAIN verified via Google and Cloudflare DoH on 2026-09-02.)
2. **Units:** MAS tables sometimes quote S$ per 100 foreign units. The scale is
   detected per pair (`detect_unit_scale`) against the ECB cross-check series:
   a median MAS/ECB ratio in [50, 150] ⇒ the series is per 100 units and is
   scaled by 100 before use. All stored rows are normalised to one unit
   foreign = X SGD.
3. **Cross-check (A1):** every sourced rate is compared with the ECB daily
   reference rate via frankfurter.app (no key; frankfurter has SGD crosses for
   the whole window — 999 daily dates per pair for 2000-01-01 → 2003-11-30,
   verified 2026-09-02). Mean/max divergence in basis points is recorded per
   pair; max divergence above 100 bps (1%) is flagged, never silently accepted.
4. **Splice semantics (A2):** `build_fx_rows` writes only dates ≤ 2003-11-30
   that the store does not already have; existing Yahoo rows (2003-12-01+) are
   never keys in the incoming set, so the storage merge cannot touch them.
5. **Normalization (A2):** the MAS pull extends to 2003-12-31 purely to measure
   the seam against the existing series. A ratio
   `mean(existing / mas)` is computed over the last month with ≥ 5 dates
   present in both series (normally 2003-12), and every backfilled row is
   scaled by `unit_scale × ratio`, so no level seam enters SGD returns. A pair
   with no stored history is written as-is (ratio 1). The ratio and its month
   are recorded in the run summary and documented here instead of adding a
   provenance column to the frozen `FxRate` schema.
6. **Provenance:** backfilled rows carry `source: "mas"`; the run summary
   (JSON, printed by the script) is the machine-readable record of source used,
   blockers, coverage gaps, unit scale, normalization ratio and divergence.

## A1 verification — 2026-09-02

`scripts/backfill_fx_history.py` was executed for real (dry-run) for the
required pairs USD, HKD, JPY. Outcome per path:

| Path | Result | Exact blocker |
| --- | --- | --- |
| (a) `eservices.mas.gov.sg/api` datastore | Blocked | Host serves a static failover page (`maintenance.mas.gov.sg/eservice/`) for API requests — no JSON API exists at that host today |
| (b) `www.mas.gov.sg` statistical tables | Blocked | The entire `/statistics/*` section serves a `<title>Maintenance</title>` page (853 KB static page); the MAS homepage renders normally, so this is a section-level outage/migration, not a client error |
| (c) data.gov.sg mirror | Partial, unusable | See below |

data.gov.sg mirror findings (dataset `d_046ff8d521a218d9178178cfbfc45c2c`,
"Exchange Rates, SGD per unit of USD, Daily", Monetary Authority of Singapore):

- It is the **only** daily FX dataset in the entire current data.gov.sg catalog
  (all 4,623 datasets enumerated; 11 are MAS-published; no other daily or
  multi-currency exchange-rate dataset exists).
- Despite its name it is **weekly** over the backfill window: 375 observations
  for 2000-01-07 → 2003-11-12, of which 145 of the ~374 interior gaps are
  exactly 7 days (only late-2003 observations become daily).
- It ends **2003-11-12**, an 18-day hole before the existing Yahoo series
  starts (2003-12-01).
- The list-rows view is capped at 1,000 rows server-side (1988-01-08 →
  2003-11-12); cursor paging restarts at the first page beyond that.
- It has **no HKD or JPY columns at all**.

Cross-check evidence collected during the run (no rows were written):

- USD mirror vs ECB (374 common dates): mean divergence 13.8 bps, max 98.3 bps
  (2000-01-28) — below the 100 bps flag. This validates that the mirror data
  is genuine MAS USD/SGD quotes at the correct unit scale, but not its cadence.
- HKD, JPY: no MAS data on any path; divergence not computable.
- ECB (frankfurter) covers the whole window for all three required pairs
  (999 daily dates each): the cross-check machinery is ready and verified for
  coverage, and was exercised against the mirror data.

## Consequences

1. **The backfill is not executed.** MAS cannot cover 2000-01-01 → 2003-11-30
   with daily rates through any documented path (USD: weekly cadence + 18-day
   terminal hole + list-rows cap; HKD/JPY: no coverage at all). Per A1, the
   exact gaps are reported here and in `docs/fx-sources.md`; no other source
   (frankfurter, Yahoo, archives) is substituted for MAS. Writing the weekly
   mirror series would also be wrong on its own terms: dates before
   2000-01-07 (e.g. QQQ's first price date 2000-01-03) would have **no rate on
   or before them** and stay unresolvable, and dates resolving across the
   18-day hole would breach the engine's 7-day FX-staleness warning
   (`MAX_FX_STALENESS_DAYS`, src/sg_investing/data/packs.py).
2. The manifest is unchanged: 1,437 `fully_supported` / 1,747 `incomplete` /
   4 `unavailable`; QQQ, AAPL, MSFT, SOXX, SMH remain `incomplete` for
   pre-2003-12 years pending FX, and no pack rebuild was run (no input data
   changed).
3. The splice/normalization implementation is complete and unit-tested (22
   synthetic tests, no network), so execution is a single command once MAS
   access returns: `python scripts/backfill_fx_history.py` (dry run; review the
   per-pair coverage and divergence), then `--write`, then a full
   `python scripts/build_data_packs.py` and the parity battery.
4. When the backfill does run, parity fixtures that pin old FX values must be
   regenerated deliberately (A4), and `fx_source` must be surfaced in pack
   provenance (A5, docs/fx-sources.md).
