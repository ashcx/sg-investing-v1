# SG / Invest — GitHub Pages completion roadmap

This roadmap tracks the full frontend experience on GitHub Pages without a
runtime backend/API endpoint. Sprints 0–8 delivered browser calculation and
static data-pack hosting. Sprints 9–15 propose a task-focused website redesign
and repair the usability and result-state regressions documented in the
[13 October 2026 audit](docs/ux-audit-2026-10-13/README.md). The
[redesign Scrum plan](Todo/redesign-scrum-plan.md) coordinates the sequential
sprints and sequential work performed entirely in the main instance. The
[clickable low-fidelity prototype](docs/redesign-prototype/index.html) is a
planning artifact, not an implemented production increment.

## How this Todo system works

The work is split into seventeen sprints (Sprint 7.5 slots between 7 and 8). Each sprint is one file in the `Todo/`
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
   `Not started` → `In progress` → `Complete`.
6. **Do not skip or reorder sprints.** All tasks, tests, reviews, and
   documentation run sequentially in the main instance, without child agents.
   Scope changes go through the sprint file (edit tasks there), never as
   side notes in code or PRs.
7. **Final acceptance** is the "Done when" section at the bottom of this file.
   Preserve the core-roadmap checks from Sprint 7 onward. The redesign is
   accepted only after Sprint 15 and all of its predecessor exit gates are met;
   core-engine completion alone does not complete the redesign. Under the
   18 October authorization, Sprints 12–15 use technical exit gates with human
   product acceptance recorded separately as pending until actually given.
8. **Task-level sequencing** (task order, contract freezes, and recorded
   verification) is coordinated in
   [Todo/orchestration-plan.md](Todo/orchestration-plan.md). That plan never
   overrides a sprint file's entry/exit gates.
9. **Record results before continuing.** Update the owning sprint checklist
   and execution log with changed files, exact check results, evidence paths,
   blockers, and next action. Review follows implementation in the main instance;
   self-review is never described as independent review or human acceptance.

| Sprint | File | Outcome | Depends on | Status |
| --- | --- | --- | --- | --- |
| 0 — Architecture decisions | [Todo/sprint-0-architecture-decisions.md](Todo/sprint-0-architecture-decisions.md) | Static target + calculation architecture recorded; specs updated | — | Complete |
| 1 — Static data packs | [Todo/sprint-1-data-packs.md](Todo/sprint-1-data-packs.md) | Versioned, partitioned, lazy-loadable packs for every security + manifests + publish workflow| 0 | Complete |
| 2 — Engine core port | [Todo/sprint-2-engine-core.md](Todo/sprint-2-engine-core.md) | Browser-runnable decimal-safe engine returning Python-shaped envelopes | 0 | Complete |
| 3 — Parity, property tests & workers | [Todo/sprint-3-parity-and-workers.md](Todo/sprint-3-parity-and-workers.md) | Golden parity + property suites green; calculations run in cancellable workers | 2 | Complete |
| 4 — DCA static support | [Todo/sprint-4-dca-static.md](Todo/sprint-4-dca-static.md) | Arbitrary DCA requests compute fully in-browser | 1, 2, 3 | Complete |
| 5 — Portfolio static support | [Todo/sprint-5-portfolio-static.md](Todo/sprint-5-portfolio-static.md) | Arbitrary ledgers reconstruct fully in-browser with local persistence | 1, 2, 3 | Complete |
| 6 — Fallback cleanup | [Todo/sprint-6-fallback-cleanup.md](Todo/sprint-6-fallback-cleanup.md) | One honest local-compute mode; no silent demo substitutions | 4, 5 | Complete |
| 7 — Release hardening & launch | [Todo/sprint-7-release-hardening.md](Todo/sprint-7-release-hardening.md) | Hardened CI, QA and confirmed GitHub Pages deployment | 4, 5, 6 | Complete |
| 7.5 — FX to 2000, incremental updates, reactive UI | [Todo/sprint-7.5-fx-incremental-reactive.md](Todo/sprint-7.5-fx-incremental-reactive.md) | Foreign-currency history back to 2000; incremental date-range updates without full rebuild; staged auto-loading UI | 7 | In progress |
| 8 — Pack origin & full-breadth hosting | [Todo/sprint-8-pack-origin.md](Todo/sprint-8-pack-origin.md) | Full 3,188-security set reachable client-side via a configurable non-Pages origin | 7 | Complete |
| 9 — Result trust and shared contracts | [Todo/sprint-9-user-experience-redesign.md](Todo/sprint-9-user-experience-redesign.md) | Reliable request/result ownership and regression protection | 7, 7.5, 8 | Complete |
| 10 — Workspace and discovery | [Todo/sprint-10-workspace-and-discovery.md](Todo/sprint-10-workspace-and-discovery.md) | Clear navigation, reusable search and coverage preview | 9 | In progress |
| 11 — Investment simulator | [Todo/sprint-11-investment-simulator.md](Todo/sprint-11-investment-simulator.md) | One-time investing and optional initial lump sum + DCA in one coherent simulator | 10 | In progress |
| 12 — Fair comparisons | [Todo/sprint-12-fair-comparisons.md](Todo/sprint-12-fair-comparisons.md) | Common-period handling and labeled responsive comparisons | 7.5 operational recovery; 11 technical exits | Not started |
| 13 — Portfolio workflow | [Todo/sprint-13-portfolio-workflow.md](Todo/sprint-13-portfolio-workflow.md) | Guided transaction editing and safe existing-ledger preservation | 12 | Not started |
| 14 — Interface design overhaul | [Todo/sprint-14-interface-design-overhaul.md](Todo/sprint-14-interface-design-overhaul.md) | Professional visual identity, restrained copy, and cohesive desktop/mobile design using frontend-design | 13 | Not started |
| 15 — Release and usability | [Todo/sprint-15-release-and-usability.md](Todo/sprint-15-release-and-usability.md) | Verified journeys, accessibility, usability and release evidence | 14 | Not started |

