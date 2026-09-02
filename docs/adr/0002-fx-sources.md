# ADR 0002 — FX history sources: backfill to 2000-01-01, cross-check and splice

- Status: Accepted and **executed** (ECB primary, 2026-09-02; MAS removed as a
  source — see "A1 verification" and "Execution record")
- Date: 2026-09-01 (A0), 2026-09-02 (A1 verification; A0 updated to drop MAS),
  2026-09-02 (execution)
- Decides: Todo/sprint-7.5-fx-incremental-reactive.md Track A tasks A0–A4
- Related: docs/fx-sources.md, scripts/backfill_fx_history.py,
  src/sg_investing/data/packs.py (support classification), Todo/sprint-7.5

## Context

The FX store held one pair, `USD_SGD`, sourced from Yahoo Finance, starting
2003-12-01. Every security priced before 2003-12-01 in a foreign currency was
therefore FX-locked: 1,092 of 3,188 securities have pre-2003-12 price rows, and
the manifest classified their pre-2003-12 years as `incomplete` (1,747
securities `incomplete`; 1,437 `fully_supported`, 4 `unavailable` at the
2026-09-02 baseline). The affected currencies actually present in the
pre-cutoff price data are USD (earliest 2000-01-03), HKD (2000-01-03) and JPY
(2003-09-17) — derived from the store, not assumed.

The store row contract is fixed by `FxRate`
(src/sg_investing/models.py): `rate_date`, `base_currency`,
`rate_to_sgd` (decimal string; **one unit foreign = X SGD**), `source`. The
storage layer (`ParquetStore.upsert_fx`) replaces whole
`data/fx/pair=<BASE>_SGD/year=<YYYY>.parquet` partitions atomically after
validation, merging on `(base_currency, rate_date)`.

## Decision

**ECB is the primary backfill source; the pull is minimal and spliced: only
dates before each pair's existing first stored date, over 2000-01-01 →
2003-11-30, and no existing 2003+ Yahoo row is rewritten.**

1. **Sourcing order (final, 2026-09-02):** (a) the ECB SDMX Data Portal API
   (`data-api.ecb.europa.eu`, series `EXR.D.<CCY>.EUR.SP00.A`, daily reference
   rates since 1999, no key); (b) the eurofxref historical CSV
   (`www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip` — one CSV, all
   currencies, daily since 1999); (c) frankfurter.app (`api.frankfurter.dev`,
   an ECB mirror, no key). Every attempted path and its blocker is recorded in
   the run summary; a failed path is never silently substituted.
   **MAS is removed as a source** (re-checked 2026-09-02: `api.mas.gov.sg`
   does not resolve, `eservices.mas.gov.sg/api` serves a maintenance failover
   page, and the data.gov.sg mirror is weekly, USD-only and ends 2003-11-12 —
   evidence below). It may serve only as an optional tertiary sanity check via
   the mirror, never as a write source.
2. **Derivation:** the ECB publishes reference rates as **per 1 EUR**. The SGD
   cross is derived exactly, with no float intermediate (frankfurter JSON is
   parsed with `parse_float=Decimal`) and no precision loss beyond the
   interpreter default Decimal context (28 significant digits):

   `SGD per 1 unit of <CCY> = (SGD per 1 EUR) / (<CCY> per 1 EUR)`

   e.g. USD/SGD on 2000-01-03 = 1.7358 / 1.0090. All stored rows are normalised
   to one unit foreign = X SGD.
3. **Cross-check:** at least one additional ECB flavor is always fetched per
   pair and the divergence (mean/max bps) is reported (flagged above 100 bps);
   the weekly MAS data.gov.sg mirror (resource
   `d_046ff8d521a218d9178178cfbfc45c2c`) is an optional tertiary sanity check
   where it has a column (USD only) — never blocking, never written.
4. **Splice semantics (A2):** `build_fx_rows` writes only dates ≤ 2003-11-30
   that the store does not already have; existing Yahoo rows (2003-12-01+) are
   never keys in the incoming set, so the storage merge cannot touch them.
5. **Normalization (A2):** the ECB pull extends to 2003-12-31 purely to measure
   the seam against the existing series. A ratio `mean(existing / ecb)` is
   computed over the last month with ≥ 5 dates present in both series
   (2003-12 for USD; none for HKD/JPY, which had no stored history), and every
   backfilled row is scaled by it, so no level seam enters SGD returns. A pair
   with no stored history is written as-is (ratio 1). The ratio and its month
   are recorded in the run summary and documented here instead of adding a
   provenance column to the frozen `FxRate` schema.
6. **Provenance:** backfilled rows carry `source: "ecb"`; the run summary
   (JSON, printed by the script) is the machine-readable record of source used,
   blockers, coverage gaps, normalization ratio and divergence.

## A1 verification — 2026-09-02 (why MAS was dropped)

`scripts/backfill_fx_history.py` was executed for real (dry-run) against the
then-primary MAS paths. Outcome per path:

