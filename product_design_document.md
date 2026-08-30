# SG Investing V1
## Backend / Financial Analytics Engine — Complete Product Design & Build Specification

**Repository:** `sg-investing-v1`

**Implementation target:** Python backend/data-engineering system only.

**Important:** Do NOT build the frontend in this phase.

---

# 1. Executive objective

Build a production-quality, testable financial data and analytics engine specifically designed for investors in Singapore.

The system must collect and maintain historical market data for a curated universe of securities and provide a deterministic calculation engine capable of answering:

> "What would my investment have actually returned in SGD, after dividends, applicable dividend withholding tax, and FX movement?"

The system must support both:

1. **Observed historical investment performance**
2. **Hypothetical investment scenarios**

The backend must be independent of any frontend framework.

A future frontend will consume this engine through Python APIs, generated JSON, or eventually a thin HTTP API.

---

# 2. Absolute scope restriction

## DO NOT build

- Astro
- React
- Vue
- HTML frontend
- CSS
- frontend charts
- IndexedDB
- browser state
- GitHub Pages application
- command-line interface
- authentication
- Supabase
- FastAPI server
- VPS
- Docker infrastructure unless genuinely required for development/testing

This phase is **backend/data/analytics only**. A future GitHub Pages frontend must
be able to consume the package's stable Python API and JSON-serializable output,
but no frontend or HTTP server is part of this phase.

The output should be a clean Python package that can run locally and through GitHub Actions.

---

# 3. Core architecture

Use:

```text
External market-data sources
          │
          ▼
   Provider abstraction
          │
          ▼
     Normalization
          │
          ▼
   Data validation / QA
          │
          ▼
      Parquet store
          │
          ├───────────────┐
          ▼               ▼
   Historical data     Metadata
          │
          └───────┬───────┘
                  ▼
        Financial calculation
               engine
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
       Python API   JSON artifacts
```

Primary technologies:

- Python 3.11+
- Polars
- PyArrow
- DuckDB
- Pydantic
- Typer
- pytest
- yfinance initially
- standard-library logging

Use pandas only where an external library requires it.

---

# 4. Core design principle

The system is NOT merely a Yahoo Finance downloader.

It is a:

> **Singapore-investor financial analytics engine**

The fundamental model is:

```text
Security
+
Historical market prices
+
Dividend events
+
Corporate actions
+
FX
+
Tax rules
+
Investor assumptions
+
Transaction assumptions
=
Investment analysis
```

Every major assumption must be:

- explicit
- deterministic
- configurable where appropriate
- testable
- documented

---

# 5. Security universe

The initial universe must be significantly broader than a small manually selected watchlist.

It must include the following categories.

---

## 5.1 S&P 500

Include all current S&P 500 constituents.

Represent index membership separately from the security itself.

Example:

```text
AAPL
```

can have:

```text
S&P 500 membership = true
```

but membership must be represented through a dated constituent table.

---

# 5.2 Nasdaq-100 / QQQ

Include:

- QQQ itself
- all Nasdaq-100 constituents

QQQ and the individual constituent securities are separate securities.

---

# 5.3 VALL

Include the following explicitly identified security:

```text
ticker: VALL
name: Vanguard FTSE Global All-Cap UCITS ETF USD Acc
ISIN: IE000VAHT5T0
domicile: Ireland
distribution_policy: accumulating
launch: August 2026
primary_provider_listing: VALL.SW (Yahoo Finance / SIX Swiss Exchange, USD)
expense_ratio_metadata: 0.07% p.a.
```

The provider-specific exchange ticker must be verified before ingestion and
stored alongside the ISIN. Do not identify a security solely by ticker where
ambiguity exists.

---

# 5.4 Russell 2000

Support:

- Russell 2000 index/benchmark where data is available
- Russell 2000 constituent equities where a reliable constituent source is available

Do not confuse:

- Russell 2000 index
- Russell 2000 ETF
- Russell 2000 constituents

They are separate instruments.

If complete constituent data cannot be obtained legally/reliably from the selected data source, document the limitation.

Never fabricate constituent membership.

---

# 5.5 Semiconductor ETFs

Include:

- SMH
- SOXX

Support constituent universes if reliable constituent data can be obtained.

---

# 5.6 Singapore securities and ETFs

Include all active SGX-listed:

- equities
- REITs
- business trusts

