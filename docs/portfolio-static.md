# Portfolio reconstruction on a static site — Sprint 5

Status: implemented 2026-09-01 (S5.1–S5.8). Scope: arbitrary user-entered
ledgers reconstructed entirely in the browser with exact backend parity and
local-only ledger persistence.

## Data flow (S5.1–S5.5)

`frontend/app.js` `submitPortfolio` (portfolio/ledger region only):

1. **Collect + validate.** Ledger rows are read from `#ledger-rows`
   (BUY / SELL / DIVIDEND / CASH_DEPOSIT / CASH_WITHDRAWAL, security or cash
   only, date, quantity, cash amount, currency, fees fixed at `"0"` because the
   ledger UI has no fees input). Client-side validation covers missing as-of
   date, missing row dates and negative/blank numerics; everything deeper
   (unknown security, currency mismatch, oversell, missing prices, bad FX) is
   left to the engine so the Python-parity error messages surface unchanged in
   `#portfolio-error`.
2. **API first (adapter mode).** The existing POST to `api/portfolio`
   (`API_BASE`-prefixed when the adapter meta tag is set, relative otherwise)
   is tried first — unchanged behaviour. A successful response renders exactly
   as before.
3. **Local fallback.** On any API failure the request is rebuilt locally via
   `s5LocalPortfolio`:
   - the distinct holding `security_id`s are resolved against the pack
     manifest (`packLoader.findSecurity`);
   - **support gate (S5.4/S5.5):** `packLoader.supportFor(entry, first
     transaction date, as_of)` decides per holding — `unavailable` (unknown
     security or range outside the covered years) renders a clear unavailable
     state in `#portfolio-results` naming the security ticker and the as-of
     date, and never a different result; `incomplete` proceeds and the reason
     plus pack data-quality warnings are surfaced inline; `fully_supported`
     proceeds silently;
   - **pack inputs (S5.3):** `packLoader.loadSecurityInputs(entry, first date,
     as_of)` loads only the security-year packs the ledger actually needs (one
     pack per holding-year, nothing for cash-only rows), cached per
     `security_id` in a module map and reloaded only when a later request
     extends the range;
   - **FX harvest:** cash currencies with no loaded pack (e.g. a USD cash
     deposit in an all-SGD ledger) borrow the as-of year FX block from one
     manifest security of the same native currency; SGD needs no FX.
   - **engine:** the payload `{as_of, transactions, securities, prices,
     fx_rates}` (all numerics strings, exactly the frozen worker-protocol
     contract for scope `portfolio`) goes through
     `engineClient.portfolio()` → `worker.js` → `analyzePortfolio`, and the
     Python-shaped envelope renders via `renderPortfolio` (WAC, native/SGD
     market values, realised/unrealised P/L, cash-by-currency, previous-close
     as-of rule).
4. **Failures show errors.** The silent demo-artifact fallback is removed: if
   both API and local paths fail, the error message is displayed and nothing
   else renders.

### Ordering and tie-breaks (S5.2)

The engine sorts transactions by `(transaction_date, transaction_id)` —
verified identical to `src/sg_investing/calculations/portfolio.py`. The local
path synthesises deterministic ids `s5-000001…` in row order, so same-day ties
resolve by row order (the documented convention). Note: the Python dev-server
adapter lets pydantic default `transaction_id` to a random UUID, so same-day
tie order is only deterministic in the local engine path; fixtures pin explicit
ordered ids.

### engine-client tracker note

The frozen `createEngineClient()` calls `tracker.nextId(scope, payload)`,
which the frozen `createRequestTracker()` does not expose. Both files are
frozen, so `app.js` injects a tracker adapter (`s5CompatibleTracker`, shared
import block with the S4 wiring) that bridges
`nextId → requestId(scope, payload) + track(id, scope)` while keeping
`observe` / `markCancelled` / `supersedeScope`. S6/S7 may want to reconcile
this inside `protocol.js`.

## Ledger persistence (S5.6)

`frontend/ledger-store.js` — local-only, user-controlled, injectable backend:

- **IndexedDB driver** (browser): database `sg-invest-cache`, **version 2**,
  out-of-line key `"current"` in a `ledger` object store created additively in
  `onupgradeneeded` per `docs/data-pack-budgets.md`. It never touches or
  recreates the `packs`/`meta` stores and ledger entries are never evicted by
  pack-cache pressure.
- **In-memory driver** (Node tests): same contract, no persistence.
- **API:** `ledgerStore.save(ledger)`, `.load()`, `.clear()`,
  `.exportJson()`, `.importJson(json)`; `createLedgerStore(driver)`,
  `createIndexedDbDriver()`, `createMemoryDriver()` for injection.
- **Row shape (validated on save/import):** `{transaction_type ∈
  BUY|SELL|DIVIDEND|CASH_DEPOSIT|CASH_WITHDRAWAL, security_id: string|null,
  transaction_date: YYYY-MM-DD, quantity/cash_amount/fees: numeric strings,
  currency: three-letter code}`.
- **When saved:** on every ledger edit (`change` events on `#ledger-rows`, the
  `+ Add transaction` button, Clear and Import). The initial demo row is not
  auto-saved until the user edits; on the next visit `s5RestoreLedger()`
  replaces the default row with the persisted ledger.
- **Buttons (existing CSS classes only):** Clear ledger (wipes the store and
  the table), Export JSON (downloads `sg-invest-ledger.json`), Import JSON
  (file picker; validates, persists, re-renders rows).
- **Export/import contents:** an envelope
  `{schema: "sg-invest-ledger", version: 1, exported_at: ISO-8601, rows: [...]}`;
  `importJson` also accepts a bare row array and rejects malformed rows with a
  per-row message.

## Parity (S5.7, S5.8)

- `scripts/generate_portfolio_fixtures.py` (new; `generate_parity_fixtures.py`
  untouched) runs ledgers through the **Python** engine
  (`analyze_portfolio(...).model_dump(mode="json")`) and writes goldens plus
  slim inputs to `frontend/engine/parity/fixtures/portfolio-fixtures/` — a
  dedicated **subdirectory** so the frozen Sprint 3 runner
  (`parity.mjs`) stays exactly 20/20.
- Cases: QQQ buy-and-hold and buy + partial sell derived from the **real data
  packs** (the exact rows `pack-loader.js` assembles), synthetic multiple
  currencies + partial sell + dividends + cash rows, dividends-only cash
  effect, cash-only rows, zero holdings, and a missing as-of price error
  golden (`AnalysisDataError`, Python message preserved).
- `node frontend/engine/portfolio-packs-integration.mjs` (new) verifies with
  the fs fetcher + `createPackLoader` + frozen `worker.js` protocol validation
  + `analyzePortfolio`: **7/7 fixtures** (pack-derived goldens match exactly;
  shuffle-invariance for every result fixture) and **7/7 ledger-store checks**
  — 14/14 total.
- Cross-check: the pack-derived QQQ buy-hold golden is string-identical in
  `total_market_value_sgd` and Decimal-identical in every holding field to the
  committed parquet-based `data/portfolios/demo-qqq.json` for the same
  request.
- No portfolio-level return, allocation or time-series claims were added
  (S5.8) — the envelope remains exactly `as_of / holdings / cash_by_currency /
  realized_pl_native / total_market_value_sgd / methodology`.
