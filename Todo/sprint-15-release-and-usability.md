# Sprint 15 — Release validation and usability

## Goal

Verify the complete redesign against the audit, existing deterministic
calculation contracts, real viewport/accessibility checks, and task-based technical and design review. Record what the evidence supports before making any
release claim.

Status: **Not started**.

## Entry criteria

- [ ] Every Sprint 14 technical exit criterion is checked, including the selected
      visual direction, implemented desktop/mobile overhaul, preserved financial
      context and behavior, design evidence, and sprint PR.

## Depends on

Sprint 14 only, following the completed Sprint 13 portfolio workflow. This is
the final sequential sprint in the redesign plan. Do not
begin release acceptance while any earlier sprint remains incomplete.

## Tasks

Timebox commitment: **S15-US01 + S15-US02 (6 SP)**. **S15-US03 (3 SP) is
stretch**, still required for sprint exit. Execute stories and their tasks in
order, including checks and recorded self-review before advancing.

- [ ] **S15-US01 — Verify financial and static-site behavior end to end** (P1,
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

- [ ] **S15-US02 — Inspect responsive, keyboard, and zoom behavior** (P1, 3 SP;
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

- [ ] **S15-US03 — Verify task clarity and design coherence** (P1, 3 SP;
      owner: main instance; review: subsequent main-instance self-review).
  - **Given** the integrated candidate and the Sprint 14 design direction,
    **when** the main instance performs a separate task-based design review,
    **then** each core journey exposes the required actions and financial
    context, and all findings are tied to actual rendered evidence.
  - Tasks:
    - [ ] Prepare and execute a repeatable task script for: QQQ one-time
          investment and actual dates; monthly contributions and result meaning;
          QQQ/VALL history difference; adding/correcting a portfolio transaction
          and finding its browser-local save location.
    - [ ] Verify every task with deterministic browser evidence and a separate
          visual walkthrough at mobile and desktop widths. Check visible metric
          labels, currencies, amounts, actual periods, current/previous state,
          input recovery, saving status and context-help discoverability.
    - [ ] Review the final result against Sprint 14's selected design and copy
          inventory; correct inconsistencies and redundant ornament/text through
          the owning sprint file. Record each finding, resolution and retest.
    - [ ] Report what technical/design evidence establishes and its limits;
          make no claims about unfamiliar-user success, human comprehension,
          participant timings or task-completion rates without observations.
  - **Evidence:** dated task protocol, browser traces, annotated captures,
    separate self-review findings and repair/retest log. Real-person sessions
    are no longer a completion requirement under the 18 October user amendment.

## Exit criteria

- [ ] Inspect the actual locally served webpage design after this sprint at
      desktop and mobile widths; record captures, changed-state checks, and
      findings under `docs/ux-redesign-evidence/sprint-15/`.
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
- [ ] The four core task scripts pass technical/design review with evidence
      across desktop/mobile; all identified release-blocking issues are repaired
      and retested. No participant or comprehension claims are inferred.
- [ ] Sprint evidence is recorded under `docs/ux-redesign-evidence/sprint-15/`
      and roadmap status changes only after every exit gate is checked.

## Human product acceptance

- [ ] Product Owner reviews the sprint evidence and records actual acceptance
      or requested changes in this sprint log and its PR.

**Pending.** Under the 18 October 2026 authorization, this remains separate from
technical completion and does not block the next sprint after technical exits
pass. Agent verification never establishes human acceptance or authorizes a
merge/deployment. Final release acceptance remains with the Product Owner.

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
  release acceptance. Technical/design review is performed in the main instance;
  it must not be represented as independent review or human usability research.
- **Completion evidence:** retain dated reports and anonymized records in
  `docs/ux-redesign-evidence/sprint-15/`. A publish/deploy action is outside
  this plan and requires separate authorization; baseline checks are
  read-only, and redesign candidate checks use a local served build.

## References

- [13 October 2026 UX audit and proposed usability targets](../docs/ux-audit-2026-10-13/README.md)
- [Sprint 13 — Portfolio workflow](sprint-13-portfolio-workflow.md)
- [Sprint 14 — Interface design overhaul](sprint-14-interface-design-overhaul.md)
- [Sprint 7 release hardening baseline](sprint-7-release-hardening.md)
- [Scrum redesign plan](redesign-scrum-plan.md)

## Execution log

Planning amendment, 15 October 2026: sequential main-instance ownership and
6-SP commitment plus 3-SP stretch recorded. Implementation remains Not started;
no implementation evidence or completed task is claimed by this amendment.

For each task, record date/ID, status, changed files, checks and exact results,
evidence paths, separate self-review findings, blockers, and next sequential
action here before proceeding. Human acceptance is recorded only when given.


Planning amendment, 18 October 2026: moved the former Sprint 14 validation and
usability backlog here as Sprint 15. At the initial move, all stories, tests, five-person sessions,
targets, exit requirements, and limitations are retained; only numbering,
evidence paths, cross-references, and the new Sprint 14 dependency changed.
Implementation remains Not started; this amendment does not satisfy entry gates.


18 October 2026 — user preflight decision: remove the five-person usability gate
and replace it with full technical/design verification. US03 and the matching
exit criterion above now reflect this explicit scope change. Earlier notes
describing an unchanged move from Sprint 14 are historical and superseded only
for the participant requirement. Product Owner acceptance remains separate.


18 October 2026 — Product Owner authorized sequential Sprints 12–15 on verified
technical/design/evidence/PR exits after Sprint 7.5 operational recovery, with
human acceptance pending separately in each PR. Entry/exit and human-review
sections above implement that scope amendment; no checkbox is completed by it.
PR #5 must stay open for review; merge/deployment remain unauthorized. Research
is the explicitly selected design. See the Scrum plan's matching authorization.