Also include all active SGX-listed ETFs and the configurable major global ETF
set. The initial global set includes QQQ, SMH, SOXX, and VALL; additional ETFs
may be added through configuration. Exclude structured products unless added
manually.

Preserve STI and other available Singapore index memberships as useful views
over this broader SGX universe. The architecture must allow multiple index
memberships, but V1 does not require historical constituent reconstruction.

---

# 5.7 Manual additions

The configuration and Python API must allow arbitrary securities to be added
manually. Manual securities remain in the universe even if they are not members
of an automatic universe.

---

# 6. Universe architecture

A security can belong to multiple universes.

Example:

```text
NVDA
├── S&P 500
├── Nasdaq-100
└── SMH
```

Create a universe-membership data structure:

```text
index/universe
security_id
effective_from
effective_to
source
```

Membership must be date-aware.

This is important for avoiding survivorship bias.

For example, the system must eventually be capable of distinguishing:

> Current S&P 500 constituents

from:

> S&P 500 constituents as of 2018.

---

# 7. Security master

Create a security master containing:

```text
security_id
ticker
exchange
market
name
ISIN
CUSIP where available
asset_type
currency
country/domicile
timezone
active
```

Supported asset types:

```text
equity
ETF
index
REIT
other
```

Ticker must NOT be the global primary key.

---

# 8. Daily market data

Canonical resolution:

**Daily OHLCV**

Store:

```text
security_id
ticker
trading_date
open
high
low
close
volume
currency
exchange
timezone
source
retrieved_at
```

Use unadjusted prices as the canonical market-price representation.

Do not rely solely on provider `adjusted_close`.

Initial historical coverage begins on 2000-01-01. A security begins on its
actual earliest available trading date (normally its IPO/listing date); the
pipeline must not fabricate pre-listing history.

---

# 9. Why OHLCV rather than only close

Return calculations will primarily use closing prices, but preserve:

- open
- high
- low
- close
- volume

because future functionality may require:

- volatility
- maximum drawdown
- rolling returns
- technical indicators
- historical charting
- execution/slippage modeling

---

# 10. Daily price convention

A daily record represents the security's local-market trading day.

Do NOT interpret:

> "daily price"

as:

> "price at a particular Singapore time."

For a US security, its daily close is the official/local US market close.

Store exchange timezone metadata.

---

# 11. Default valuation price

For historical investment calculations:

**Use the daily closing price by default.**

For example:

```text
investment date
    ↓
first valid trading close
```

and:

```text
valuation date
    ↓
last valid trading close
```

If a requested date is not a trading day, use a deterministic documented convention.

Default:

- purchase → next available trading day
- valuation → previous available trading day

Make this behavior configurable at the calculation layer.

---

# 12. No intraday data in V1

Do not collect:

- tick data
- 1-minute
- 5-minute
- 15-minute
- hourly

V1 uses daily data.

Design abstractions so intraday can theoretically be added later.

---

# 13. Dividend data

Dividends must be represented independently from prices.

Schema:

```text
security_id
ticker
ex_date
record_date
pay_date
amount
currency
dividend_type
source
retrieved_at
```

At minimum:

- ticker/security
- ex-date
- amount

must be known.

Pay date and record date may be null if unavailable.

Deduplicate dividend events.

Do not create duplicate dividends every time the update pipeline executes.

---

# 14. Corporate actions

Support at minimum:

- stock splits
- reverse splits

Schema:

```text
security_id
effective_date
action_type
ratio
source
retrieved_at
```

Future architecture should permit:

- ticker changes
- mergers
- spin-offs
- special distributions
- delistings

Do not build a highly complex corporate-action engine unless required for correctness.

---

# 15. FX data

FX is a first-class dataset.

Initially support:

```text
USD/SGD
GBP/SGD
EUR/SGD
JPY/SGD
HKD/SGD
AUD/SGD
```

Add others when needed by the universe.

Use one explicit convention.

Preferred convention:

```text
1 unit foreign currency = X SGD
```

Example:

```text
USD/SGD = 1.35
```

means:

```text
US$1 = S$1.35
```

Unit-test FX direction aggressively.

---

# 16. FX calculation

For foreign assets:

```text
foreign value × foreign/SGD rate
=
SGD value
```

Example:

```text
US$10,000 × 1.35
=
S$13,500
```

Do not accidentally invert FX.

---

# 17. Tax architecture

Create:

```text
config/tax_rules.yaml
```

Tax rules must be:

- security-aware where necessary
- country-aware
- investor-type aware
- income-type aware
- effective-date aware

Do not hard-code tax rates into calculation functions.

Example:

```yaml
rules:

  - rule_id: US_DIVIDEND_NONRESIDENT
    source_country: US
    income_type: dividend
    investor_type: singapore_individual
    rate: 0.30
    effective_from: 1900-01-01
    effective_to: null
```

The exact tax rule must be verified from appropriate sources before being included.

---

# 18. Tax layers

Keep these concepts separate:

```text
investor-level dividend withholding
fund-level tax drag
local investor taxation
```

Do NOT assume they are the same thing.

The V1 user-facing return engine should model **investor-level dividend withholding** where the applicable rule is known.

Fund-level tax drag should be represented as metadata/research information rather than artificially deducted from historical ETF prices.

---

# 19. Expense ratio — IMPORTANT

Do NOT create a user-selectable TER/expense-ratio deduction.

This is intentional.

For observed ETF performance, fund expenses are generally already reflected in the fund's NAV/performance over time.

Therefore:

**Do not subtract an ETF's TER from observed historical ETF returns.**

Doing so would risk double-counting expenses.

---

# 20. Expense ratio metadata

TER should still be collected as ETF metadata.

Store:

```text
expense_ratio
expense_ratio_type
effective_date
source
```

This is useful for displaying/comparing ETFs.

But it is NOT an adjustable deduction in the historical return engine.

The system should explicitly document:

> TER is metadata and generally embedded in observed ETF/fund performance. It is not deducted again from historical observed returns.

---

# 21. Price return

Price return excludes dividends.

For a security:

```text
ending_price / starting_price - 1
```

This should be available in both:

- security currency
- SGD

---

# 22. Gross dividend return

Support theoretical gross dividend calculations.

If withholding is disabled:

```text
gross dividend
=
net dividend for the modeled scenario
```

This allows users to compare:

> gross total return

against:

> Singapore-investor net return.

---

# 23. Dividend withholding toggle

Withholding tax is independently configurable.

Example:

```json
{
  "withholding_tax": {
    "enabled": true
  }
}
```

If disabled:

```text
net dividend = gross dividend
```

for the model.

If enabled:

```text
net dividend =
gross dividend × (1 - applicable withholding rate)
```

Do not hard-code a single universal rate.

---

# 24. Dividend toggle

Users must be able to turn dividends on/off.

### Dividends OFF

Produces:

> price return

### Dividends ON

Produces:

> total return

This must be independent of withholding tax.

Therefore:

```text
Dividends ON
Withholding OFF
```

means gross dividends.

And:

```text
Dividends ON
Withholding ON
```

means net dividends under the configured investor tax rules.

---

# 25. Dividend reinvestment toggle

Support:

```text
reinvest = true
```

and:

```text
reinvest = false
```

### Reinvestment OFF

Dividends accumulate as cash.

### Reinvestment ON

Dividends are used to acquire additional shares.

Fractional shares are allowed.

---

# 26. Reinvestment convention

Default V1 convention:

1. Dividend becomes available on `pay_date`.
2. Applicable withholding tax is deducted.
3. Net dividend is converted to the security's currency where necessary.
4. Net dividend is reinvested at the closing price on the pay date.
5. If pay date is not a trading day, use the next trading day.
6. Fractional shares are permitted.
7. Brokerage/fees are zero unless explicitly enabled.

This is a modeling convention.

Document that it does not necessarily reproduce a broker's actual DRIP execution.

When a provider does not supply a pay date, approximate it as 30 calendar days
after the ex-date, then move it to the next local trading day. Surface this
approximation in the result warnings and methodology metadata.

---

# 27. Cash dividend mode

When reinvestment is disabled, output:

```text
final_security_value
gross_dividends
withholding_tax
net_dividend_cash
final_total_value
```

where:

```text
final_total_value =
security value + dividend cash
```

---

# 28. Accumulating ETFs

Represent ETF distribution policy:

```text
accumulating
distributing
unknown
```

For accumulating ETFs:

- do not invent investor dividend events
- do not assume the investor receives cash
- do not apply investor-level dividend withholding to a fictional distribution
- rely on observed market/NAV performance for the investment return
- retain tax/domicile metadata for informational purposes

Do not attempt to reverse-engineer internal fund withholding tax from price history.

---

# 29. Transaction costs — deferred

