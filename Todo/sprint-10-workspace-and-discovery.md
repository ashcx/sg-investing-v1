# Sprint 10 — Workspace and security discovery

## Goal

Give users a small set of clear destinations and a reusable way to find and
identify a security. Establish the shared visual and language rules used by the
simulator, comparison, portfolio, and Data & methods views.

Status: **Complete**.

## Entry criteria

- [x] Every Sprint 9 exit criterion is checked, including the request-identity,
      result-state, currency, coverage, and warning evidence.

## Depends on

Sprint 9 only. Work in this sprint begins after its full exit gate; Sprint 11
waits for all Sprint 10 exits. The redesign sequence is strictly serial.

## Tasks

Timebox commitment: **S10-US01 + S10-US02 (6 SP)**. **S10-US03 (3 SP) is
stretch**, still required for sprint exit. Execute stories and their tasks in
order, including checks and recorded self-review before advancing.

- [x] **S10-US01 — Navigate by task and return to a view** (P1, 3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Given** a visitor arriving at the site or opening a destination directly,
    **when** they choose Simulator, Compare investments, My portfolio, or
    Data & methods, **then** the selected destination is clear, its URL can be
    reloaded, browser Back works, and keyboard users can skip to its content.
    (F12)
  - Tasks:
    - [x] Review [the low-fidelity prototype](../docs/redesign-prototype/index.html),
          its [README](../docs/redesign-prototype/README.md), and the audit.
          Walk through the navigation and state annotations with the Product
          Owner in the normal Sprint Planning/Review cadence, then freeze the
          agreed route and state design in the frontend specification before
          shell implementation. This review is part of the sprint, not a
          separate approval gate; the prototype remains design input.
    - [x] Replace the long feature-first page structure with compact persistent
          task navigation and one active workspace view.
    - [x] Make direct links, browser Back/Forward, reload, and supported legacy
          section links open a meaningful destination; record the legacy-link
          mapping.
    - [x] Specify share-link semantics: links recalculate using available latest
          published packs; exports retain the produced snapshot metadata. Do not
          imply a historical snapshot is loaded solely because its ID is in a URL.
    - [x] Add a skip-to-content link and a keyboard/touch-operable collapsed
          navigation for narrow screens.
    - [x] Replace the promotional first screen with a short task introduction
          and an optional example action.
  - **Evidence:** frozen route/state design, prototype and audit walkthrough
    notes, route/deep-link browser checks, keyboard path, and captures of
    desktop and narrow-screen navigation.

- [x] **S10-US02 — Find a security and recover from an empty search** (P1, 3 SP;
      owner: main instance; review: subsequent main-instance self-review).
  - **Given** a user searching by ticker, name, or ISIN, **when** results appear
    or the query has no match, **then** each result identifies the security,
    exchange, currency, and coverage, and an uncommitted/unknown query cannot
    inherit metadata from the previous selection. (F14, F19)
  - Tasks:
    - [x] Build one reusable search/browse panel with Arrow keys, Enter, Escape,
          touch selection, clear/reset, and visible query/selection states.
    - [x] Move advanced filters behind a progressive browse control; translate
          internal universe names into friendly labels and show active filters.
    - [x] Fix result counts and bounded pagination so the count is not clipped
          and no visible “Show more” action leads to an unreachable result.
    - [x] Show identity and usable-history/coverage facts before selection.
    - [x] Add deterministic fixtures for known, unknown, empty, and paginated
          searches; begin subsequent main-instance test/self-review only after fixtures are
          frozen.
  - **Evidence:** search fixture output, keyboard/touch browser checks, and
    captures of selected, uncommitted, empty, and filtered states.

- [x] **S10-US03 — Apply one readable workspace language and style** (P1/P2,
      3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Given** a user moving among workspace views or checking a security's
    methodology, **when** labels and controls are rendered, **then** form labels
    remain readable, components share a coherent hierarchy, and Data & methods
    shows security-specific coverage, sources, assumptions, and provenance.
    (F05, F16, F17, F18)
  - Tasks:
    - [x] Define semantic type, spacing, surface, focus, status, control, and
          responsive tokens; scope surfaces so form text stays legible on its
          background and normal text meets the audit's contrast target.
    - [x] Apply consistent labels, fields, buttons, cards, and status patterns
          to the workspace shell and security picker.
    - [x] Create the Data & methods utility view with contextual coverage and
          provenance for the selected security; retain general methodology as
          supporting help.
    - [x] Record a plain-language glossary; use agreed names such as
          “Compare investments,” “Currency,” and “Average cost” in shared
          chrome. Simulator and portfolio-specific advanced terms are completed
          in their owning sprints. Map “Force refresh”/“replay” to Calculate or
          Update results, “same lens” to same assumptions, “dividend bridge” to
          Dividend details, and CCY/WAC to Currency/Average cost; Sprints 11 and
          13 explain XIRR and average cost in context.
    - [x] Check visible focus, reduced motion, text sizing, and labels at the
          widths in the UX audit; record any limitation for Sprint 14.
  - **Evidence:** token/glossary specification, contrast measurements, and
    browser captures of forms and security-specific Data & methods content.

## Exit criteria

- [x] Human Product Owner reviews the sprint outcome and evidence; record
      actual acceptance or requested changes. For the user-authorized S10→S11
      pair, review may follow both increments; all technical/design/PR gates
      still apply before S11, as recorded in the Scrum execution amendment.

- [x] Inspect the actual locally served webpage design after this sprint at
      desktop and mobile widths; record captures, changed-state checks, and
      findings under `docs/ux-redesign-evidence/sprint-10/`.
- [x] Open the sprint PR in `ashcx/sg-investing-v1` with the sprint plan,
      implementation changes, checks/results, and remaining gaps; record its URL.


- [x] The four destinations have distinct active navigation; direct URLs,
      reload, Back/Forward, skip-to-content, and narrow-screen navigation work.
- [x] Search covers ticker/name/ISIN, recovery, friendly filters, selected vs
      uncommitted identity, usable-history/coverage, and bounded pagination;
      F14 and F19 have deterministic evidence.
- [x] F05 and F17 are resolved by a consistent component system with readable
      labels, usable focus, and documented responsive rules.
- [x] F18 has actionable security-specific Data & methods content with retained
      provenance and assumptions.
- [x] Shared terminology is recorded and applied to navigation and discovery;
      remaining context-specific terminology is assigned to Sprints 11–13.
- [x] Sprint evidence is recorded under `docs/ux-redesign-evidence/sprint-10/`;
      every story acceptance condition and evidence item is satisfied.

## Scrum details

- **Sprint length and capacity:** fixed one-week timebox; US01 + US02 = 6 SP
  committed, US03 = 3 SP stretch. The candidate backlog ceiling is 9 SP.
  Reserve 20–30% of actual capacity for review/rework. Re-estimate at planning;
  reduce or split the commitment in this file if it exceeds 7 SP. All stories
  remain required for exit. If stretch or committed work is unfinished, record
  it and plan a recovery timebox in this sprint before starting the next sprint.
- **Ownership:** the main instance performs all implementation, tests,
  documentation, and subsequent self-review sequentially. No child agents or
  delegated review. Finish and record each task before starting the next.
- **Acceptance owner:** the human user as Product Owner. Coordinator review
  confirms evidence and records unresolved product questions without claiming
  user acceptance.
- **Completion evidence:** store route checks, search fixtures, captures, and
  contrast measurements in `docs/ux-redesign-evidence/sprint-10/`.

## References

- [UX audit: findings F05, F12, F14, F16–F19](../docs/ux-audit-2026-10-13/README.md)
- [Low-fidelity prototype](../docs/redesign-prototype/index.html) and
  [prototype README](../docs/redesign-prototype/README.md)
- [Sprint 9 — Result trust](sprint-9-user-experience-redesign.md)
- [Sprint 11 — Investment simulator](sprint-11-investment-simulator.md)
- [Scrum redesign plan](redesign-scrum-plan.md)

## Execution log

Planning amendment, 15 October 2026: sequential main-instance ownership and
6-SP commitment plus 3-SP stretch recorded. Implementation remains Not started;
no implementation evidence or completed task is claimed by this amendment.

For each task, record date/ID, status, changed files, checks and exact results,
evidence paths, separate self-review findings, blockers, and next sequential
action here before proceeding. Human acceptance is recorded only when given.

### 15 October 2026 — Planning and route freeze

Owner: main instance. User authorized Sprints 10 and 11 after the outcome summary.
Reviewed Sprint 9 exits/evidence, prototype, prototype README/QA and audit.
Commitment: US01 + US02, 6 SP; US03 is required stretch. Desktop/mobile checks
and separate PR precede Sprint 11. Human review is deferred for this authorized
pair and remains explicitly pending; this is not product acceptance of S10.
Route contract is frozen in the frontend specification before shell changes.

### S10-US01 complete

Four mounted workspaces, canonical and legacy URL routes, route-preserving skip
link, compact navigation and task introduction implemented. Frozen contract in
frontend specification. Chrome routes/direct links/Back/Forward/reload/skip
checks PASS (`docs/ux-redesign-evidence/sprint-10/routes.txt`). Subsequent
self-review corrected initialization order; no result is recalculated on route
changes. Next: US02; fixed search cases in `tests/browser/sprint-10.cjs` include
1,051 unique catalog entries, known ISIN, empty search and unknown text.

### S10-US02 and US03 complete — technical/design review

Frozen search fixture: 1,051 unique entries, known ISIN, unknown/empty query and
pagination beyond the former cap. Browser checks PASS: keyboard selection,
metadata clearing, clear/reset, complete pagination, coverage previews,
contextual methodology, mobile menu and Back/Forward. Light-form label contrast
measured at 15.84:1. Reduced motion exercised; focus styles and skip link checked.
Actual page captures inspected at 1440/1280/768/390/320px; no page overflow.
Sprint 9 result-state/export/share regressions PASS in the new workspace.
Static-site, module syntax and whitespace checks PASS. No calculation or worker
changes in this sprint. Reports/captures: `docs/ux-redesign-evidence/sprint-10/`.
Human review remains pending under the user-authorized S10/11 execution amendment.
Next: publish the Sprint 10 PR, then verify its technical gates before S11.

PR published: https://github.com/ashcx/sg-investing-v1/pull/2 (stacked on #1).
All technical/design/PR exits verified. Human product review remains pending.


### Completion review, 28 October 2026

Fresh sequential Chrome checks pass for this sprint's implemented behavior.
Implementation/design/PR exits remain satisfied; human Product Owner acceptance
remains unrecorded and unchecked. Status remains **In progress**, with technical
work complete. See [completion review](../docs/sprint-completion-2026-10-28/README.md)
for exact scope, captures, published PR state and dropped test-drift finding.
No acceptance is inferred from merge or publication authorization.


### Product Owner acceptance, 28 October 2026

Following the completion review and its reported verification results, the
human Product Owner explicitly accepted Sprints 10 and 11 in this chat:
"yes go ahead and accept". Human acceptance is now recorded and checked.
All exit criteria are checked; status is **Complete**. This records acceptance
of the reviewed increments and does not start Sprint 13 or authorize deployment.

Release-validation follow-up, 28 October 2026: `tests/browser/startup.cjs`
held the optional data-status response and reproduced workspace routing never
initializing. The initialization order now activates routes before awaiting
that metadata. The held-response probe passes without releasing the response.
This repair is in the Sprint 14 PR; prior product acceptance is unchanged.
