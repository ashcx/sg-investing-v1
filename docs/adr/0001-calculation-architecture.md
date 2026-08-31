# ADR 0001 — Calculation architecture for the static GitHub Pages deployment

- Status: Accepted
- Date: 2026-08-31
- Decides: Todo/sprint-0-architecture-decisions.md tasks (deployment target,
  calculation architecture)
- Related: TODO.md, Todo/orchestration-plan.md (freeze points),
  frontend_application_specification.md

## Context

Sprint 0 confirms two decisions required before any implementation sprint:

1. **Deployment target (confirmed).** The target is a fully static GitHub
   Pages site with no runtime `/api` dependency. GitHub Actions may build and
   publish data artifacts, but the browser must be able to complete supported
   calculations offline once its data packs are loaded. The current static
   replay can only show precomputed QQQ artifacts; arbitrary analysis, DCA,
   comparison and portfolio requests require computation in the browser.

2. **Calculation architecture.** The Python engine in `src/sg_investing/` is
   the authoritative reference and stays the source of truth for methodology.
   The browser needs a portable implementation of that methodology. The
   original TODO recorded Rust/WASM as preferred, with a decimal-library
   implementation acceptable if parity tests are comprehensive.

## Decision

**Browser-native ES-module JavaScript engine with a vendored decimal
arithmetic library (decimal.js), executed inside Web Workers, with no build
step.** The Python engine remains the single authoritative reference for
methodology and result contracts; the JS engine is a port of it, not an
independent design. Comprehensive golden parity tests against the Python
engine (Todo sprint 3) are the mandatory acceptance condition for the port —
this is the condition under which the original TODO permits a non-WASM
implementation.

Rationale against the alternatives:

- **Rust/WASM (deferred, not rejected forever):** introducing a Rust
  toolchain, wasm-bindgen/wasm-pack bindings and a compile stage in CI
  conflicts with the repository's zero-build static deployment (README:
  "no Node.js build step is required") and adds substantial parity-harness
  complexity. Revisit only if measured performance demands it.
- **TypeScript (deferred):** requires a compiler/build stage; the same
  decimal-safety and structure is achievable with plain ES2022 modules plus
  JSDoc typing, keeping the site build-free.

## Consequences

- `decimal.js` is vendored under `frontend/vendor/` and pinned; JavaScript
  `Number` is never used for money, FX, share quantities or XIRR inputs.
- Engine modules mirror the structure of `src/sg_investing/` so parity
  fixtures can be mapped module-for-module.
- Result envelopes must match the Python `model_dump(mode="json")` shapes,
  including warnings and provenance.
- Sprint 3's parity and property suites gate Sprints 4–5; no browser feature
  may compute results before parity is proven.
- The Python adapter (`scripts/frontend_server.py`) remains the development
  reference until Sprint 6 demotes it to an optional mode.

## Fonts and third-party assets (recorded with Sprint 1 task 8)

Decision deferred to Sprint 1's audit of `frontend/index.html` and
`styles.css`: any external font/asset references found there must be
self-hosted (vendored) so the site remains deterministic when third-party
requests are unavailable. The engine itself has zero third-party runtime
requests.