Brokerage, exchange, platform, clearing, FX-conversion, and slippage costs are
out of scope for V1. The engine reports mark-to-market investment values and
does not assume a sale on the end date. The models should leave a clear
extension point for transaction costs, but calculations must not include them
in V1.

---

# 33. Return scenario configuration

Every analysis should accept a scenario object.

Example:

```json
{
  "dividends": {
    "enabled": true,
    "reinvest": true
  },

  "withholding_tax": {
    "enabled": true
  }
}
```

Do NOT include:

```text
expense_ratio.enabled
```

TER is not a user-selectable deduction.

---

# 34. Scenario presets

Support useful presets.

### Price only

```text
dividends = OFF
```

### Gross total return

```text
dividends = ON
withholding = OFF
reinvestment = ON
```

### Singapore investor return

```text
dividends = ON
withholding = ON
reinvestment = ON
```

### Singapore investor cash-dividend return

```text
dividends = ON
withholding = ON
reinvestment = OFF
```

Transaction costs are deferred from V1.

---

# 35. Observed vs modeled return

The engine must distinguish:

### Observed historical return

Based on actual observed market prices/distributions.

### Modeled investor return

Observed data plus explicitly modeled assumptions such as:

- dividend withholding

This distinction must be reflected in output metadata.

---

# 36. Return output

A security analysis should return structured data similar to:

```json
{
  "security": {
    "ticker": "VOO",
    "name": "Vanguard S&P 500 ETF",
    "currency": "USD",
    "asset_type": "ETF"
  },

  "period": {
    "start_date": "2015-01-02",
    "end_date": "2026-08-28"
  },

  "initial_investment": {
    "amount": 10000,
    "currency": "SGD",
    "foreign_currency_amount": 7407.41
  },

  "price_return": {
    "foreign_currency": 0.0,
    "sgd": 0.0
  },

  "dividends": {
    "gross": 0.0,
    "withholding_tax": 0.0,
    "net": 0.0,
    "gross_sgd_at_payment": 0.0,
    "withholding_tax_sgd_at_payment": 0.0,
    "net_sgd_at_payment": 0.0
  },

  "investment": {
    "shares": 0.0,
    "final_security_value": 0.0,
    "dividend_cash": 0.0,
    "final_value_foreign_currency": 0.0,
    "final_value_sgd": 0.0
  },

  "returns": {
    "total_return": 0.0,
    "cagr": 0.0,
    "total_return_foreign_currency": 0.0,
    "cagr_foreign_currency": 0.0
  },

  "fx": {
    "start_rate": 0.0,
    "end_rate": 0.0
  },

  "methodology": {
    "dividend_reinvestment": "pay_date_close",
    "withholding_tax_enabled": true,
    "ter_deducted": false
  },

  "data_quality": {
    "status": "OK",
    "warnings": []
  }
}
```

Do not round internal calculations.

Round only at output/presentation boundaries.

For a future currency-mode switcher, expose both native-security-currency and
SGD values in a single result. For a US security, `foreign_currency` means USD.
The existing unqualified `total_return` and `cagr` remain SGD-based; their
`*_foreign_currency` counterparts are native-currency returns. Dividend SGD
amounts are informational cash-flow translations using the resolved payment
date's FX rate, while final-value and SGD-return calculations use the
valuation-date FX rate.

---

# 37. CAGR

Use:

```text
CAGR =
(ending_value / starting_value) ^ (1 / years) - 1
```

Use a consistent elapsed-time convention.

Document it.

Test:

- one year
- multi-year
- less than one year
- zero return
- negative return

---

# 38. DCA

Support recurring investments.

Inputs:

```text
ticker
start_date
end_date
contribution_amount
contribution_currency
frequency
```

V1 frequencies:

- monthly
- quarterly
- yearly

Default convention:

> contribution occurs on the first available trading day of the period.

Each contribution:

```text
SGD contribution
      ↓
FX conversion if required
      ↓
transaction cost if enabled
      ↓
shares purchased
```

Fractional shares are permitted.

---

# 39. DCA return methodology

Do not use ordinary CAGR as the primary annualized return metric for a multi-contribution strategy.

Expose:

- total contributed
- final value
- gain/loss
- XIRR / money-weighted return

CAGR may be shown only where mathematically appropriate.

---

# 40. Portfolio ledger

Build a transaction-based portfolio engine.

Transaction schema:

```text
date
security_id
transaction_type
quantity
cash_amount
currency
fees
```

