# SG / Invest portable calculation engine (Sprint 2)

Browser-native ES2022 port of the authoritative Python engine
(`src/sg_investing/`). No build step, no npm; modules are imported directly by
a page or a Web Worker (worker execution is Sprint 3). Runs unmodified under
Node >= 18 for self-testing (`node frontend/engine/selftest.mjs`).

## Vendored arithmetic

- `frontend/vendor/decimal.mjs` — **decimal.js v10.6.0** (exact upstream file
  from `https://cdn.jsdelivr.net/npm/decimal.js@10/decimal.mjs`, pinned by
  content below), vendored with no modification.
- Context set in `money.js`: `Decimal.set({ precision: 28, rounding:
  ROUND_HALF_EVEN })`, mirroring Python `getcontext().prec = 28` and the
  default `ROUND_HALF_EVEN`.
- sha-256 of the vendored file is recorded here at pin time:
  `SHA256=45e6ecc0a500fee6439acdf67ee2e9322aab57e6ea0409ef52993dedbba8cf19`

## Module map (mirrors the Python structure)

| Engine module | Python counterpart |
| --- | --- |
| `money.js` | `decimal` context + `analysis.py` constants (`_ONE`, `_ZERO`, `_DAYS_PER_YEAR`, `_MAX_FX_STALENESS_DAYS`) |
| `calendar.js` | `datetime.date` arithmetic + `bisect` (`bisect_left`, `bisect_right`, `insort`) |
| `models.js` | `models.py` enums/scenario defaults, `AnalysisDataError`/`ValueError` |
| `fx.js` | `analysis.py` `_rate_for_date`, `_rate_for_date_with_staleness`, `_warn_if_fx_is_stale` |
| `prices.js` | `analysis.py` `_sorted_prices`, `_resolve_price` |
| `validation.js` | `data/validation.py` `validate_dividends`, `dividend_event_key` |
| `dividends.js` | `analysis.py` `_tax_rate_for`, pay-date estimate, accumulating/type-warning handling |
| `splits.js` | corporate-action grouping and `shares *= ratio` application |
| `analysis.js` | `analysis.py` `analyze_security` |
| `dca.js` | `calculations/dca.py` `dca_analysis`, `xirr`, `_contribution_dates` |
| `portfolio.js` | `calculations/portfolio.py` `analyze_portfolio` |
| `index.js` | public barrel |
| `selftest.mjs` | fixture-driven verification harness (Sprint 2 exit evidence) |
| `fixtures/` | real envelopes dumped from the Python engine plus equivalent JS inputs |

## Methodology preserved (S2.3)

- Purchase resolves to the **next trading day**, valuation to the
  **previous trading day** (`prices.js`, exact Python error strings).
- FX is **one unit of foreign currency = X SGD**; rates resolve with the
  previous-trading-day rule and a 7-calendar-day staleness warning.
- Dividend cash is available on the **pay date**; when absent it is estimated
  as **ex-date + 30 calendar days** and then resolved to the next trading day,
  recording the Python-identical warning.
- A dividend whose **pay date precedes its ex-date** is rejected (validation
  error), never turned into an impossible cash flow.
- **Accumulating / non-distributing** securities ignore supplied dividend
  events with a warning; no invented investor cash.
- Reinvestment happens on the resolved **pay-date close** (fractional shares),
  after any same-date corporate action and entitlement, and the resolved date
  is inserted into the chronological timeline exactly as the Python loop does.
- Splits multiply held shares at the effective date **before** same-day
  dividend entitlements.
- DCA invests on the **first available trading day** of each monthly,
  quarterly, or yearly period and reports money-weighted XIRR.
- Portfolio uses **weighted-average cost basis**, mark-to-market end value,
  realized/unrealized P&L, and per-currency cash.

## Result envelopes (S2.4)

Envelopes mirror the Python `model_dump(mode="json")` shapes: `Decimal`
fields are emitted as JSON strings, dates as `YYYY-MM-DD` strings, enums as
their string values, and `data_quality` carries `status` + `warnings`.
The Python-side reference fixtures in `fixtures/` were dumped with
`.venv/bin/python` via `SGInvestingEngine.analyze` / `dca_analysis` /
`analyze_portfolio` (QQQ, 2024-01-02..2024-07-01, real Parquet data).

Verification result: the analysis envelope matches the Python dump **exactly**
(every key, value and warning). The DCA envelope matches except `xirr` /
`xirr_foreign_currency`, which agree within 1e-9 (see deviations). The
portfolio envelope matches on all keys/types with decimal values equal;
string forms may differ in trailing zeros (see deviations). **No envelope key
is unmatched.**

## Documented deviations

1. **XIRR internals.** Python's `xirr` runs float NPV bisection on
   `float(amount)` values. The JS port keeps every XIRR *input* as `Decimal`
   and runs the same bracketed bisection (`[-0.9999, 10.0]`, doubling,
   200 iterations, 1e-10 tolerance) in Decimal arithmetic, so roots agree
   with Python to ~1e-9 or better but not bit-for-bit.
2. **Trailing zeros.** decimal.js normalizes away insignificant trailing
   zeros (`1653` vs Python's `Decimal("1653.0")`); values are numerically
   equal, string forms can differ in scale.
3. **CAGR.** Python computes CAGR as a derived presentation metric via float
   (`float(final/initial) ** (1/years) - 1`); the port mirrors that exactly
   so values match bit-for-bit. No money/FX/quantity/XIRR input ever touches
   `Number`.
4. **`Number` usage.** Restricted to array indices/loop counters, calendar
   arithmetic (`calendar.js`), FX staleness day counts, DCA period-key
   extraction, and the CAGR float presentation step — never money, FX rates,
   share quantities, dividends or XIRR inputs.

## Fixtures

- `inputs-qqq-2024h1.json` — normalized inputs (slim price/dividend/FX/action
  rows carrying exactly the fields the engine consumes).
- `analysis-qqq-2024h1.json`, `dca-qqq-2024h1.json`,
  `portfolio-fixture-2024.json` — authoritative Python envelopes.