Sequencing notes:

- 18 October 2026 unattended-run preflight: user requires Sprint 7.5 recovery
  before interface implementation. Early Sprint 14 visual proposals are expressly
  requested for review now; this does not open implementation gates. Separate
  PRs are required for Sprints 12–15. Human review deferral is not yet authorized.

- 18 October 2026: user requested a new Sprint 14 interface design overhaul
  using frontend-design, preserving the high-level workspace structure. The
  previous validation/usability sprint moved to Sprint 15; a subsequent explicit
  user decision replaces its five-person gate with technical/design review. This is a
  planning amendment only; existing entry/acceptance gates remain open.

- 18 October 2026: Sprint 7.5 Track B daily-operation exit reopened following
  verified scheduled failures. Investigation and sequential recovery are recorded
  in its sprint file; prior implementation evidence is retained. Sprints 10–11
  retain their existing review status; no later sprint starts during recovery.

- Execute Sprints 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 7.5 → 8 → 9 → 10 →
  11 → 12 → 13 → 14 → 15, one at a time. Dependencies in the table are minimum
  technical prerequisites, not permission to start another sprint early.
- Verify all depended-on exits and the active sprint's entry criteria before
  starting work. Sprints 0–8 retain their historical completion evidence.
- Sprint 9 is Complete; Sprints 10 and 11 are In progress pending product review; Sprints 12–15 remain Not started. Historical exits do not negate the
  regressions recorded by the audit.
- User decision, 15 October 2026: all work belongs to the main instance, with
  sequential implementation, verification, self-review, and recorded results.
- Product Owner decision, 15 October 2026: adopt explicit Calculate/Update;
  edited results are labeled previous until recalculated. Sprint 9 records the
  amendment to Sprint 7.5's automatic-calculation behavior.
- Redesign timebox commitment: US01 + US02 = 6 SP; US03 = 3 SP stretch, with
  20–30% of capacity reserved for review/rework. Stretch remains required for
  sprint exit; use a recovery timebox if needed before starting the next sprint.

## Done when (final acceptance)

- [ ] A fresh GitHub Pages deployment can calculate a new supported DCA request
      for any covered security without a network call to `/api`.
- [ ] A fresh GitHub Pages deployment can reconstruct an arbitrary supported
      portfolio ledger entirely in the browser.
- [ ] Results match the Python reference fixtures, retain provenance/warnings,
      and never silently substitute a demo artifact.
- [ ] The site remains responsive, accessible and usable when data is missing,
      incomplete or stale.
- [ ] Sprint 14 delivers the reviewed visual overhaul across all four workspaces,
      with a new palette, restrained copy, and cohesive mobile/desktop behavior.
- [ ] All Sprint 9–15 tasks and exit criteria are satisfied, with the audit
      findings reconciled to evidence and no reproduced P1 defect remaining.
- [ ] Existing ledgers remain compatible and recoverable, and every result,
      chart, date, warning, and export identifies the request it represents.
- [ ] Sprint 15's technical/design task review and repair/retest evidence are
      complete; agent review is not represented as human usability research.


## Technical progression authorization — 18 October 2026

Product Owner decision: **Keep PR #5 open for review.** Do not merge or deploy
it. After Sprint 7.5 is operationally verified, **proceed with Sprints 12–15 on
verified technical checks; keep human acceptance pending** in each separate PR.
This supersedes the earlier unresolved human-review-deferral notes only.

For Sprints 12–15, completion and progression require all implementation,
technical/design verification, viewport evidence, separate self-review, and
sprint-PR exit criteria. Human product/release acceptance is tracked in a
separate section, remains pending until actually given, and does not block the
next sprint. Sprint 12 checks Sprint 11's technical/design/PR exits rather than
its pending human acceptance. This does not waive Sprint 7.5 operational
verification, any technical dependency, the selected-design decision, or merge
and deployment authorization. Research is the explicitly selected direction.
No entry, task, exit, or acceptance checkbox is completed by this amendment.
