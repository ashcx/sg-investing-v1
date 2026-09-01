# SG / Invest — GitHub Pages completion roadmap

This roadmap tracks the work required for the full frontend experience to run
on GitHub Pages without a runtime backend/API endpoint. The current site is a
static replay: the catalog and representative QQQ artifacts load, but arbitrary
analysis, DCA, comparison and portfolio requests still depend on the Python
adapter or a checked-in artifact.

## How this Todo system works

The work is split into nine sprints. Each sprint is one file in the `Todo/`
folder. Agents and humans must follow these rules:

1. **One sprint at a time.** Pick the lowest-numbered sprint whose entry
   criteria are satisfiable. Never start a sprint whose entry criteria are
   unmet.
2. **Entry criteria are a gate.** A sprint file's "Entry criteria" checklist
   must be fully ticked before any of its "Tasks" are started. Entry criteria
   reference the exit criteria of earlier sprints.
3. **Tick tasks as you complete them.** Work happens inside the sprint file's
   "Tasks" checklist. Tick `- [ ]` → `- [x]` in the sprint file itself as work
   completes — do not keep a separate task list elsewhere.
4. **Exit criteria are the completion gate.** A sprint is not complete until
   every "Exit criteria" item in its file is ticked. If an item cannot be
   ticked, the sprint is still in progress — record the blocker in the sprint
   file.
5. **Update the status column below** whenever sprint status changes:
   `Not started` → `In progress` → `Complete`. Also note parallel work (e.g.
   Sprints 4 and 5 in flight together) in the status cell.
6. **Do not skip or reorder sprints** beyond the parallelism noted below.
   Scope changes go through the sprint file (edit tasks there), never as
   side notes in code or PRs.
7. **Final acceptance** is the "Done when" section at the bottom of this file.
   It is only evaluated after Sprint 7 is complete.
8. **Task-level sequencing** (which tasks are sequential vs parallel, staffing
   patterns, freeze points) is coordinated in
   [Todo/orchestration-plan.md](Todo/orchestration-plan.md). That plan never
   overrides a sprint file's entry/exit gates.

| Sprint | File | Outcome | Depends on | Status |
| --- | --- | --- | --- | --- |
| 0 — Architecture decisions | [Todo/sprint-0-architecture-decisions.md](Todo/sprint-0-architecture-decisions.md) | Static target + calculation architecture recorded; specs updated | — | Complete |
| 1 — Static data packs | [Todo/sprint-1-data-packs.md](Todo/sprint-1-data-packs.md) | Versioned, partitioned, lazy-loadable packs for every security + manifests + publish workflow| 0 | Complete |
| 2 — Engine core port | [Todo/sprint-2-engine-core.md](Todo/sprint-2-engine-core.md) | Browser-runnable decimal-safe engine returning Python-shaped envelopes | 0 | Complete |
| 3 — Parity, property tests & workers | [Todo/sprint-3-parity-and-workers.md](Todo/sprint-3-parity-and-workers.md) | Golden parity + property suites green; calculations run in cancellable workers | 2 | Complete |
| 4 — DCA static support | [Todo/sprint-4-dca-static.md](Todo/sprint-4-dca-static.md) | Arbitrary DCA requests compute fully in-browser | 1, 2, 3 | Complete |
| 5 — Portfolio static support | [Todo/sprint-5-portfolio-static.md](Todo/sprint-5-portfolio-static.md) | Arbitrary ledgers reconstruct fully in-browser with local persistence | 1, 2, 3 | Complete |
| 6 — Fallback cleanup | [Todo/sprint-6-fallback-cleanup.md](Todo/sprint-6-fallback-cleanup.md) | One honest local-compute mode; no silent demo substitutions | 4, 5 | Complete |
| 7 — Release hardening & launch | [Todo/sprint-7-release-hardening.md](Todo/sprint-7-release-hardening.md) | Hardened CI, QA and confirmed GitHub Pages deployment | 4, 5, 6 | In progress |
| 8 — Pack origin & full-breadth hosting | [Todo/sprint-8-pack-origin.md](Todo/sprint-8-pack-origin.md) | Full 3,188-security set reachable client-side via a configurable non-Pages origin | 7 | Not started |

Sequencing notes:

- Sprints 4 and 5 are independent of each other and may run in either order or
  in parallel once Sprints 1–3 are complete.
- Sprint 2 may start against fixtures before Sprint 1 packs exist, but
  end-to-end feature work needs Sprint 1.
- Do not start Sprint 6 until both feature sprints (4 and 5) have delivered,
  since it removes the fallback paths they previously depended on.
- Sprint 8 (pack origin & full-breadth hosting) trails Sprint 7 so the
  Tier-1 Pages deployment and the `sg-invest-pack-base` override exist to
  build on; its research tasks may run as early-lane work at any time.

## Done when (final acceptance)

- [ ] A fresh GitHub Pages deployment can calculate a new supported DCA request
      for any covered security without a network call to `/api`.
- [ ] A fresh GitHub Pages deployment can reconstruct an arbitrary supported
      portfolio ledger entirely in the browser.
- [ ] Results match the Python reference fixtures, retain provenance/warnings,
      and never silently substitute a demo artifact.
- [ ] The site remains responsive, accessible and usable when data is missing,
      incomplete or stale.
