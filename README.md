# SG Investing

**Live site: [sg-investing-v1](https://ashcx.github.io/sg-investing-v1/)** —
everything below runs there, in your browser, with no backend.

> **⚠ Status: very, very early preview (v0.1.0).** This project is under
> active development and **lots of features do not work yet**. Expect rough
> edges, missing securities, changing contracts and occasional deployment
> churn. See "What works / What does not work yet" below, and the sprint
> roadmap in [`TODO.md`](TODO.md).

SG / Invest is a calm, auditable return lens for Singapore-based investors:
pick a security and see its historical performance in the security's native
currency **and** in SGD, with FX, dividends and investor-level withholding tax
handled explicitly. Replay a dollar-cost-averaging plan, reconstruct a
portfolio from a transaction ledger, compare securities, and export the raw
result JSON — all computed locally, parity-tested against the authoritative
Python engine.

## What works (verified)

- The Python engine and its test battery: unit suite, golden parity fixtures
  against the browser engine, property tests, worker self-tests.
- The deployed static site: catalog browsing and local in-browser analysis,
  DCA, comparison and portfolio reconstruction for securities in the published
  Tier-1 pack set (currently 1,242 securities — every catalog universe except
  Russell 2000), with zero backend calls.
- CI: backend tests on push, static-site checks, and gated publishing of
  frontend + data packs.

## What does not work yet

- **Russell 2000 constituents (1,946 securities) are not available** on the
  site — the full pack set (1.79 GB) exceeds the GitHub Pages cap; a Tier-2
  origin (object storage or self-hosted) is pending (Sprint 8).
- Requests the pack manifest marks `incomplete` or `unavailable` (for example
  pre-2003 USD history, which lacks FX coverage) return explicit "unavailable"
  states rather than results — by design, but it means many securities/ranges
  cannot be analysed yet. (Sprint 7.5 backfills FX to 2000.)
- **Live data refresh is not wired**: packs are built from the committed LFS
  snapshot and go stale between manual snapshot updates. (Sprint 7.5 adds
  incremental date-range updates.)
- Charts and results currently require pressing "Run historical replay";
  staged auto-loading is planned (Sprint 7.5).
- V1 models **no brokerage, sale, FX-conversion or slippage costs**, performs
  **no Singapore capital-gains tax calculation**, and rejects cross-currency
  dividends rather than converting them.
- The SGX listing-source adapter and broad index importers are not yet wired,
  so the catalog grows only through reviewed manual additions.
- Mobile/accessibility polish is minimal and QA is headless-Chromium only.

## System design in one minute

1. **Python reference engine** (`src/sg_investing/`) — the authoritative,
   deterministic, decimal-safe financial math. Canonical prices, FX and
   dividends live as partitioned Parquet in Git LFS; the storage layer upserts
   atomically and never lets bad data replace good data.
2. **CI data publishing** — every deploy re-validates the snapshot with the
   test suite, builds versioned JSON data packs (one per security per year,
   with provenance and support manifests), prunes them to the publishable tier
   (~750 MB) and deploys them together with the app to GitHub Pages.
3. **Browser engine** (`frontend/`) — a decimal-safe JavaScript port of the
   Python engine runs inside a Web Worker, lazily loads only the packs a
   request needs, and must reproduce the Python results exactly. That last
   claim is enforced, not assumed: golden parity fixtures and property tests
   run in CI.

Architecture decisions live in `docs/adr/`, the full roadmap in
[`TODO.md`](TODO.md) and `Todo/`.

## Two computation modes

- **Static mode** (default — what the live site runs): the browser computes
  everything from published data packs. Works offline after first load, needs
  no servers, and never sends your requests anywhere.
- **Adapter mode** (development/reference): `scripts/frontend_server.py`
  serves the same UI with `/api` routes backed directly by the Python engine.
  Point the `sg-invest-api-base` meta tag at a hosted adapter to switch the
  site to server-side compute.

**Is keeping both truly necessary?** Strictly, no — the live site never calls
the adapter. It stays for two cheap reasons: it is the developer's *oracle*
(one command to compare a browser-computed result against the authoritative
Python result for the same request), and it is a ready fallback if the pack
pipeline is ever broken. It can be deleted without touching the live site;
the Python engine itself stays regardless, as the CI reference.

## What is implemented

- Daily unadjusted OHLCV contracts and a provider boundary (Yahoo Finance is the
  initial adapter).
- Atomic, partitioned Parquet price storage with manifests and incremental
  reconciliation. Invalid data and provider errors cannot replace valid data.
- Deterministic single-investment return analysis in SGD, including FX,
  dividends, investor-level withholding tax, cash dividends, pay-date dividend
  reinvestment, fractional shares, splits, and CAGR.
- DCA analysis using the first available trading day of each monthly, quarterly,
  or yearly period and XIRR.
- Transaction-ledger portfolio reconstruction using weighted-average cost basis.
- Configured major ETFs and an auditable catalog that can be augmented with a
  current SGX listing snapshot.
- Dual-currency result contracts: a security's native-currency results sit
  alongside the SGD results, so a future interface can switch presentation
  without reproducing financial calculations.
- `frontend/` contains the responsive SG / Invest application for catalog
  discovery, historical replay, native/SGD display switching, comparisons, DCA
  replays, portfolio reconstruction, series charts, warnings and JSON export.
- `scripts/frontend_server.py` exposes read-only `/api/catalog`, `/api/status`,
  `/api/analyze`, `/api/series`, `/api/compare`, `/api/dca` and
  `/api/portfolio` routes over the canonical Parquet data.

## Financial methodology

- Prices are daily local-exchange closes. A purchase resolves to the next
  trading day; valuation resolves to the previous one.
- FX means **one unit of the foreign currency equals X SGD**. For example,
  US$100 × 1.35 = S$135.
- Distributing-fund dividends are modeled separately from price data. If their
  pay date is absent, the engine uses ex-date + 30 calendar days and then the
  next trading day, recording a warning in the result.
- A dividend record whose pay date precedes its ex-date is rejected during
  analysis rather than being used to create an economically impossible cash
  flow.
- Accumulating ETFs never receive invented investor dividend cash.
- The V1 engine models no brokerage, sale, FX-conversion, or slippage costs.
  Output is mark-to-market at the valuation date.
- ETF TER is stored as metadata only. It is **not subtracted** from observed
  historical ETF performance because it is generally already reflected in NAV.
- Portfolio realized/unrealized P&L uses weighted-average cost basis. This is a
  reporting convention and not a Singapore capital-gains tax calculation.
- For a foreign security, result fields suffixed `foreign_currency` are in the
  security's native currency (USD for a US asset). `*_sgd_at_payment` dividend
  fields translate dividends included in the ending value at their resolved
  payment-date FX rate; end-value and return fields use the valuation-date FX
  rate where applicable.

## Running locally

```bash
python -m pip install -e ".[dev,market-data]"
python -m pytest                      # full suite, no live network calls
python scripts/build_data_packs.py    # build browser data packs from data/
python scripts/frontend_server.py --port 4173   # adapter mode, http://127.0.0.1:4173/
```

Any static file server pointed at `frontend/` runs static mode (packs land in
`frontend/data/packs/` after a build).

## Pointers

- Deployment runbook: `docs/deployment.md`
- Data-pack schema and budgets: `docs/data-pack-schema.md`,
  `docs/data-pack-budgets.md`
- Architecture decisions: `docs/adr/`
- Universe catalog policy: `config/universe.yaml`
- Sprint roadmap: [`TODO.md`](TODO.md) and `Todo/`