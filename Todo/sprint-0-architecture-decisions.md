# Sprint 0 — Architecture decisions & spec alignment

## Goal

Lock the deployment target and calculation architecture so every later sprint
builds on one recorded decision.

## Entry criteria

None — this is the first sprint. Start here.

## Depends on

Nothing.

## Tasks

- [x] Confirm the target is a fully static GitHub Pages site with no runtime
      `/api` dependency. GitHub Actions may build/publish data, but the browser
      must be able to complete supported calculations offline after its data is
      loaded.
- [x] Record the chosen calculation architecture: a shared Rust/WASM core is
      preferred; a TypeScript implementation using a decimal arithmetic library
      is an acceptable alternative if parity tests are comprehensive.
- [x] Update the frontend specification and README when the architecture is
      approved. The current specification keeps financial calculation logic in
      Python, which must change for arbitrary no-API calculations.

## Exit criteria

- [x] Architecture decision recorded in the repository (short ADR or a section
      in `frontend_application_specification.md`).
- [x] `frontend_application_specification.md` and `README.md` updated to match.
- [x] No open design questions blocking Sprint 1 (data packs) or Sprint 2
      (engine port).

## References

- `product_design_document.md`
- `frontend_application_specification.md`
- README section "GitHub Pages deployment"
