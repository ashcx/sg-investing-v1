# Sprint 9 — Result trust and shared result contracts

## Goal

Make each displayed result, chart, warning, and export belong to the exact
request that produced it. Give the existing calculator views one clear contract
for initial, edited, loading, invalid, incomplete, failed, and previous-result
states, and make coverage and currency details understandable. This is the
first usable increment of the redesign; navigation and the new task views come
in later sprints.

Status: **In progress**. Implementation authorized by the Product Owner on
15 October 2026. S9-US01 is the first task; later stories remain gated.

## Entry criteria

- [x] Sprint 7 exit checklist reviewed; all exit items are checked in
      [Sprint 7](sprint-7-release-hardening.md).
- [x] Sprint 7.5 exit checklist reviewed; all exit items are checked in
      [Sprint 7.5](sprint-7.5-fx-incremental-reactive.md).
- [x] Sprint 8 exit checklist reviewed; all exit items are checked in
      [Sprint 8](sprint-8-pack-origin.md).

These historical exits establish the deployed static-engine baseline. They do
not resolve the live regressions reproduced in the UX audit.

## Depends on

Sprints 7, 7.5, and 8. Start this sprint only after all entry items above are
checked. Sprint 9 is the first redesign sprint; Sprint 10 depends on every
Sprint 9 exit item.

## Recorded scope decision and mandatory ordering

**Product Owner decision, 15 October 2026:** adopt explicit Calculate/Update;
label edited results as previous until recalculated. This amends Sprint 7.5's
automatic financial recalculation requirement for the calculator views. Automatic
series/data loading may remain. Preserve the safety intent of “no stale results
possible”: an output must never appear current for different inputs. Pending,
invalid, unsupported, or failed edits must identify retained outputs as previous,
with their original request summary and matching export/share identity.
Historical Sprint 7.5 completion remains evidence of its shipped baseline.

**Hard gate:** the first two S9-US01 tasks (documented request-identity contract
freeze and per-view state isolation) must both be complete, verified, and logged
before dependent regression fixtures/tests or any S9-US02/S9-US03 work starts.
This gate is mandatory even with one owner. Finish S9-US01 regression evidence
before S9-US02, then S9-US03. Do not tick this gate from planning alone.

## Tasks

Timebox commitment: **S9-US01 + S9-US02 (6 SP)**. **S9-US03 (3 SP) is
stretch**, still required for sprint exit. Execute stories and their tasks in
order, including checks and recorded self-review before advancing.

