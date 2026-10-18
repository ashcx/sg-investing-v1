# Sprint 12 — Fair investment comparisons

## Goal

Compare two to six securities using a disclosed common setup and honest usable
dates. Preserve valid results when one security is unsupported, and label every
financial value on small screens. This sprint compares one-time investments
only; multi-security DCA/regular-contribution comparison is outside its scope.

Status: **Not started**.

## Entry criteria

- [ ] Sprint 7.5 operational recovery is verified against its actual exit
      evidence, including scheduled successes and publication checks. PR #5
      stays open for review until the Product Owner authorizes its merge.
- [ ] Every Sprint 11 technical/design/PR exit criterion is checked, including
      the unified simulator, accurate price chart, and isolated setup handoff.
      Its pending human acceptance does not block this authorized progression.

## Depends on

Sprint 7.5 operational recovery and Sprint 11 technical/design/PR completion.
Portfolio work in Sprint 13 follows this technically complete comparison
increment; all tasks remain sequential in the main instance.

## Tasks

Timebox commitment: **S12-US01 + S12-US02 (6 SP)**. **S12-US03 (3 SP) is
stretch**, still required for sprint exit. Execute stories and their tasks in
order, including checks and recorded self-review before advancing.

- [ ] **S12-US01 — Choose a fair common date window** (P1, 3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Given** two or more securities and a requested period, **when** the user
    previews or calculates a comparison, **then** usable history and resolved
    dates are checked for each security, with a common-window action or an
    explicit unequal-period warning. (F04)
  - Tasks:
    - [ ] Support an explicit simulator setup handoff and a direct-visit state
          with two empty security slots and one shared setup.
    - [ ] Keep the handoff one-time only. A regular contribution request remains
          in the simulator with an explanation; never copy a contribution amount
          into initial capital without an explicit user choice.
    - [ ] Preview each security's usable history and proposed common window
          before calculation.
    - [ ] Compute/display actual resolved start/end dates per result; state
          periods are equal only after actual date equality is checked.
    - [ ] Offer a common-available-dates action where supported; otherwise
          explain the unequal window or let the user exclude the unsupported
          security explicitly.
    - [ ] Add the QQQ/VALL unequal-history regression with fixed fixtures.
  - **Evidence:** QQQ/VALL fixture output that demonstrates equal-window and
    unequal-window behavior, including the displayed dates and status.

- [ ] **S12-US02 — Understand every comparison value on mobile** (P1, 3 SP;
      owner: main instance; review: subsequent main-instance self-review).
  - **Given** a populated comparison at a narrow viewport, **when** a user
    reads a result card, **then** each value names its metric, currency/unit,
    and actual period without relying on a hidden table header. (F06)
  - Tasks:
    - [ ] Present SGD ending value and return as primary comparison measures;
          show native-currency return as a clearly secondary measure.
    - [ ] Use responsive labeled cards/table; each mobile metric repeats its
          own label, unit, and period.
    - [ ] Provide inspectable coverage and warning details per security,
          including a clear status for a partially completed comparison.
    - [ ] Verify two to six entries, duplicate identities, removals, invalid
          inputs, partial failures, and pending/previous result states.
  - **Evidence:** browser captures at 320px, 390px, and desktop widths, plus
    metric-label assertions for every card.

- [ ] **S12-US03 — Keep comparison setup and partial results honest** (P1,
      3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Given** an edited comparison setup or an unsupported security, **when** a
    request fails or succeeds partially, **then** the view identifies which
    request each result belongs to, retains valid alternatives, and never marks
    the whole comparison equal or complete without evidence. (F03, F15)
  - Tasks:
    - [ ] Use the common assumptions and date setup copied from the simulator;
          expose the same assumptions summary and shared warning language.
    - [ ] Show per-security loading, invalid, unavailable, failed, and ready
          states while preserving valid completed results with their identity.
    - [ ] Check removal/reordering and edits for stale outputs; add deterministic
          browser fixtures after the shared comparison contract is frozen.
  - **Evidence:** partial-failure fixture traces and comparison request-identity
    assertions.

## Exit criteria

- [ ] Inspect the actual locally served webpage design after this sprint at
      desktop and mobile widths; record captures, changed-state checks, and
      findings under `docs/ux-redesign-evidence/sprint-12/`.
- [ ] Open the sprint PR in `ashcx/sg-investing-v1` with the sprint plan,
      implementation changes, checks/results, and remaining gaps; record its URL.


- [ ] F04 common-window logic verifies actual resolved date equality and
      discloses periods/security; the QQQ/VALL regression passes.
- [ ] F06 mobile cards retain the label, unit, and period for every visible
      value at 320px and 390px.
- [ ] Two-to-six security comparison supports direct entry, simulator handoff,
      duplicates/removals, partial failures, pending changes, and honest
      coverage/warnings.
- [ ] No unsupported security is represented as a completed, equal-period
      result; valid alternatives remain understandable after partial failure.
- [ ] Sprint evidence is recorded under `docs/ux-redesign-evidence/sprint-12/`;
      every story acceptance condition and evidence item is satisfied.

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
- **Acceptance owner:** human user as Product Owner. Coordinator/integrator
  reviews the evidence and does not infer acceptance from a green test alone.
- **Completion evidence:** save fixed comparison inputs, expected actual dates,
  test reports, and viewport captures under
  `docs/ux-redesign-evidence/sprint-12/`.

## References

- [UX audit: findings F04, F06, F15](../docs/ux-audit-2026-10-13/README.md)
- [Sprint 11 — Investment simulator](sprint-11-investment-simulator.md)
- [Sprint 13 — Portfolio workflow](sprint-13-portfolio-workflow.md)
- [Scrum redesign plan](redesign-scrum-plan.md)

## Execution log

Planning amendment, 15 October 2026: sequential main-instance ownership and
6-SP commitment plus 3-SP stretch recorded. Implementation remains Not started;
no implementation evidence or completed task is claimed by this amendment.

For each task, record date/ID, status, changed files, checks and exact results,
evidence paths, separate self-review findings, blockers, and next sequential
action here before proceeding. Human acceptance is recorded only when given.


18 October 2026 — Product Owner authorized sequential Sprints 12–15 on verified
technical/design/evidence/PR exits after Sprint 7.5 operational recovery, with
human acceptance pending separately in each PR. Entry/exit and human-review
sections above implement that scope amendment; no checkbox is completed by it.
PR #5 must stay open for review; merge/deployment remain unauthorized. Research
is the explicitly selected design. See the Scrum plan's matching authorization.


Planning verification, 18 October 2026: eight amended planning files checked;
58 local Markdown links resolve. Sprints 12–15 retain required sections,
Not started status and unchecked implementation gates; human acceptance is
separate and pending. Sprint 7.5 operational prerequisite and separate PRs are
preserved. Whitespace checks pass. Separate self-review confirms planning-only
changes; no runtime or financial code changed, so runtime tests were not repeated.
