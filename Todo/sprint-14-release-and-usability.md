# Sprint 14 — Release validation and usability

## Goal

Verify the complete redesign against the audit, existing deterministic
calculation contracts, real viewport/accessibility checks, and observed tasks
with unfamiliar people. Record what the evidence supports before making any
release claim.

Status: **Not started**.

## Entry criteria

- [ ] Every Sprint 13 exit criterion is checked, including ledger preservation,
      accessible transaction entry, mobile readability, and import/export
      evidence.

## Depends on

Sprint 13 only. This is the final sequential sprint in the redesign plan. Do not
begin release acceptance while any earlier sprint remains incomplete.

## Tasks

Timebox commitment: **S14-US01 + S14-US02 (6 SP)**. **S14-US03 (3 SP) is
stretch**, still required for sprint exit. Execute stories and their tasks in
order, including checks and recorded self-review before advancing.

- [ ] **S14-US01 — Verify financial and static-site behavior end to end** (P1,
      3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Given** a locally served integrated candidate, fixed test data, and the
    published pack artifacts, **when** the verification matrix runs, **then**
    calculation parity, browser journeys, exports, URL state, pack behavior,
    and failure recovery are recorded with no change to engine contracts.
    (F01–F04, F07–F11, F15)
  - Tasks:
    - [ ] Run deterministic journeys for one-time investment, regular
          investing, comparison, portfolio, pending/error states, and routes.
          Include pure DCA and initial-lump-sum-plus-DCA, with matching Python
          and browser results and correct invested-capital/XIRR cash flows.
    - [ ] Run the Python, golden parity, property, worker, and static-site
          suites; build packs for required pack-integration checks and record
          results.
    - [ ] Exercise the locally served integrated candidate against published
          Tier-1/Tier-2 pack artifacts, including missing-pack and network
          failure recovery; confirm no runtime calculation API is required.
    - [ ] Separately run read-only smoke checks on the currently deployed
          baseline to confirm the existing pack origins remain reachable. Label
          these checks as baseline evidence; they do not prove the redesigned
          candidate is deployed or validate its UI.
    - [ ] Verify result, series, ledger, and share-link round trips preserve
          request identity, warnings, provenance, methodology, and snapshot
          semantics.
    - [ ] Reconcile each audit finding F01–F19 against a test, inspection, or
          documented resolution; do not count absence of evidence as a pass.
  - **Evidence:** dated test reports, fixture manifests, read-only smoke
    captures/logs, and a finding-by-finding evidence map.

- [ ] **S14-US02 — Inspect responsive, keyboard, and zoom behavior** (P1, 3 SP;
      owner: main instance; review: subsequent main-instance self-review).
  - **Given** the integrated candidate, **when** it is inspected at the audit's
    viewport widths and with keyboard, zoom, reduced-motion, and accessible-name
    checks, **then** financial values retain their labels and controls remain
    reachable/readable, with limitations recorded. (F05, F06, F10–F19)
  - Tasks:
    - [ ] Inspect 320, 390, 768, 1280, and 1440 pixel layouts; check 200% zoom,
          keyboard order/focus, reduced motion, chart table alternatives,
          accessible names, and contrast.
    - [ ] Check all displayed mobile metric cards, warnings, form validation,
          route navigation, and portfolio transaction controls.
    - [ ] Save before/after captures and an issue log; fix release-blocking P1
          defects through the owning sprint file before declaring completion.
  - **Evidence:** viewport matrix, contrast/accessibility findings, keyboard
    paths, captures, and a list of remaining limitations.

- [ ] **S14-US03 — Evaluate real human usability tasks** (P1, 3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Human involvement:** the Product Owner recruits/accepts participants;
    actual people perform the sessions. The main instance prepares materials,
    records available observations, and evaluates evidence.
  - **Given** five people unfamiliar with the product and a stable candidate,
    **when** each performs the four audit tasks without coaching, **then** their
    task completion, mistakes, comprehension, and time to first valid result
    are recorded directly, and release readiness reflects the observed results.
  - Tasks:
    - [ ] Prepare a neutral task script for: QQQ one-time investment and actual
          dates; monthly contributions and result meaning; QQQ/VALL history
          difference; and adding/correcting a portfolio transaction and finding
          its save location.
    - [ ] Recruit and run sessions with five unfamiliar participants; record
          completion, assistance, mistakes, time, and whether each person can
          identify currency, amount, actual period, and current vs previous
          result. Use anonymized notes and do not invent or infer observations.
    - [ ] Evaluate the proposed audit targets: at least 4 of 5 complete each
          core task unaided, median time to first valid result under one minute,
          and all participants identify the key result attributes. If a target
          is missed, record the product issue, keep the release gate open, and
          replan remediation and a real retest in the backlog.
  - **Evidence:** dated protocol, anonymized participant-level observation
    sheet, calculation of target outcomes, and any follow-up backlog items.

## Exit criteria

- [ ] Human Product Owner reviews the sprint outcome and evidence; record
      actual acceptance or requested changes before starting the next sprint.

- [ ] Inspect the actual locally served webpage design after this sprint at
      desktop and mobile widths; record captures, changed-state checks, and
      findings under `docs/ux-redesign-evidence/sprint-14/`.
- [ ] Open the sprint PR in `ashcx/sg-investing-v1` with the sprint plan,
      implementation changes, checks/results, and remaining gaps; record its URL.


- [ ] Deterministic financial, parity, worker, static-site, pack integration,
      and route/journey checks pass with reports retained.
- [ ] The locally served integrated candidate passes pack and failure-recovery
      checks using published artifacts; read-only deployed-baseline checks are
      separately labeled and are not presented as candidate UI evidence. No
      redesigned candidate is called deployed without an authorized publish.
- [ ] Audit findings F01–F19 are each linked to evidence and are fixed or
      explicitly resolved in documented scope; no reproduced P1 remains.
- [ ] Required responsive/keyboard/zoom/contrast checks are recorded and no
      financial value loses its label or period on mobile.
- [ ] Existing ledger compatibility and recovery are verified without exposing
      private user ledger contents in the evidence set.
- [ ] Five real unfamiliar participants complete the planned sessions; actual
      outcomes are recorded, and proposed usability targets are met. If targets
      are missed or sessions cannot be run, leave this sprint In progress and
      record the blocker/retest plan.
- [ ] Product Owner reviews the evidence and accepts the release candidate;
      technical agent sign-off is not represented as user acceptance.
- [ ] Sprint evidence is recorded under `docs/ux-redesign-evidence/sprint-14/`
      and roadmap status changes only after every exit gate is checked.

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
- **Acceptance owner:** the human user is Product Owner and owns product and
  release acceptance. Real participant observations are required for the
  usability gate. A prototype, simulated response, or agent-generated summary
  cannot substitute for sessions.
- **Completion evidence:** retain dated reports and anonymized records in
  `docs/ux-redesign-evidence/sprint-14/`. A publish/deploy action is outside
  this plan and requires separate authorization; baseline checks are
  read-only, and redesign candidate checks use a local served build.

## References

- [13 October 2026 UX audit and proposed usability targets](../docs/ux-audit-2026-10-13/README.md)
- [Sprint 13 — Portfolio workflow](sprint-13-portfolio-workflow.md)
- [Sprint 7 release hardening baseline](sprint-7-release-hardening.md)
- [Scrum redesign plan](redesign-scrum-plan.md)

## Execution log

Planning amendment, 15 October 2026: sequential main-instance ownership and
6-SP commitment plus 3-SP stretch recorded. Implementation remains Not started;
no implementation evidence or completed task is claimed by this amendment.

For each task, record date/ID, status, changed files, checks and exact results,
evidence paths, separate self-review findings, blockers, and next sequential
action here before proceeding. Human acceptance is recorded only when given.
