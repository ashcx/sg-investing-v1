# SG Investing

A backend financial analytics engine and read-only web UI for Singapore-based
investors. The frontend keeps all financial calculations in the Python engine;
it consumes the same JSON contracts through a local adapter or published data
artifacts.

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

## Setup and tests

The deployment target is Python 3.11 or newer.

```bash
python -m pip install -e ".[dev,market-data]"
python -m pytest
```

The normal test suite makes no live network calls. Provider and integration
tests use fake responses and temporary stores. The optional full-universe smoke
tests run only when explicitly enabled:

```bash
python -m pytest -m provider
python -m pytest -m integration
SG_INVESTING_RUN_UNIVERSE_SMOKE=1 python -m pytest tests/smoke
```

To preview the frontend against the current local data:

```bash
python scripts/build_frontend_data.py
python scripts/frontend_server.py --port 4173
# open http://127.0.0.1:4173/ in Chrome
```

`build_frontend_data.py` publishes the catalog, coverage/status envelope and
representative analysis, DCA, comparison and portfolio artifacts. The adapter
serves dynamic backend results without moving calculation logic into the
browser.

## GitHub Pages deployment

The checked-in `frontend/` directory is a static site and is published by
`.github/workflows/pages.yml` when changes reach the repository's `main` branch.
Enable GitHub Pages in the repository settings with **GitHub Actions** as the
source. The workflow uploads `frontend/` directly, so no Node.js build step is
required.

The site works on Pages as a static replay using the checked-in catalog and
representative artifacts. GitHub Pages cannot run the Python adapter, so
arbitrary analysis, DCA, comparison and portfolio requests require a separately
hosted adapter. Set the `sg-invest-api-base` meta tag in `frontend/index.html`
to that HTTPS API origin when one is available; leave it empty for static-only
mode. The frontend uses relative API paths by default, which also works when a
repository is served below a project subpath.

The calculation architecture for removing the runtime adapter dependency is
decided in `docs/adr/0001-calculation-architecture.md`: a browser-native
ES-module engine (vendored decimal arithmetic, Web Workers, no build step),
ported from and parity-tested against the Python engine. The work is tracked
as sprints in [`TODO.md`](TODO.md) and the `Todo/` folder.

The remaining work for a fully self-contained Pages deployment is tracked in
[`TODO.md`](TODO.md), including browser-side DCA and portfolio reconstruction,
static data-pack publishing and parity testing against the Python engine.

The smoke tests validate downloaded Parquet data and attempt analysis for
securities with sufficient price and FX coverage. A scheduled workflow can run
`python scripts/update_data.py` to update configured securities. It produces a
JSON summary and does not commit data automatically.

## Python API

```python
from datetime import date
from decimal import Decimal

from sg_investing.analysis import analyze_security
from sg_investing.models import AnalysisScenario

result = analyze_security(
    security=security,
    prices=price_rows,
    fx_rates=fx_rows,
    start_date=date(2024, 1, 1),
    end_date=date(2025, 1, 1),
    initial_sgd=Decimal("10000"),
    scenario=AnalysisScenario(
        dividends_enabled=True,
        reinvest_dividends=True,
        withholding_tax_enabled=True,
    ),
    dividends=dividend_rows,
    corporate_actions=action_rows,
    tax_rules=tax_rules,
)

frontend_payload = result.model_dump(mode="json")
```

When the configured data store has been refreshed, the application-facing API
loads the catalog, tax rules, and Parquet datasets for you:

```python
from sg_investing import SGInvestingEngine

engine = SGInvestingEngine(".")
payload = engine.analyze(
    ticker="QQQ",
    start_date=date(2024, 1, 2),
    end_date=date(2025, 1, 2),
    initial_sgd="10000",
).model_dump(mode="json")
```

For recurring investments, use `sg_investing.calculations.dca.dca_analysis`.
For transaction-ledger analytics, use
`sg_investing.calculations.portfolio.analyze_portfolio`.

## Data layout

```text
data/
  prices/market=US/year=2026.parquet
  manifests/prices/market=US/year=2026.json
  update_summary.json
```

Parquet data is partitioned by market and year. Each upsert merges by
`(security_id, trading_date)` and replaces a partition atomically only after
validation.

## Universe policy

`config/universe.yaml` contains the initial global ETF records, including the
unambiguous USD/SIX listing for VALL (`VALL.SW` on Yahoo Finance, ISIN
`IE000VAHT5T0`). It also
defines the policy for adding current SGX equities, REITs, business trusts, and
ETFs from a reviewed SGX directory snapshot. Structured products are excluded
unless explicitly added.

The data horizon starts on 2000-01-01; securities begin only at their actual
available listing history.

## Current limitations

- The current SGX listing-source adapter and the broad S&P 500, Nasdaq-100, and
  Russell constituent importers still need to be wired to reviewed source
  exports before a full-universe live load. The catalog and ingestion contracts
  are already in place for them.
- Yahoo Finance is an initial data provider and live smoke tests are intentionally
  separate from deterministic financial tests.
- V1 supports dividends denominated in the security currency. Cross-currency
  fund distributions are rejected rather than silently converted.