- [x] **S9-US01 — Keep every result with its own request** (P1, 3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Given** a completed result in one tool, **when** a different tool's
    security or currency selection changes, **then** the first result's
    security, period, chart, metrics, and display currency remain bound to its
    own completed request. (F03)
  - Tasks:
    - [x] Freeze a UI request-identity contract for results, charts, warnings,
          and exports; record its fields and state transitions in the frontend
          specification. Keep Python/browser calculation logic, worker
          protocol, and result envelopes unchanged.
          Account for Sprint 11's documented optional initial-lump-sum DCA
          extension when freezing UI request identity; include both amounts.
    - [x] Isolate per-view selection and chart/currency presentation state in
          `frontend/`; the main instance owns all affected files. Record
          isolation verification and contract evidence before downstream work.
    - [x] After the hard gate above is evidenced and deterministic fixtures
          are frozen, add the ES3 analysis then
          SMH regular-investing selection regression and assert the ES3 result
          remains internally consistent.
  - **Evidence:** request-state contract, deterministic regression output, and
    a browser capture showing the original result and chart stay paired.

- [x] **S9-US02 — Make current, pending, and previous results unmistakable**
      (P1, 3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Given** the initial form, an example, a completed calculation, or an
    invalid/unsupported edit, **when** the user opens the page or changes a
    financial input, **then** the visible result either matches the exact
    inputs or is clearly marked as pending/previous with its original inputs.
    (F01, F02, F08)
  - Tasks:
    - [x] Start empty or load an example whose inputs and result are the same
          request; remove any first-paint mismatch.
    - [x] Mark every financial edit, including initial amount, as pending, label
          retained output previous, and present one explicit Calculate/Update
          results action; do not automatically recalculate financial edits.
    - [x] For invalid, unavailable, or failed requests, show the new request's
          error and either clear the old result or label it as previous with
          its input summary; make its export/share controls identify that
          previous request.
    - [x] Add deterministic browser regressions for fresh load, amount edit,
          invalid amount, and unsupported dates; retain the fixture inputs with
          the test evidence.
  - **Evidence:** the four regressions, screenshots of empty/example/pending/
    error states, and output-to-request identity assertions.

- [x] **S9-US03 — Explain currency, coverage, and warnings beside the answer**
      (P1, 3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Given** a result with native currency, date truncation, or warnings,
    **when** the result is displayed, **then** the currency direction, requested
    dates, resolved dates, usable security/FX coverage, and material warnings
    are stated accurately near the answer with inspectable details. (F07, F09,
    F15)
  - Tasks:
    - [x] Use the security's actual native currency in FX captions, state the
          direction as native currency to SGD, and omit duplicate FX details
          for SGD securities.
    - [x] Distinguish requested dates, actual resolved dates, latest usable
          security/FX dates, and data snapshot date; show material truncation or
          staleness near the result.
    - [x] Add a consistent concise coverage/warning summary with grouped
          details and a recovery action where one exists.
    - [x] Add fixed-fixture checks for foreign and SGD currency captions,
          truncated dates, and warning visibility.
  - **Evidence:** deterministic currency/coverage/warning assertions and browser
    captures for one foreign-currency and one SGD result.

## Exit criteria

- [ ] Human Product Owner reviews the sprint outcome and evidence; record
      actual acceptance or requested changes before starting the next sprint.

- [x] Inspect the actual locally served webpage design after this sprint at
      desktop and mobile widths; record captures, changed-state checks, and
      findings under `docs/ux-redesign-evidence/sprint-9/`.
- [x] Open the sprint PR in `ashcx/sg-investing-v1` with the sprint plan,
      implementation changes, checks/results, and remaining gaps; record its URL.


- [x] F01, F02, F03, F07, F08, and F09 have deterministic browser regression
      evidence; no visible metric, chart, warning, or export can silently refer
      to a different request than its label and inputs.
- [x] Invalid, unavailable, failed, and edited requests have honest result
      states; retained results identify their original inputs and cannot appear
      current.
- [x] Currency direction, requested/resolved dates, usable coverage, snapshot
      date, and material warnings are accurate and visible at the result.
- [x] F15 warning details are consistently readable and have a recovery action
      where the current product can offer one.
- [x] Existing calculation outputs, decimal behavior, methodology, worker
      protocol, result-envelope shape, provenance, and warning semantics remain
      unchanged; record the relevant parity/diff evidence.
- [x] Sprint evidence is recorded under `docs/ux-redesign-evidence/sprint-9/`;
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
- **Acceptance owner:** the human user is Product Owner and owns product
  acceptance. The coordinator/integrator checks implementation evidence and
  records gaps; technical sign-off does not stand in for human usability
  acceptance.
- **Completion evidence:** store test output, browser captures, and any approved
  contract/spec changes in `docs/ux-redesign-evidence/sprint-9/`. No evidence or
  user outcome is claimed before it exists.

## Out of scope

Navigation, the unified simulator, comparison redesign, portfolio editing, and
release usability sessions are assigned to Sprints 10–14. Calculation
methodology, engine changes, new result-envelope fields, and production deploys
are outside this sprint.

## References

- [13 October 2026 UX audit](../docs/ux-audit-2026-10-13/README.md)
- [Frontend specification](../frontend_application_specification.md)
- [Sprint 10 — Workspace and discovery](sprint-10-workspace-and-discovery.md)
- [Scrum redesign plan and migration map](redesign-scrum-plan.md)

## Execution log

Planning amendment, 15 October 2026: sequential main-instance ownership and
6-SP commitment plus 3-SP stretch recorded. Implementation remains Not started;
no implementation evidence or completed task is claimed by this amendment.

For each task, record date/ID, status, changed files, checks and exact results,
evidence paths, separate self-review findings, blockers, and next sequential
action here before proceeding. Human acceptance is recorded only when given.

### 15 October 2026 — Sprint Planning

- Owner: main instance, including subsequent self-review; no delegation.
- Entry review: inspected Sprint 7, 7.5, and 8 exit sections; all are checked.
- Commitment: S9-US01 and S9-US02 (6 SP); S9-US03 is 3-SP stretch and remains
  mandatory before exit. Reserve review/rework capacity and use recovery if needed.
- Authorized decisions: explicit Calculate/Update; previous-result labels after
  edits; browser design review and one PR per sprint.
- Sequence: freeze UI identity → isolate views → verify/log the hard gate →
  S9-US01 deterministic/browser regression → S9-US02 → S9-US03 → full review/PR.
- Existing audit/prototype/planning files are included as the redesign baseline;
  they are not evidence that production implementation is complete.

### 15 October 2026 — S9-US01 hard gate verified

- Frozen contract: `frontend_application_specification.md`, Sprint 9 UI request
  identity section; includes future initial lump sum plus recurring amounts.
- Changes: analysis and DCA selections/currency are isolated; series prefetch
  cannot replace a completed analysis chart; DCA coverage context survives rerender.
- Checks: module syntax PASS; real headless Chrome loads the page and changes
  DCA to catalog SMH; analysis selection and complete result/chart HTML remain
  unchanged after the debounce interval (PASS). Isolated temporary Chrome
  profile; no private user browser/ledger data used.
- Self-review: confirmed DCA currency handlers no longer rerender analysis.
- Hard gate satisfied; next: deterministic ES3/SMH fixture regression and capture.

### 15 October 2026 — S9-US01 and S9-US02 verification

- Changes: independent selection/currency/chart ownership; frozen request
  summaries; immediate pending/previous labels; explicit submit; invalid/failed
  request states; no first-paint example; generation invalidation on input.
- Evidence: `tests/browser/sprint-9.cjs`, fixed inputs in
  `tests/fixtures/redesign/sprint-9.json`, captures in the sprint evidence folder.
- Real Chrome against fixture packs and the actual worker: fresh load, synthetic
  ES3 analysis → SMH DCA/currency, amount edit, invalid amount, unsupported
  analysis/DCA dates, edit during in-flight work, and no browser exceptions PASS.
- Fixtures reuse golden input rows but relabel securities ES3/SMH for UI identity
  checks; they are explicitly synthetic and are not evidence of market returns.
- Self-review: DCA display context retained; share uses requested rather than
  resolved dates; previous export controls identify the originating request.
- Next: S9-US03 coverage/currency/warning presentation and fixtures.

### 15 October 2026 — S9-US03, verification and design review

- S9-US03 complete: native-to-SGD caption, SGD FX suppression, requested/resolved
  periods, published security/FX coverage and snapshot metadata, grouped original
  warnings, and a keyboard-accessible action to review dates. Missing metadata
  is explicitly Not published. No engine/result-envelope changes.
- Verification: Python 218 pass/8 deselected; selftest 68; parity 27; worker 90;
  properties 19/1,473 cases; deterministic Chrome UI suite and static checks PASS.
  See `docs/ux-redesign-evidence/sprint-9/README.md` and linked reports/captures.
- Self-review and actual webpage design inspection: 1440/390/320px. Corrected
  inherited coverage typography, narrow analysis form overflow, and result badge
  overflow; mobile result bounds pass. Later-sprint whole-site issues remain
  assigned to their owners in the backlog.
- Ruff: 13 baseline findings in unchanged Python files; recorded without changing
  unrelated code. Full generated-pack integrations not run (packs absent);
  fixed-pack browser checks run the actual worker and make no live data calls.
- Next: publish sprint PR with these checks and obtain human product review.
  Sprint 9 remains In progress until actual acceptance; Sprint 10 stays gated.

### 15 October 2026 — PR published; product review pending

- PR: https://github.com/ashcx/sg-investing-v1/pull/1
- Branch: `codex/sprint-9-result-trust`; targets `main` in the configured repo.
- PR includes the Scrum plan, Sprint 9 changes, verification results, screenshots,
  baseline lint findings, and remaining later-sprint scope.
- Connected GitHub app could read the repo but denied PR creation (HTTP 403);
  the repository's working Git authentication created the PR successfully.
- All technical and design-review exit items are checked. Human Product Owner
  acceptance is still unchecked; no merge/deploy or Sprint 10 work performed.
