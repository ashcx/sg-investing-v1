# Golden parity report — Sprint 3, task S3.1

Python engine (`src/sg_investing/`) is authoritative. Every fixture is generated
by `scripts/generate_parity_fixtures.py`, which runs the scenario through the
Python engine, records the `model_dump(mode="json")` envelope as the golden
reference, and writes the equivalent slim input rows consumed by the browser
engine. The runner is `frontend/engine/parity/parity.mjs` (plain Node ≥ 18, no
npm). Re-run generation any time:

```bash
.venv/bin/python scripts/generate_parity_fixtures.py
node frontend/engine/parity/parity.mjs
```

Fixture generation reads only the committed local Parquet store (no live
network calls) and is deterministic: two consecutive runs produce byte-identical
files. All 20 fixtures together are ~340 KB.

## Fixture inventory

| # | Fixture | Category | Kind | Exercises |
| --- | --- | --- | --- | --- |
| 1 | `qqq-2024-analysis-reinvest` | `usd-etf-real` | analysis | Real catalog security (QQQ) over 2024 from the Parquet store via the SGInvestingEngine data path: FX conversion, withholding tax (US 30%), reinvestment at estimated pay dates, unclassified dividend-type warnings, one dividend whose estimated pay date falls outside the price history (incomplete-data warning) |
| 2 | `qqq-2024-dca-monthly` | `dca` | dca | Real-data monthly DCA over 2024 (12 contributions) with dividends, estimated pay dates and XIRR fields |
| 3 | `smh-2023-real-split` | `usd-etf-real` | analysis | Real 2:1 split (SMH, 2023-05-05) applied to held shares before same-period dividend handling; dividend pay date beyond the price history |
| 4 | `synthetic-usd-split-reinvest` | `usd-split-synthetic` | analysis | Hand-built USD case: 2:1 split between ex-date and pay date; entitlement uses pre-split shares, reinvestment uses post-split pay-date close |
| 5 | `sgd-security-dividends-reinvest` | `sgd-security` | analysis | SGD security with no FX history at all (SGD needs no conversion), SGD dividends, missing SG tax rule → "assumed 0%" warnings |
| 6 | `dividend-pay-before-ex-rejected` | `dividend-edge` | analysis | Pay-date-before-ex-date record rejected during validation (error fixture) |
| 7 | `dividend-estimated-pay-date` | `dividend-edge` | analysis | Missing pay date estimated as ex-date + 30 calendar days (a Saturday) then resolved to the next trading day, with the Python-identical warning |
| 8 | `dividend-accumulating-ignored` | `dividend-edge` | analysis | Accumulating fund ignores supplied dividends with a warning; no invented investor cash |
| 9 | `dividend-zero-dividend-security` | `dividend-edge` | analysis | No dividend events: clean `OK` envelope, zero dividend fields, CAGR present |
| 10 | `fx-normal-conversion` | `fx` | analysis | Non-trivial USD/SGD rates at start and end; SGD-vs-native return split |
| 11 | `fx-stale-rate-warning` | `fx` | analysis | FX history ending 10 days before valuation → staleness warning (threshold is >7 days) |
| 12 | `fx-missing-history-rejected` | `fx` | analysis | GBP security with no FX rows → `AnalysisDataError` "No GBP/SGD FX history supplied." (error fixture) |
| 13 | `dividend-after-valuation-excluded` | `incomplete-data` | analysis | Dividend available only after the valuation date → excluded from end-date value with the Python-identical warning (plus an incidental staleness warning; ordering pinned) |
| 14 | `dca-quarterly-synthetic` | `dca` | dca | Quarterly schedule (4 first-trading-day contributions) with XIRR fields |
| 15 | `dca-yearly-synthetic` | `dca` | dca | Yearly schedule (single contribution) with XIRR fields |
| 16 | `dca-monthly-synthetic-cash-dividends` | `dca` | dca | Monthly DCA with `reinvest_dividends: false`: dividends accumulate as cash in the final value |
| 17 | `portfolio-mixed-currency` | `portfolio` | portfolio | Two securities in USD and SGD: buys, partial sell (realized P/L), dividend transaction, deposits/withdrawal, per-currency cash, SGD-denominated realized entry of `"0"` |
| 18 | `portfolio-zero-holding` | `portfolio` | portfolio | Buy then sell everything: holding drops from snapshots, realized P/L remains, cash-only valuation |
| 19 | `portfolio-cash-only` | `portfolio` | portfolio | Only cash deposits/withdrawals: empty holdings, negative cash balance in USD |
| 20 | `portfolio-missing-as-of-price` | `portfolio` | portfolio | Holding with no price on or before the as-of date → `AnalysisDataError` (error fixture) |

Categories: `usd-etf-real` 2, `usd-split-synthetic` 1, `sgd-security` 1,
`dividend-edge` 4, `fx` 3, `incomplete-data` 1, `dca` 4, `portfolio` 4.

## Comparison policy

