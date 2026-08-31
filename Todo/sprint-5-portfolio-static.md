# Sprint 5 — Portfolio reconstruction, full static-site support

## Goal

Arbitrary user-entered ledgers are reconstructed entirely in the browser with
exact backend parity and local-only persistence.

## Entry criteria

- [ ] Sprint 1 exit criteria are all met: packs exist for every supported
      security with support manifests.
- [ ] Sprint 2 exit criteria are all met: browser engine returns Python-shaped
      envelopes.
- [ ] Sprint 3 exit criteria are all met: parity and property suites are green;
      workers are cancellable and non-blocking.

Note: this sprint may run in parallel with Sprint 4 once Sprints 1–3 are done.

## Depends on

Sprints 1, 2, 3.

## Tasks

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

## Exit criteria

- [ ] A fresh static deployment can reconstruct an arbitrary supported portfolio
      ledger entirely in the browser.
- [ ] All listed transaction types, validation and ordering rules match the
      backend exactly.
- [ ] Ledger persistence is local with working clear/export/import.
- [ ] Portfolio parity fixtures pass for the listed cases.
