# Sprint 2 — Portable calculation engine (core port)

## Goal

A browser-runnable calculation module/worker that reproduces the Python
engine's methodology and result envelopes exactly.

## Entry criteria

- [x] Sprint 0 exit criteria are all met: calculation architecture (Rust/WASM
      vs TypeScript-decimal) is recorded and the specs reflect it.

Note: this sprint may start against fixtures before Sprint 1 packs exist, but
end-to-end use requires Sprint 1.

## Depends on

Sprint 0. (Sprint 1 needed for end-to-end use, not for porting.)

## Tasks

- [x] Extract or port the authoritative backend calculations into a browser
      module/WASM worker without changing the financial methodology.
- [x] Use decimal-safe arithmetic throughout; do not use JavaScript `Number` for
      financial calculations, FX conversion, share quantities or XIRR inputs.
- [x] Preserve the backend rules for next-trading-day purchases, previous-close
      valuation, FX direction, dividend withholding, pay-date estimates,
      reinvestment and accumulating funds.
- [x] Return the same result envelopes and provenance fields as the Python
      engine, including warnings and coverage status.

## Exit criteria

- [x] The engine runs in a browser (module or worker) and returns Python-shaped
      result envelopes for early fixture cases.
- [x] No `Number`-based arithmetic in any financial path (auditable grep/review).
- [x] Methodology rules listed above demonstrably behave as the backend does.

## Out of scope

- Formal parity/property test suites and worker hardening (Sprint 3).
- Wiring DCA/portfolio UI features onto the engine (Sprints 4–5).
