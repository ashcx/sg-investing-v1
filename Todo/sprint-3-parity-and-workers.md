# Sprint 3 — Parity tests, property tests & worker hardening

## Goal

Prove the portable engine matches the Python reference and is safe for large
date ranges without blocking the interface.

## Entry criteria

- [ ] Sprint 2 exit criteria are all met: the engine runs in a browser, returns
      Python-shaped envelopes, and uses decimal-safe arithmetic throughout.

## Depends on

Sprint 2.

## Tasks

- [ ] Add golden parity tests that run identical fixtures through Python and the
      browser engine for USD and SGD securities, dividends, FX and incomplete
      data cases.
- [ ] Add property tests for rounding, contribution scaling, split handling,
      cash-flow ordering and deterministic request keys.
- [ ] Run calculations in Web Workers with cancellation/error handling so large
      date ranges do not block the interface.

## Exit criteria

- [ ] Parity suite green for: USD ETFs, SGX/SGD securities, dividend and FX
      cases, and incomplete-data cases.
- [ ] Property tests cover rounding, contribution scaling, splits, cash-flow
      ordering and deterministic request keys.
- [ ] A running calculation can be cancelled; errors surface to the caller; the
      UI thread stays responsive for large ranges.
