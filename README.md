# SG / Invest

**Live site:** [sg-investing-v1](https://ashcx.github.io/sg-investing-v1/)

SG / Invest is a Singapore-focused investment analytics engine and static web
application. It helps answer:

> What would an investment have returned in its native currency and in SGD,
> after FX movement, dividends, and applicable investor-level withholding tax?

The calculation engine is authoritative in Python and also runs in the browser
through a parity-tested JavaScript port that uses decimal arithmetic for
monetary values. The deployed site has no runtime calculation API: it loads
published data packs and computes locally in a Web Worker.

## Current status

This is a functional preview at version `0.1.0`. The core feature roadmap is
implemented through Sprint 8, while data coverage, operational workflows, and
polish continue to evolve. The sprint status and final acceptance checklist
are tracked in [`TODO.md`](TODO.md).

The project is designed to be explicit about uncertainty. A security or date
range may be classified as `fully_supported`, `incomplete`, or `unavailable`;
the frontend keeps those states visible instead of silently substituting a
different result.

## What you can do

- Explore the security catalog by ticker, name, ISIN, exchange, market,
  currency, asset type, universe, distribution policy, and active status.
- Replay a historical investment in both the security's native currency and
  SGD.
- Compare price return, total return, gross dividends, net dividends,
  withholding tax, FX effects, and CAGR.
- Toggle dividends, withholding tax, and dividend reinvestment independently.
- Model cash dividends, pay-date reinvestment, fractional shares, stock splits,
  and reverse splits.
- Run monthly, quarterly, or yearly DCA scenarios and inspect contribution
  dates, shares, ending value, gain/loss, and XIRR.
- Reconstruct a portfolio from BUY, SELL, DIVIDEND, CASH_DEPOSIT, and
  CASH_WITHDRAWAL transactions using weighted-average cost basis.
- Persist a ledger locally in IndexedDB, then clear, import, or export it.
- Compare two to six securities with the same dates, capital, and scenario.
- Inspect native and SGD daily price series, view the underlying table, and
  download CSV or JSON results.
- See methodology versions, data snapshots, provenance, warnings, and support
  explanations attached to results.

## Data coverage and hosting

The checked-in catalog snapshot is dated 2026-08-30 and contains 3,172 unique
securities represented by 3,260 universe-membership rows. The catalog includes:

- 1,946 Russell 2000 constituents
- 708 active SGX equities, REITs, business trusts, and ETFs
- 489 S&P 500 entries
- 101 Nasdaq-100 entries
- Russell 2000 benchmark data
- Major global ETFs including QQQ, SMH, SOXX, IWM, VALL.SW, and selected
  Irish-domiciled UCITS ETFs
- Auditable manual additions and source-labelled universe memberships

The complete browser pack build contains 3,188 securities, including 16
priced-but-uncatalogued entries. It is too large for GitHub Pages on its own:

- **Tier 1 — GitHub Pages:** 1,242 securities, excluding the Russell 2000
  constituent universe. The measured deployment is approximately 747 MB.
- **Tier 2 — Cloudflare R2:** the full pack set, including Russell 2000
  constituents. The frontend consults Tier 1 first and uses the configured R2
  origin for securities missing from the Pages manifest.
- **Tier 3 — canonical data:** validated Parquet data and generated packs used
  by CI and local development.

The generated data-status artifact currently reports 3,109 stored securities,
59 incomplete records, and 4 unavailable records in the 3,172-security
catalog snapshot. These counts describe data coverage, not catalog membership:
an entry can exist in the catalog while its price history is incomplete or
unavailable.

## Architecture

The system has four cooperating layers:

1. **Canonical Python engine — `src/sg_investing/`**

   Provides deterministic financial calculations, Pydantic contracts, tax-rule
   selection, date resolution, dividend handling, FX conversion, DCA, portfolio
   reconstruction, and JSON-serializable result envelopes.

2. **Canonical data store — `data/`**

   Stores unadjusted daily OHLCV, dividends, corporate actions, FX, catalog
   metadata, coverage reports, and manifests as partitioned Parquet or JSON
   artifacts. Git LFS holds the large canonical snapshot.

3. **Pack pipeline — `scripts/` and CI workflows**

   Validates the canonical snapshot, builds lazy-loadable security/year JSON
   packs, records provenance and support status, merges scoped incremental
   rebuilds, prunes the GitHub Pages tier, and synchronizes the full pack set
   to the Tier-2 origin.

4. **Static frontend — `frontend/`**

   Loads the catalog and only the packs required by a request. A vendored
   decimal library and Web Worker execute the browser calculation engine. The
   frontend uses deterministic request keys, cancellation, stale-response
   guards, and explicit unavailable states.

Golden fixtures, property tests, and worker tests compare the browser engine
with the Python reference engine.

## Computation modes

### Static/local mode

This is the deployed default. The browser performs calculations locally from
published packs and makes no runtime `/api` calls. The pack origin may be the
same GitHub Pages site or the configured Tier-2 static origin; neither is a
calculation server.

Selecting a security loads its series automatically. Analysis, DCA, and
portfolio panels run after debounced input changes, while their buttons remain
available as immediate **Force refresh** actions.

### Adapter mode

[`scripts/frontend_server.py`](scripts/frontend_server.py) serves the same UI
with read-only routes backed by the Python engine. Set the
`sg-invest-api-base` meta tag to use it during development. When configured,
the adapter is tried first and the local engine remains an explicit fallback.
The UI identifies whether a visible result came from the local engine, the
adapter, or the initial published example replay.

The adapter exposes:

```text
GET  /api/catalog
GET  /api/status
GET  /api/analyze
GET  /api/series
GET  /api/compare
GET  /api/dca
POST /api/portfolio
```

## Python entry points

The main Python calculation functions are importable without the frontend:

```python
from sg_investing.analysis import analyze_security
from sg_investing.calculations.dca import dca_analysis
from sg_investing.calculations.portfolio import analyze_portfolio
```

The adapter and browser worker adapt these functions into the same structured,
JSON-compatible result shapes. The higher-level `SGInvestingEngine` also loads
the configured catalog, Parquet store, and tax rules for standard security
analysis.

## Financial methodology

The engine keeps observed data and modeled investor assumptions separate.

- **Prices:** daily, unadjusted local-exchange OHLCV. A purchase resolves to
  the next available trading day; valuation resolves to the previous available
  trading day.
- **FX:** one unit of the foreign currency equals `X` SGD. For example,
  USD/SGD `1.35` means US$100 equals S$135. FX is resolved using the latest
  available rate on or before the requested date, with staleness warnings.
- **Dividends:** stored independently from prices. A missing pay date is
  approximated as ex-date plus 30 calendar days, then moved to the next local
  trading day; the approximation is recorded as a warning.
- **Dividend timing:** a dividend becomes available on its pay date. If
  reinvested, withholding is applied first and the net amount is invested at
  the resolved pay-date closing price. Fractional shares are allowed.
- **Tax:** investor-level withholding is configuration-driven, security-aware,
  country-aware, and effective-date-aware. A missing rule is surfaced and
  modeled as zero withholding rather than silently inventing a rate.
- **Accumulating funds:** no investor dividend cash is invented for
  accumulating or non-distributing securities.
- **Corporate actions:** stock splits and reverse splits are modeled as
  separate events against the unadjusted price series.
- **TER:** ETF expense ratio is metadata only. It is not subtracted from
  observed historical ETF performance because it is generally already reflected
  in the fund's NAV.
- **Costs and taxes:** V1 does not model brokerage, sale, FX-conversion, or
  slippage costs and does not calculate Singapore capital-gains tax.
- **Portfolio basis:** realized and unrealized P&L uses weighted-average cost
  basis. This is a reporting convention, not Singapore tax-lot accounting.
- **Valuation:** output is mark-to-market at the valuation date; V1 does not
  assume a sale on that date.

For foreign securities, fields ending in `foreign_currency` use the security's
native currency. Dividend fields ending in `*_sgd_at_payment` use the payment-
date FX rate; ending values and SGD returns use the valuation-date FX rate
where applicable.

## Data refresh and publishing

### Incremental refresh

The daily update workflow runs after the US close and can also be dispatched
manually:

```bash
python scripts/update_incremental.py --since auto
```

It refreshes only the required tails and reconciliation windows, including:

- New or restated prices
- Late or restated dividends
- Corporate actions
- Required FX tails and gap fills
- Only the affected security/year packs
- The merged pack manifest and incremental snapshot metadata

The CI workflow deliberately does not auto-commit. It uploads changed data and
packs as a short-lived artifact for operator review. After validation, an
operator applies and commits the canonical changes, which triggers the normal
deployment pipeline.

### Full rebuild

Use the full path for quarterly reconciliation, catalog changes, or methodology
changes:

```bash
python scripts/refresh_universe.py
python scripts/update_data.py
python scripts/build_data_packs.py
python -m pytest -m "not smoke"
```

The full build resets generated packs and rebuilds the manifest from the
canonical store. It is substantially slower than an incremental update.

### Tier-2 synchronization

After a validated Tier-1 deployment, CI synchronizes the full pack set to the
configured Cloudflare R2 bucket and verifies the remote snapshot ID and
security count. If the external origin is unavailable, affected Tier-2
securities show an explicit unavailable state; Tier-1 securities continue to
work.

## Known limitations

- Coverage is not uniform. The manifest may classify individual securities or
  date ranges as incomplete or unavailable.
- The full pack integration tests require generated packs. `frontend/data/packs/`
  is intentionally gitignored, so a clean checkout must run
  `python scripts/build_data_packs.py` before those tests can run.
- A full offline reload without a service worker is not supported. Warm browser
  caches can reuse the manifest and packs, but the application still needs its
  static host for a fresh page load.
- Chrome QA found remaining mobile overflow in the compact header and a
  populated portfolio ledger. The portfolio table itself is horizontally
  scrollable, but the surrounding layout still needs refinement.
- Portfolio-level time-weighted return, money-weighted return, allocation, and
  exposure analytics are not part of the current V1 portfolio result.
- Ruff currently reports existing repository findings even though the Python
  test suite passes. The test workflow is the current CI gate.

## Running locally

Install the project and development dependencies:

```bash
python -m pip install -e ".[dev,market-data]"
```

Run the Python suite without smoke tests or live-data checks:

```bash
python -m pytest -m "not smoke"
```

Build the browser data packs. This is a large generated output and is not
committed:

```bash
python scripts/build_data_packs.py
```

Run the adapter mode locally:

```bash
python scripts/frontend_server.py --port 4173
```

Then open <http://127.0.0.1:4173/>.

To serve static mode with any static file server, point it at `frontend/` after
building the packs. For example:

```bash
python -m http.server 8000 --directory frontend
```

Open <http://127.0.0.1:8000/>. Static mode requires the generated
`frontend/data/packs/` directory unless you are using the published site or a
configured Tier-2 origin.

## Verification commands

The main browser-engine checks are plain Node scripts and require no npm
installation:

```bash
node frontend/engine/selftest.mjs
node frontend/engine/parity/parity.mjs
node frontend/engine/property/property.mjs
node frontend/engine/worker-selftest.mjs
```

After building data packs, run the pack integration checks:

```bash
node frontend/engine/dca-packs-integration.mjs
node frontend/engine/portfolio-packs-integration.mjs
```

Run static asset and path checks:

```bash
python scripts/check_static_site.py
```

The latest local verification baseline includes 218 Python tests, 27/27 parity
fixtures, 68/68 engine self-tests, 90/90 worker checks, 19 property groups
covering 1,473 cases, and passing DCA and portfolio pack integrations after a
pack build.

## Repository guide

- Python engine: [`src/sg_investing/`](src/sg_investing/)
- Browser engine and worker protocol: [`frontend/engine/`](frontend/engine/)
- Static application: [`frontend/`](frontend/)
- Canonical configuration: [`config/`](config/)
- Data-pack schema: [`docs/data-pack-schema.md`](docs/data-pack-schema.md)
- Data-pack budgets: [`docs/data-pack-budgets.md`](docs/data-pack-budgets.md)
- Data update runbook: [`docs/data-updates.md`](docs/data-updates.md)
- Deployment runbook: [`docs/deployment.md`](docs/deployment.md)
- FX sources and staleness: [`docs/fx-sources.md`](docs/fx-sources.md)
- DCA static workflow: [`docs/dca-static.md`](docs/dca-static.md)
- Portfolio static workflow: [`docs/portfolio-static.md`](docs/portfolio-static.md)
- Parity report: [`docs/parity-report.md`](docs/parity-report.md)
- Architecture decisions: [`docs/adr/`](docs/adr/)
- Roadmap and sprint files: [`TODO.md`](TODO.md) and [`Todo/`](Todo/)