Supported transaction types:

```text
BUY
SELL
DIVIDEND
CASH_DEPOSIT
CASH_WITHDRAWAL
```

The system must be capable of reconstructing portfolio holdings from the transaction ledger.

Do not model a portfolio merely as current weights.

---

# 41. Portfolio analytics

Support:

- current holdings
- cost basis
- market value
- realized P/L where possible
- unrealized P/L
- dividends
- fees
- cash
- total portfolio value
- time-weighted return where appropriate
- money-weighted return/XIRR where appropriate

Use weighted-average cost basis for realized and unrealized P/L in V1. This is
a performance-reporting convention, not a Singapore capital-gains tax method.
Do not overbuild tax-lot accounting in V1.

---

# 42. Data storage

Use Parquet as the canonical historical data format.

Recommended structure:

```text
data/
  prices/
    market=US/
      year=2025.parquet
      year=2026.parquet

    market=SG/
      year=2025.parquet
      year=2026.parquet

  dividends/
    year=2025.parquet
    year=2026.parquet

  corporate_actions/
    year=2025.parquet
    year=2026.parquet

  fx/
    pair=USD_SGD/
      year=2025.parquet
      year=2026.parquet

  metadata/
    securities.parquet
    index_memberships.parquet
    etfs.parquet
```

Choose partitioning pragmatically.

Avoid one enormous monolithic file.

---

# 43. Incremental updates

The pipeline must be incremental.

Do NOT redownload the entire history every day.

Determine:

```text
latest_valid_stored_date
```

and fetch the missing period.

However, periodically reconcile recent historical data because providers can revise:

- prices
- dividends
- corporate actions

Recommended:

### Daily

Fetch recent/new observations.

### Recent reconciliation

Recheck a configurable recent window.

### Full rebuild

Provide:

```bash
sg-investing data rebuild
```

---

# 44. Data update safety

A failed update must never destroy valid existing data.

Use:

```text
temporary dataset
       ↓
validation
       ↓
atomic replacement
```

where practical.

Never replace good data with a partially downloaded or invalid dataset.

---

# 45. Provider abstraction

The calculation engine must not directly depend on yfinance.

Create a provider interface such as:

```python
class MarketDataProvider(Protocol):
    def get_prices(...): ...
    def get_dividends(...): ...
    def get_corporate_actions(...): ...
    def get_metadata(...): ...
```

Implement Yahoo/yfinance initially.

This allows future providers to be substituted.

---

# 46. API failures

The ingestion system must tolerate:

- timeouts
- rate limits
- missing tickers
- malformed responses
- temporary provider outages

One failed security must not automatically invalidate the entire update.

Produce per-security status.

Example:

```text
497 successful
2 temporary failures
1 invalid response
```

---

# 47. Rate limiting

Use:

- bounded concurrency
- retries
- exponential backoff
- timeouts
- request caching

Do not aggressively hammer free data providers.

---

# 48. Data validation

Validate:

### Prices

- dates valid
- no duplicate `(security_id, date)`
- prices positive where appropriate
- OHLC relationships sensible
- volume non-negative

### Dividends

- amount non-negative
- valid ex-date
- duplicates removed

### Corporate actions

- valid ratios
- valid dates

### FX

- positive rates
- correct currency pair
- no inverted convention

---

# 49. Suspicious data

Do not silently delete suspicious observations.

Flag them.

Examples:

```text
10,000% one-day price movement
missing historical period
duplicate dividend
unexpected zero price
large unexplained volume anomaly
```

Return:

```text
OK
WARNING
INCOMPLETE
FAILED
```

---

# 50. Data manifests

Every dataset should have a manifest.

Example:

```json
{
  "dataset": "prices",
  "security": "VOO",
  "source": "yahoo_finance",
  "retrieved_at": "2026-08-30T00:00:00Z",
  "first_date": "2010-09-09",
  "last_date": "2026-08-28",
  "row_count": 4000,
  "pipeline_version": "0.1.0"
}
```

This makes data discrepancies auditable.

---

# 51. Data provenance

Preserve:

- source
- retrieval timestamp
- provider
- pipeline version
- relevant transformation version

The calculation engine should be able to report which dataset it used.

---

# 52. Execution interface

Do not build a CLI in V1. Provide importable Python entry points that can be
run from a script, notebook, test suite, or future thin frontend adapter.
Public results must be JSON-serializable so a GitHub Pages frontend can consume
generated JSON without reproducing any financial calculations.

