# FX data sources — semantics, provenance, staleness

Status: current as of 2026-09-02 (Sprint 7.5 Track A). The decision record for
sources is `docs/adr/0002-fx-sources.md`; this document describes the row
contract, how rates are resolved and how staleness is surfaced, and the current
state of the store.

## Row contract

One FX row is **one unit of the foreign (base) currency expressed in SGD**,
for one date, per pair:

| Field | Meaning |
| --- | --- |
| `rate_date` | ISO date the quote is for |
| `base_currency` | 3-letter ISO code of the foreign unit (`FxRate` uppercases it) |
| `rate_to_sgd` | decimal string; 1 unit of `base_currency` = `rate_to_sgd` SGD |
| `source` | provenance label: `yahoo_finance` (existing 2003+ rows) or `mas` (backfill, once executed) |

Storage: `data/fx/pair=<BASE>_SGD/year=<YYYY>.parquet`, written only through
`ParquetStore.upsert_fx` (atomic per-partition replacement after validation,
merged on `(base_currency, rate_date)` — an upsert never rewrites an existing
`(pair, date)` key, it only adds missing dates).

## Resolution and staleness (engine contract)

For a price date `d` in a foreign currency, the engine resolves the **latest
rate on or before `d`** (`bisect_right` − 1 semantics, the engine's
previous-trading-day rule):

- **Missing:** no rate exists on or before `d` (rate series starts after `d`).
  The price date is unresolvable; the pack year is `incomplete` with a
  `missing_fx` count.
- **Stale:** the rate resolves but the lag `d − rate_date` exceeds
  `MAX_FX_STALENESS_DAYS = 7` days. The year remains `fully_supported` but the
  manifest records a `stale_fx` count and the maximum lag (7 days covers
  weekends plus one holiday; a weekly source would breach it almost every
  week).

Range support is the worst of the intersecting in-window years
(`classify_range`, frozen rules in `docs/data-pack-schema.md`).

## Sources

### Yahoo Finance — current, 2003-12-01 → present

- Pair: `USD_SGD` only. Source label: `yahoo_finance`.
- Daily quotes as stored by the Sprint ≤7 ingestion pipeline.

### MAS backfill — designed, 2000-01-01 → 2003-11-30, **not yet executed**

`scripts/backfill_fx_history.py` implements the A0 decision (ADR 0002):
MAS primary (datastore API → statistical tables → data.gov.sg mirror), ECB
cross-check via frankfurter.app, per-100-unit scale detection against the
cross-check, minimal splice (only dates before the pair's existing first
stored date), and a normalization ratio measured over the last month present
in both the sourced series and the existing store so no level seam enters SGD
returns. Per-pair coverage gaps (first/last observation, longest date gap) and
MAS-vs-ECB divergence (mean/max bps, flagged above 100 bps) are printed in the
run summary.

**Status (verified 2026-09-02):** blocked — `eservices.mas.gov.sg` API serves
a failover page, the MAS statistics section serves a maintenance page, and the
data.gov.sg mirror survived the catalog migration only as a weekly,
USD-only, 1,000-row view ending 2003-11-12 (no HKD/JPY). Exact evidence and
the measured mirror-vs-ECB divergence (mean 13.8 bps, max 98.3 bps) are in
ADR 0002. No rows have been written; substituting another source is
explicitly out of scope per A1.

### ECB (frankfurter.app) — cross-check only, never a write source

- No key; daily reference rates with SGD crosses covering the whole backfill
  window (999 daily dates per pair, 2000-01-01 → 2003-11-30, verified
  2026-09-02).
- Used for: per-100-unit scale detection, divergence statistics, and (after any
  future MAS outage) nothing else — rates are never written from it.

## Provenance and audit trail

- Rows carry their `source` label; per-partition dataset manifests are written
  by the storage layer on every upsert.
- The backfill script prints (and should have its output archived alongside the
  data change) a JSON summary: mode, window, per-pair source used, attempted
  paths and blockers, unit scale, normalization ratio and month, coverage gaps,
  divergence stats, rows written.
- The normalization ratio is the one value that has no column in the frozen
  `FxRate` contract; it lives in the run summary and in the git history of the
  backfill run, by decision (ADR 0002, §Decision 5).

## Re-running the backfill (once MAS access is restored)

```bash
python scripts/backfill_fx_history.py          # dry run: review coverage/divergence
python scripts/backfill_fx_history.py --write  # write spliced rows (mas source)
python scripts/build_data_packs.py             # full pack rebuild; manifest reclassification
node frontend/engine/parity/parity.mjs         # regenerate changed goldens deliberately
```

Acceptance: pre-2003-12 years for covered pairs become `fully_supported`
(modulo the strict gap rule on SGX names, which is unrelated to FX); QQQ,
AAPL, MSFT, SOXX, SMH 2000-2003 statuses flip accordingly; parity battery
green with any FX-pinned fixtures regenerated deliberately.
