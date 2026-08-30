# SG / Invest — GitHub Pages completion TODO

This checklist tracks the work required for the full frontend experience to run
on GitHub Pages without a runtime backend/API endpoint. The current site is a
static replay: the catalog and representative QQQ artifacts load, but arbitrary
analysis, DCA, comparison and portfolio requests still depend on the Python
adapter or a checked-in artifact.

## Release definition

- [ ] Confirm the target is a fully static GitHub Pages site with no runtime
      `/api` dependency. GitHub Actions may build/publish data, but the browser
      must be able to complete supported calculations offline after its data is
      loaded.
- [ ] Record the chosen calculation architecture: a shared Rust/WASM core is
      preferred; a TypeScript implementation using a decimal arithmetic library
      is an acceptable alternative if parity tests are comprehensive.
- [ ] Update the frontend specification and README when the architecture is
      approved. The current specification keeps financial calculation logic in
      Python, which must change for arbitrary no-API calculations.

## 1. Static data publishing

- [ ] Define versioned browser data-pack schemas for daily native prices, FX,
      dividend events, security metadata, coverage and provenance.
- [ ] Generate packs for every supported security, not only the current
      representative QQQ analysis/DCA/comparison/portfolio/series artifacts.
- [ ] Publish packs in security/year partitions so the browser loads only the
      securities and date ranges a user requests.
- [ ] Include `data_snapshot_id`, catalog version, methodology version, source,
      coverage dates and data-quality warnings in every pack/manifest.
- [ ] Add a manifest that tells the client whether a security/date range is
      fully supported, incomplete or unavailable before calculation begins.
- [ ] Update the data-refresh workflow to build and publish the frontend data
      artifact after a validated snapshot. Do not require committing canonical
      Parquet files to the public repository.
- [ ] Add payload-size, cache and load-time budgets. Use lazy loading and
      IndexedDB/browser caching for previously loaded packs.
- [ ] Decide whether external fonts/assets should be self-hosted so the site
      remains deterministic when third-party requests are unavailable.

## 2. Portable calculation engine

- [ ] Extract or port the authoritative backend calculations into a browser
      module/WASM worker without changing the financial methodology.
- [ ] Use decimal-safe arithmetic throughout; do not use JavaScript `Number` for
      financial calculations, FX conversion, share quantities or XIRR inputs.
- [ ] Preserve the backend rules for next-trading-day purchases, previous-close
      valuation, FX direction, dividend withholding, pay-date estimates,
      reinvestment and accumulating funds.
- [ ] Return the same result envelopes and provenance fields as the Python
      engine, including warnings and coverage status.
- [ ] Add golden parity tests that run identical fixtures through Python and the
      browser engine for USD and SGD securities, dividends, FX and incomplete
      data cases.
- [ ] Add property tests for rounding, contribution scaling, split handling,
      cash-flow ordering and deterministic request keys.
- [ ] Run calculations in Web Workers with cancellation/error handling so large
      date ranges do not block the interface.

## 3. DCA — full static-site support

- [ ] Replace the static-mode `/api/dca` dependency with the local calculation
      engine and lazily loaded security data packs.
- [ ] Support monthly, quarterly and yearly contribution schedules using the
      backend's first-available-trading-day rule.
- [ ] Support dividends, withholding tax, reinvestment, fractional shares,
      native-currency output, SGD output and both XIRR fields.
- [ ] Preserve explicit warnings for estimated/missing pay dates, missing FX,
      incomplete price history and unverified dividend coverage.
- [ ] Add parity fixtures for USD ETFs, SGX/SGD securities, accumulating funds,
      zero-dividend cases and invalid date/amount inputs.
- [ ] Show a clear loading/progress state while a data pack or worker result is
      being resolved; never show a result from a different request.

## 4. Portfolio reconstruction — full static-site support

- [ ] Move ledger reconstruction into the local engine. Arbitrary user-entered
      ledgers cannot be precomputed as static artifacts.
- [ ] Support BUY, SELL, DIVIDEND, CASH_DEPOSIT and CASH_WITHDRAWAL transactions
      with the existing validation and ordering rules.
- [ ] Load only the required security price/dividend/FX packs for the ledger's
      holdings and selected as-of date.
- [ ] Match backend weighted-average cost, native market value, SGD value,
      realised P/L, unrealised P/L and cash-by-currency output exactly.
- [ ] Preserve the as-of previous-close rule, missing-price behavior and all
      data-quality warnings.
- [ ] Keep ledger data local in IndexedDB; add explicit clear, export and import
      behavior so users control persistence and backup.
- [ ] Add parity fixtures for buys, partial sells, multiple currencies,
      dividends, cash-only rows, zero holdings and missing as-of prices.
- [ ] Continue to exclude unsupported portfolio-level return, allocation and
      time-series claims unless the backend contract supplies them.

## 5. Remove misleading API/static fallbacks

- [ ] Add an explicit static/local-compute mode and show it in the UI.
- [ ] Replace all runtime `/api` calls with local-engine calls when the API base
      is empty; retain the adapter only as an optional development/reference
      mode.
- [ ] Fix comparison fallback behavior: a failed custom comparison must not
      silently render the checked-in QQQ/SMH/SOXX demo artifact.
- [ ] Ensure a missing or stale pack produces a clear unavailable state with the
      requested security/date range, never a result from another request.
- [ ] Keep native/SGD switching presentation-only and map directly to the
      result contract in both local and adapter modes.

## 6. GitHub Pages release hardening

- [ ] Keep `.github/workflows/pages.yml` as the deployment path and verify it on
      the repository's actual default branch (the current workflow assumes
      `main`).
- [ ] Add CI checks for static asset paths under a repository project subpath,
      missing data packs, malformed JSON and broken internal links.
- [ ] Run the full Python suite, browser-engine parity suite and static-site
      smoke tests before publishing.
- [ ] Add a generated build identifier and visible snapshot date to the site;
      fail the build if required artifacts are stale or inconsistent.
- [ ] Pin third-party action/library versions and confirm no credentials or
      private market data are included in the Pages artifact.
- [ ] Set a Content Security Policy and review external requests, downloads and
      client-side storage behavior.
- [ ] Repeat Chrome QA at desktop and mobile widths for catalog, analysis,
      currency switching, DCA, portfolio, comparison, warnings and offline
      reload behavior.
- [ ] Document repository setup: create the Git repository, push the default
      branch, enable Pages with GitHub Actions, and confirm the deployed URL.

## Done when

- [ ] A fresh GitHub Pages deployment can calculate a new supported DCA request
      for any covered security without a network call to `/api`.
- [ ] A fresh GitHub Pages deployment can reconstruct an arbitrary supported
      portfolio ledger entirely in the browser.
- [ ] Results match the Python reference fixtures, retain provenance/warnings,
      and never silently substitute a demo artifact.
- [ ] The site remains responsive, accessible and usable when data is missing,
      incomplete or stale.