---

# 53. Python API

Expose clean Python functions.

Example:

```python
result = analyze_security(
    ticker="VOO",
    start_date="2015-01-01",
    end_date="2026-08-30",
    initial_sgd=10_000,
    scenario=Scenario(
        dividends=True,
        reinvest_dividends=True,
        withholding_tax=True,
    ),
)
```

Also support:

```python
compare_securities(...)
dca_analysis(...)
portfolio_analysis(...)
```

The frontend should eventually be able to consume these without duplicating financial logic.

---

# 54. Calculation scenario immutability

A calculation should be reproducible from:

```text
security
+
date range
+
initial capital
+
scenario
+
tax rules
+
data snapshot
+
methodology version
```

Include:

```text
methodology_version
```

in every result.

---

# 55. Scenario comparison

Support multiple scenarios against the same security.

Example:

```text
VOO

Scenario A
Dividends OFF
Withholding OFF

Scenario B
Dividends ON
Withholding OFF
Reinvestment ON

Scenario C
Dividends ON
Withholding ON
Reinvestment ON

Scenario D (future extension)
Scenario C
+ explicit transaction costs
```

Return comparable structured results.

---

# 56. Return attribution

Where mathematically appropriate, expose:

```text
price return
dividend contribution
withholding-tax drag
FX effect

Transaction-cost attribution is deferred from V1.
```

Be careful with additive attribution.

Do not claim:

```text
price + dividends + FX = exact final return
```

unless the mathematical methodology actually supports it.

---

# 57. ETF metadata

Track:

```text
ticker
ISIN
name
issuer
domicile
exchange
currency
asset_type
distribution_policy
expense_ratio
benchmark
inception_date
```

TER is informational metadata only.

It must not be automatically deducted from observed historical returns.

---

# 58. Index metadata

Track:

```text
index_name
index_provider
constituents
effective dates
source
```

Index membership must be time-aware.

---

# 59. Survivorship bias

Do not design the system only around today's index constituents.

Where historical constituent data is available, preserve historical membership.

The system should eventually support:

```text
backtest universe as-of date
```

rather than automatically using today's winners.

---

# 60. Testing philosophy

Financial calculations require independent tests.

Do not test a function using the same calculation logic to generate the expected answer.

Create manually calculated synthetic fixtures.

---

# 61. Unit tests

Test:

- FX conversion
- FX direction
- CAGR
- price return
- dividend calculations
- withholding tax
- reinvestment
- fractional shares
- split handling
- date handling
- DCA
- XIRR
- portfolio ledger
- scenario configuration

---

# 62. Golden financial tests

Create synthetic securities with independently calculated expected results.

Example:

```text
Initial investment = S$10,000
Starting security price = US$100
Ending security price = US$110

Dividend = US$2
Withholding = 30%

Starting USD/SGD = 1.30
Ending USD/SGD = 1.40
```

Manually calculate expected outputs independently.

Test:

- gross dividends
- net dividends
- reinvestment
- FX
- final SGD value
- CAGR

These tests must catch:

- inverted FX
- gross/net dividend mistakes
- tax mistakes
- reinvestment mistakes

---

# 63. Edge cases

Test:

- zero dividends
- multiple dividends
- dividend on non-trading day
- missing pay date
- split during holding period
- reverse split
- missing FX date
- security listed after requested start date
- short holding period
- one-day holding period
- zero return
- negative return
- fractional shares
- invalid ticker
- missing tax rule
- accumulating ETF
- distributing ETF

---

# 64. Live-data tests

Core tests must NOT depend on live APIs.

Create separate optional smoke tests for live providers.

Provider changes must not break the deterministic calculation test suite.

---

# 65. GitHub Actions

Create:

```text
.github/workflows/test.yml
```

Run:

- dependency installation
- linting where configured
- type checks where configured
- unit tests
- integration tests

Create:

```text
.github/workflows/update-data.yml
```

for scheduled data updates.

The update workflow must:

1. checkout repository
2. install Python
3. install dependencies
4. run incremental update
5. validate changes
6. run relevant tests
7. generate update summary
8. make only validated data eligible for a future commit; no automatic commit
   is required in V1
9. fail safely if validation fails

---

# 66. No bad-data commits

If validation detects catastrophic problems:

```text
do not commit updated data
```

Examples:

