# Sprint 4 — DCA, full static-site support

## Goal

Arbitrary DCA requests run entirely in the browser using the local engine and
lazily loaded data packs — no `/api/dca` dependency.

## Entry criteria

- [x] Sprint 1 exit criteria are all met: packs exist for every supported
      security with support manifests.
- [x] Sprint 2 exit criteria are all met: browser engine returns Python-shaped
      envelopes.
- [x] Sprint 3 exit criteria are all met: parity and property suites are green;
      workers are cancellable and non-blocking.

## Depends on

Sprints 1, 2, 3.

## Tasks

- [x] Replace the static-mode `/api/dca` dependency with the local calculation
      engine and lazily loaded security data packs.
- [x] Support monthly, quarterly and yearly contribution schedules using the
      backend's first-available-trading-day rule.
- [x] Support dividends, withholding tax, reinvestment, fractional shares,
      native-currency output, SGD output and both XIRR fields.
- [x] Preserve explicit warnings for estimated/missing pay dates, missing FX,
      incomplete price history and unverified dividend coverage.
- [x] Add parity fixtures for USD ETFs, SGX/SGD securities, accumulating funds,
      zero-dividend cases and invalid date/amount inputs.
- [x] Show a clear loading/progress state while a data pack or worker result is
      being resolved; never show a result from a different request.

## Exit criteria

- [x] A fresh static deployment can calculate a new supported DCA request for
      any covered security without a network call to `/api`.
- [x] All warning and provenance behavior matches the Python engine.
- [x] DCA parity fixtures pass for the listed cases.