| Path | Result | Exact blocker |
| --- | --- | --- |
| (a) `eservices.mas.gov.sg/api` datastore | Blocked | Host serves a static failover page (`maintenance.mas.gov.sg/eservice/`) for API requests — no JSON API exists at that host today |
| (b) `www.mas.gov.sg` statistical tables | Blocked | The entire `/statistics/*` section serves a `<title>Maintenance</title>` page (853 KB static page) |
| (c) data.gov.sg mirror | Partial, unusable | Weekly cadence over the window (375 obs for 2000-01-07 → 2003-11-12), ends 2003-11-12 (18-day hole before the Yahoo series starts), list-rows capped at 1,000 rows (1988→2003-11-12), and **no HKD or JPY columns at all** |

The mirror was additionally confirmed to be the **only** daily FX dataset in
the entire current data.gov.sg catalog (all 4,623 datasets enumerated). Its
data is genuine (USD mirror vs ECB, 374 common dates: mean divergence 13.8 bps,
max 98.3 bps) but its cadence and coverage cannot satisfy the engine's 7-day
staleness rule or the pre-2000-01-07 head of the window. Per the 2026-09-02
user decision, MAS was dropped as a required source and ECB promoted to
primary.

## Execution record — 2026-09-02

`scripts/backfill_fx_history.py --write` (ECB primary). Primary source for all
three pairs: `ecb_sdmx_data_portal`. Per pair (window 2000-01-01 → 2003-11-30;
pull extended to 2003-12-31 to measure the seam):

| Pair | Rows written | Coverage | Longest gap | Normalization ratio (month) |
| --- | --- | --- | --- | --- |
| USD/SGD | 998 | 2000-01-03 → 2003-11-28 | 4 days (Easter 2000) | 0.999598… (2003-12, vs existing Yahoo) |
| HKD/SGD | 998 | 2000-01-03 → 2003-11-28 | 4 days (Easter 2000) | 1 (no stored history) |
| JPY/SGD | 998 | 2000-01-03 → 2003-11-28 | 4 days (Easter 2000) | 1 (no stored history) |

Cross-check divergence (basis points, vs the SDMX-derived primary; 1,019
common dates for the two ECB flavors, 374 for the USD-only weekly mirror):

| Pair | eurofxref-hist CSV | frankfurter.app | MAS mirror (tertiary) |
| --- | --- | --- | --- |
| USD | mean 0.0 / max 0.0 | mean 0.1 / max 0.3 | mean 13.8 / max 98.2 |
| HKD | mean 0.0 / max 0.0 | mean 0.1 / max 0.2 | no column — not computable |
| JPY | mean 0.0 / max 0.0 | mean 1.6 / max 3.5 | no column — not computable |

Nothing flagged (all far below the 100 bps threshold): the three ECB flavors
publish the same reference rates (eurofxref byte-equal to SDMX; frankfurter
differs only by float64 rounding), and the weekly USD mirror confirms the MAS
fixing sits within ~14 bps of the ECB 16:00 CET fixing.

Verification after the write:

- Only pre-2003-12 dates written: the rewritten `pair=USD_SGD/year=2003`
  partition carries its 23 pre-existing rows for 2003-12-01+ **identical in
  content and order** (verified against the pre-write bytes from git); the 23
  other pre-existing USD partitions (2004–2026) are byte-identical.
- Staleness: for every stored price date of USD/HKD/JPY securities within the
  backfilled window the resolved FX lag is ≤ 4 days (0 breaches of the
  engine's 7-day rule; worst cases are the Easter and Christmas TARGET
  closures). Maximum gap between consecutive spliced rates: 5 calendar days.
- Manifest after a full pack rebuild: **2,514 `fully_supported` / 670
  `incomplete` / 4 `unavailable`** securities (baseline 1,437/1,747/4). QQQ,
  AAPL, MSFT, SOXX and SMH 2000–2003 years are all `fully_supported`.
  Remaining incompletes are the SGX strict calendar-gap rule (SGD names,
  unrelated to FX) and CNY/EUR/GBP pairs whose pre-cutoff data does not exist
  in the store (no FX needed pre-2003-12 → outside this backfill's minimal
  scope), plus 2003-12+ staleness warnings for HKD/JPY (their FX series
  intentionally ends 2003-11-28; no source contract exists yet for 2003-12+
  HKD/JPY).

## Consequences

1. The backfill **is executed**: `data/fx` holds USD/HKD/JPY vs SGD from
   2000-01-03, spliced to the existing Yahoo USD series with the measured
   ratio; pre-2003-12 foreign-currency security-years classify
   `fully_supported` after a pack rebuild.
2. Future refreshes of the backfill window (or extensions for other
   pre-existing currencies) re-run the same script: it is idempotent (only
   missing dates are written) and re-measures the seam each run.
3. 2003-12+ HKD/JPY FX remains out of scope until a source contract exists
   (Yahoo FX ingestion for those pairs, or another provider); affected
   security-years carry `stale_fx`/`missing_fx` warnings as before.
4. `fx_source` in pack provenance: the pack schema does not carry an
   `fx_source` field, so provenance lives in the FX rows' `source` column and
   the run summary (per decision 5/6 above); no schema field was invented.