- 95% of historical rows disappear
- dates become corrupted
- invalid Parquet
- massive unexplained security count reduction
- malformed schema
- serious duplicate explosion

Preserve the previous valid dataset.

---

# 67. Update summary

Every update should generate something like:

```text
SG Investing data update

Prices:
  497 updated
  2 unchanged
  1 failed

Dividends:
  13 new events
  0 duplicates

Corporate actions:
  2 new events

FX:
  6 pairs updated

Warnings:
  XYZ: missing dividend pay date

Overall:
  PASS
```

---

# 68. Configuration files

Create:

```text
config/
  universe.yaml
  tax_rules.yaml
  data_sources.yaml
  settings.yaml
```

Keep assumptions outside application logic whenever practical.

---

# 69. Repository structure

Use a structure approximately like:

```text
sg-investing-v1/
│
├── README.md
├── pyproject.toml
├── .gitignore
│
├── config/
│   ├── universe.yaml
│   ├── tax_rules.yaml
│   ├── data_sources.yaml
│   └── settings.yaml
│
├── src/
│   └── sg_investing/
│       ├── models/
│       ├── data/
│       │   ├── providers/
│       │   ├── ingestion.py
│       │   ├── normalization.py
│       │   ├── validation.py
│       │   ├── storage.py
│       │   └── manifest.py
│       │
│       ├── calculations/
│       │   ├── prices.py
│       │   ├── dividends.py
│       │   ├── withholding.py
│       │   ├── fx.py
│       │   ├── returns.py
│       │   ├── cagr.py
│       │   ├── dca.py
│       │   └── portfolio.py
│       │
│       ├── universe/
│       └── utils/
│
├── data/
│   ├── prices/
│   ├── dividends/
│   ├── corporate_actions/
│   ├── fx/
│   └── metadata/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── fixtures/
│   └── golden/
│
└── .github/
    └── workflows/
        ├── test.yml
        └── update-data.yml
```

You may improve the structure if there is a strong technical reason.

---

# 70. Documentation

README must explain:

- architecture
- installation
- Python API
- universe configuration
- data providers
- Parquet layout
- update pipeline
- tax methodology
- dividend methodology
- FX methodology
- return methodology
- transaction-cost extension point (not modeled in V1)
- TER treatment
- limitations
- testing
- GitHub Actions

Include worked examples.

---

# 71. Critical methodology documentation

The README must explicitly state:

### TER

> ETF expense ratios are treated as metadata and are not subtracted from observed historical ETF performance because fund expenses are generally reflected in fund NAV/performance.

### Dividend withholding

> Investor-level withholding tax is modeled separately from observed market prices and can be enabled or disabled.

### Dividend reinvestment

> Reinvestment uses the configured deterministic pay-date convention and allows fractional shares.

### FX

> Foreign-currency values are converted using the configured daily FX methodology.

### Transaction costs

> Brokerage, FX conversion costs, and slippage are deferred from V1. Results
> are mark-to-market and do not assume an end-date sale.

---

# 72. No hidden assumptions

Every result must identify material assumptions.

For example:

```json
{
  "methodology": {
    "price": "daily_close",
    "purchase_date_rule": "next_trading_day",
    "valuation_date_rule": "previous_trading_day",
    "dividend_reinvestment": "pay_date_close",
    "fractional_shares": true,
    "withholding_tax": true,
    "ter_deducted": false
  }
}
```

---

# 73. Future frontend contract

Although no frontend should be built, design all Python APIs and JSON outputs so that a future frontend can request:

```text
security analysis
comparison
DCA analysis
portfolio analysis
universe information
data-quality information
```

without implementing its own financial calculations.

---

# 74. No server requirement

The backend must work as a standalone Python engine.

It should not require a continuously running server.

It must be runnable through:

```text
Python API
GitHub Actions
```

A future HTTP API can be added as a thin layer around the existing engine.

Do not build that HTTP API now.

---

# 75. Completion criteria

Do not declare the project complete merely because it installs.

The following must work.

## Data

```text
[ ] initialize dataset
[ ] add security
[ ] update security
[ ] incremental update
[ ] recent reconciliation
[ ] full rebuild
[ ] validation
[ ] manifests
[ ] safe failure handling
```

## Universe