- **Exact** — object key sets, plain strings, dates, booleans, warnings
  (string-for-string and in order), error type + message.
- **Numeric decimal equality** — decimal-valued fields are compared with
  decimal arithmetic (`Decimal.eq`), so trailing-zero string differences from
  decimal.js normalization (`"3400.00"` vs `"3400"`) are tolerated (documented
  deviation 2 in `frontend/engine/README.md`).
- **XIRR within absolute 1e-9** — `xirr` / `xirr_foreign_currency`: Python runs
  float NPV bisection, the engine keeps every XIRR input in Decimal (documented
  deviation 1).
- **CAGR within absolute 1e-12** — `returns.cagr` / `cagr_foreign_currency` are
  presentation metrics computed through float `pow()`; see mismatches below.
- **Error fixtures** — golden envelope stores
  `{"error": {"type", "message"}}`; the runner requires a throw of the mapped
  engine class (`AnalysisDataError` → `AnalysisDataError`,
  `ValueError` → `EngineValueError`) with the identical message.
- On any mismatch the runner prints a structured diff (`path`, `expected`,
  `actual`) per failing fixture and exits 1; on success it prints per-category
  pass counts and exits 0.

## Mismatches found → root cause → resolution

1. **`dca-monthly-synthetic-cash-dividends` diverged on every
   dividend-sensitive field** (`shares`, `final_value_*`, `gain_loss_*`,
   `xirr*`, `methodology.dividend_reinvestment`).
   - **Root cause:** a bug in the *fixture generator*, not the engine —
     `analysis_input`/`dca_input` built the golden envelope without forwarding
     the per-fixture `scenario`, so Python ran with the default
     `reinvest_dividends=True` while the JS input rows carried
     `reinvest_dividends=false`.
   - **Resolution:** generator fix (forward `AnalysisScenario(**request["scenario"])`);
     fixtures regenerated. No engine change.

2. **`fx-normal-conversion` — `cagr_foreign_currency` differed in the last
   float ulp** (Python `0.21600301183320147` vs engine `0.21600301183320125`,
   |diff| ≈ 2.2e-16).
   - **Root cause:** verified on both sides that every float *input* to the CAGR
     step is bit-identical (`years`, `1/years`, `final/initial` as float); the
     divergence is inside `pow()` itself — glibc's `pow` (used by CPython) and
     V8's `Math.pow` disagree by one ulp for this exponent/value pair. Deviation
     3 in `frontend/engine/README.md` ("matches bit-for-bit") holds for the
     Sprint 2 fixtures but cannot hold universally across libm implementations.
   - **Resolution:** comparison policy — CAGR paths compared within absolute
     1e-12 (documented above and in `parity.mjs`). No engine change: the port
     already mirrors Python's algorithm exactly, and no JS-side change can
     guarantee cross-libm `pow` identity.

**No engine port bugs were found.** None of
`frontend/engine/{analysis,dca,portfolio,fx,dividends,splits,prices,money,calendar,validation,models}.js`
was modified; the parity suite passed after the generator fix and the CAGR
policy refinement.

## Final results

```text
$ node frontend/engine/parity/parity.mjs

==== PARITY RESULTS ====
  dca: 4/4 pass
  dividend-edge: 4/4 pass
  fx: 3/3 pass
  incomplete-data: 1/1 pass
  portfolio: 4/4 pass
  sgd-security: 1/1 pass
  usd-etf-real: 2/2 pass
  usd-split-synthetic: 1/1 pass
  TOTAL: 20/20 pass
```

Regression battery after the changes:

```text
$ node frontend/engine/selftest.mjs
==== SELFTEST SUMMARY: PASS 68 / FAIL 0 ==== all checks green

$ .venv/bin/python -m pytest
172 passed, 8 skipped in 7.71s

$ .venv/bin/ruff check src scripts
Found 30 errors.        # unchanged pre-existing baseline; the new script itself passes ("All checks passed!")
```

## Deferred / notes

- `config/universe.yaml` contains no `currency: SGD` securities (all twelve
  catalog rows are USD-listed), so the SGD case is the documented fallback: an
  in-memory SGD security built through the public `analyze_security` API with
  hand-built price/dividend rows and an empty FX list. The repo's Parquet store
  does contain real SGX market data (`data/prices/market=SG/`) plus a refreshed
  catalog (`data/universe/current_catalog.json`); wiring a real SGD ticker
  through a future catalog extension would be a straightforward fixture add.
- The committed dividend store carries no pay dates at all (all estimated), so
  explicit-pay-date dividend flows are exercised by the synthetic/SGD fixtures
  rather than by real data.
- DCA-specific incomplete-data wording ("becomes available after valuation."
  without the analysis suffix) and the DCA "Could not resolve a trading day"
  path are pinned indirectly via the real-data fixtures (QQQ/SMH exercise the
  analysis variants); a dedicated DCA-variant fixture was not needed because
  both DCA real-data fixtures traverse those branches.
