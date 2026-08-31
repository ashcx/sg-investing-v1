# Sprint 4 — DCA, full static-site support

## Goal

Arbitrary DCA requests run entirely in the browser using the local engine and
lazily loaded data packs — no `/api/dca` dependency.

## Entry criteria

- [ ] Sprint 1 exit criteria are all met: packs exist for every supported
      security with support manifests.
- [ ] Sprint 2 exit criteria are all met: browser engine returns Python-shaped
      envelopes.
- [ ] Sprint 3 exit criteria are all met: parity and property suites are green;
      workers are cancellable and non-blocking.

## Depends on

Sprints 1, 2, 3.

## Tasks

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

## Exit criteria

- [ ] A fresh static deployment can calculate a new supported DCA request for
      any covered security without a network call to `/api`.
- [ ] All warning and provenance behavior matches the Python engine.
- [ ] DCA parity fixtures pass for the listed cases.