```text
[ ] S&P 500
[ ] Nasdaq-100
[ ] QQQ
[ ] Russell 2000 / feasible constituents
[ ] SMH
[ ] SOXX
[ ] STI
[ ] major Singapore index universes where feasible
[ ] all active SGX equities, REITs, business trusts, and SGX-listed ETFs
[ ] configured major global ETFs
[ ] manual securities
[ ] current membership with effective dates where available
```

## Analytics

```text
[ ] price return
[ ] gross dividend return
[ ] withholding tax
[ ] net dividend return
[ ] dividend reinvestment
[ ] cash dividends
[ ] SGD conversion
[ ] FX attribution
[ ] CAGR
[ ] DCA
[ ] XIRR
[ ] portfolio calculations
```

## ETF treatment

```text
[ ] expense ratio stored as metadata
[ ] TER NOT deducted from observed ETF historical returns
[ ] accumulating/distributing distinction
```

## Quality

```text
[ ] unit tests
[ ] integration tests
[ ] golden tests
[ ] edge-case tests
[ ] deterministic calculations
[ ] live provider isolated from core tests
```

## Automation

```text
[ ] GitHub Actions test workflow
[ ] scheduled update workflow
[ ] validated-data safety before any future commit
[ ] update summary
```

---

# 76. Required agent behavior

You are an autonomous coding agent.

Do not simply describe implementation steps.

Actually:

1. inspect the existing `sg-investing-v1` repository
2. determine what already exists
3. create/refactor the backend architecture
4. implement the data model
5. implement the provider layer
6. implement ingestion
7. implement validation
8. implement Parquet storage
9. implement the calculation engine
10. implement tax rules
11. implement dividend handling
12. implement FX handling
13. implement DCA
14. implement portfolio logic
15. expose documented Python entry points and JSON-serializable outputs
16. implement tests
17. implement GitHub Actions
18. run the tests
19. fix all failures
20. run end-to-end synthetic examples
21. inspect generated datasets
22. improve documentation
23. do not commit unless the user explicitly asks

Do not ask for confirmation for routine implementation decisions.

Do not build the frontend.

---

# 77. Financial correctness priority

When forced to choose between:

- implementation convenience
- performance
- financial correctness

choose:

**financial correctness.**

When uncertain about a financial methodology:

1. make the assumption explicit
2. make it configurable where appropriate
3. document it
4. write a test
5. do not silently invent a value

Never hide an assumption inside a calculation function.

---

# 78. Final self-review

Before declaring completion, verify:

```text
[ ] No frontend has been built
[ ] No unnecessary server has been introduced
[ ] Canonical data is Parquet
[ ] Raw/unadjusted prices are preserved
[ ] OHLCV is retained
[ ] Daily resolution is used
[ ] Exchange-local trading dates are respected
[ ] FX direction is unit-tested
[ ] Dividend events are separate from prices
[ ] Corporate actions are separate from prices
[ ] Dividend withholding is configurable
[ ] Dividend reinvestment is configurable
[ ] Cash-dividend mode works
[ ] Accumulating ETFs are handled correctly
[ ] TER is metadata only
[ ] TER is NOT deducted from observed ETF returns
[ ] Transaction costs are not modeled in V1
[ ] All assumptions are visible in output
[ ] Tax rules are configuration-driven
[ ] Tax rules support effective dates
[ ] S&P 500 universe works
[ ] Nasdaq-100 universe works
[ ] QQQ works
[ ] Russell 2000 universe works where feasible
[ ] SMH works
[ ] SOXX works
[ ] STI works
[ ] Singapore index universes work where feasible
[ ] all active SGX equities, REITs, business trusts, and SGX-listed ETFs are supported
[ ] configured major global ETFs exist
[ ] Manual additions work
[ ] Current memberships are stored with effective dates where available
[ ] Incremental updates work
[ ] Full rebuild works
[ ] Failed updates cannot corrupt valid data
[ ] Python API works
[ ] JSON output works
[ ] Golden financial tests pass
[ ] GitHub Actions test workflow works
[ ] GitHub Actions update workflow is valid
[ ] README is complete
```

---

# Final objective

The finished repository must be a robust, reusable:

**Singapore Investor Financial Analytics Engine**

capable of transforming:

```text
market data
+
dividends
+
corporate actions
+
FX
+
tax rules
+
investment assumptions
```

into:

```text
USD/foreign-currency returns
+
SGD returns
+
gross dividends
+
net dividends
+
withholding tax
+
reinvestment results
+
DCA results
+
portfolio results
```

with reproducible calculations and auditable data provenance.

**Do not build the frontend.**
