# Sprint 3 — Parity tests, property tests & worker hardening

## Goal

Prove the portable engine matches the Python reference and is safe for large
date ranges without blocking the interface.

## Entry criteria

- [x] Sprint 2 exit criteria are all met: the engine runs in a browser, returns
      Python-shaped envelopes, and uses decimal-safe arithmetic throughout.

## Depends on

Sprint 2.

## Tasks

- [x] Add golden parity tests that run identical fixtures through Python and the
      browser engine for USD and SGD securities, dividends, FX and incomplete
      data cases.
- [x] Add property tests for rounding, contribution scaling, split handling,
      cash-flow ordering and deterministic request keys.
- [x] Run calculations in Web Workers with cancellation/error handling so large
      date ranges do not block the interface.

## Exit criteria

- [x] Parity suite green for: USD ETFs, SGX/SGD securities, dividend and FX
      cases, and incomplete-data cases.
- [x] Property tests cover rounding, contribution scaling, splits, cash-flow
      ordering and deterministic request keys.
- [x] A running calculation can be cancelled; errors surface to the caller; the
      UI thread stays responsive for large ranges.
