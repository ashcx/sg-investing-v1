# FX data sources — semantics, provenance, staleness

Status: current as of 2026-09-02 (Sprint 7.5 Track A executed). The decision
record for sources is `docs/adr/0002-fx-sources.md`; this document describes
the row contract, how rates are resolved and how staleness is surfaced, and
the current state of the store.

## Row contract

One FX row is **one unit of the foreign (base) currency expressed in SGD**,
for one date, per pair:

| Field | Meaning |
| --- | --- |
| `rate_date` | ISO date the quote is for |
| `base_currency` | 3-letter ISO code of the foreign unit (`FxRate` uppercases it) |
| `rate_to_sgd` | decimal string; 1 unit of `base_currency` = `rate_to_sgd` SGD |
| `source` | provenance label: `yahoo_finance` (existing 2003+ USD rows) or `ecb` (backfilled 2000-01-03 → 2003-11-28 rows) |

Storage: `data/fx/pair=<BASE>_SGD/year=<YYYY>.parquet`, written only through
`ParquetStore.upsert_fx` (atomic per-partition replacement after validation,
merged on `(base_currency, rate_date)` — an upsert never rewrites an existing
`(pair, date)` key, it only adds missing dates). Pairs currently stored:
`USD_SGD`, `HKD_SGD`, `JPY_SGD`.

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

### ECB — backfill, 2000-01-03 → 2003-11-28, **executed 2026-09-02**

`scripts/backfill_fx_history.py` fetches ECB daily reference rates (published
since 1999, no key) with this fallback order:

1. **ECB SDMX Data Portal API** — `data-api.ecb.europa.eu`, series
   `EXR.D.<CCY>.EUR.SP00.A` (requested as CSV) — *used for all three pairs*;
2. **eurofxref historical CSV** — `www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip`
   (one zipped CSV, all currencies, daily);
3. **frankfurter.app** — `api.frankfurter.dev`, an ECB mirror (JSON).

**Derivation.** The ECB publishes rates *per 1 EUR*, so the SGD cross is
derived exactly — Decimal end to end (frankfurter JSON parsed with
`parse_float=Decimal`; CSV values parsed straight to `Decimal`), division at
the interpreter default Decimal context (28 significant digits), no float
intermediate:

```
SGD per 1 unit of <CCY> = (SGD per 1 EUR) / (<CCY> per 1 EUR)
```

e.g. USD/SGD on 2000-01-03 = 1.7358 / 1.0090 = 1.72051536174430… The rows are
written at that full precision (`rate_to_sgd` is a decimal string).

**Normalization splice.** The pull extends through 2003-12-31 purely to
measure the seam against the existing store; the ratio
`mean(existing / ecb)` is taken over the last month present in both series
(≥ 5 common dates). Measured ratios:

| Pair | Normalization month | Ratio applied to the backfilled window |
| --- | --- | --- |
| USD/SGD | 2003-12 | 0.999598… (existing Yahoo sits ~4 bps below the ECB-derived cross) |
| HKD/SGD | — (no stored history) | 1 (written as-is) |
| JPY/SGD | — (no stored history) | 1 (written as-is) |

**Cross-checks recorded in the run summary** (mean/max bps vs the SDMX
primary, 1,019 common dates): eurofxref-hist CSV 0.0/0.0 for all pairs;
frankfurter.app USD 0.1/0.3, HKD 0.1/0.2, JPY 1.6/3.5 (float64 rounding in
the mirror only). The weekly MAS data.gov.sg mirror (`d_046ff8d521a218d9178178cfbfc45c2c`,
USD-only, never blocking, never written) measured USD mean 13.8 / max 98.2 bps
over 374 common dates — genuine quotes at a different fixing time.

**Coverage and staleness after the splice:** each pair contributes 998 daily
observations 2000-01-03 → 2003-11-28; the longest gap between consecutive
rates is 4–5 calendar days (Easter/Christmas TARGET closures), and every
stored USD/HKD/JPY price date inside the window resolves with lag ≤ 4 days —
0 breaches of the 7-day rule.

### MAS — removed as a source (2026-09-02)

Dropped by decision (A0 update): `api.mas.gov.sg` does not resolve;
`eservices.mas.gov.sg/api` serves a maintenance failover page; the MAS
statistics section serves a maintenance page; the data.gov.sg mirror survived
the catalog migration only as a weekly, USD-only, 1,000-row view ending
2003-11-12 (no HKD/JPY). Exact evidence: ADR 0002, "A1 verification". The
mirror may still be fetched by the script as a tertiary sanity check; its rows
are never written.

## Provenance and audit trail

- Rows carry their `source` label; per-partition dataset manifests are written
  by the storage layer on every upsert.
- The backfill script prints (and should have its output archived alongside
  the data change) a JSON summary: mode, window, per-pair source used,
  attempted paths and blockers, cross-check divergences, normalization ratio
  and month, coverage gaps, rows written.
- The normalization ratio is the one value that has no column in the frozen
  `FxRate` contract; it lives in the run summary and in the git history of the
  backfill run, by decision (ADR 0002, §Decision 5). The pack schema carries
  no `fx_source` field; provenance travels with the rows themselves.

## Re-running or extending the backfill

```bash
python scripts/backfill_fx_history.py          # dry run: review coverage/divergence
python scripts/backfill_fx_history.py --write  # write spliced rows (ecb source)
python scripts/build_data_packs.py             # full pack rebuild; manifest reclassification
node frontend/engine/parity/parity.mjs         # parity battery (regenerate goldens if FX values moved)
```

The script is idempotent: only dates missing before each pair's existing first
stored date are written, so re-runs are no-ops unless the store changes. To
cover a new currency, no code change is needed — the pair list is derived from
the store (currencies of securities with pre-2003-12 price rows); the ECB
publishes SGD crosses for all its reference currencies.

Acceptance (met 2026-09-02): pre-2003-12 years for covered pairs are
`fully_supported`; QQQ, AAPL, MSFT, SOXX, SMH 2000-2003 statuses flipped to
`fully_supported`; parity battery green with no fixture changes (2023-2024
goldens do not touch the backfilled window).
