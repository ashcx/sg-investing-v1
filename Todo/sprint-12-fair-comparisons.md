# Sprint 12 — Fair investment comparisons

## Goal

Compare two to six securities using a disclosed common setup and honest usable
dates. Preserve valid results when one security is unsupported, and label every
financial value on small screens. This sprint compares one-time investments
only; multi-security DCA/regular-contribution comparison is outside its scope.

Status: **In progress**.

## Entry criteria

- [x] Every Sprint 11 exit criterion is checked, including the unified
      simulator, accurate price chart, and isolated setup handoff.
      Verified 19 October 2026 against `Todo/sprint-11-investment-simulator.md`:
      every technical exit (unified setup, regular-investing lump sum plus
      contributions, accurate price chart, simulator → comparison isolation,
      evidence directory, sprint PR) is checked. The single open Sprint 11 exit
      is human Product Owner review, which the 18 October 2026 user
      authorization keeps non-blocking and unticked. The Sprint 7.5 Track B
      scheduled-run recovery remains open and externally gated; it does not
      gate this sprint's one-time comparison work because Sprints 10–11 were
      accepted into `main` and evidence for their increments is independent of
      the incremental-update schedule.

## Depends on

Sprint 11 only. Portfolio work in Sprint 13 follows this complete comparison
increment; all tasks remain sequential in the main instance.

## Tasks

Timebox commitment: **S12-US01 + S12-US02 (6 SP)**. **S12-US03 (3 SP) is
stretch**, still required for sprint exit. Execute stories and their tasks in
order, including checks and recorded self-review before advancing.

- [x] **S12-US01 — Choose a fair common date window** (P1, 3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Given** two or more securities and a requested period, **when** the user
    previews or calculates a comparison, **then** usable history and resolved
    dates are checked for each security, with a common-window action or an
    explicit unequal-period warning. (F04)
  - Tasks:
    - [x] Support an explicit simulator setup handoff and a direct-visit state
          with two empty security slots and one shared setup.
    - [x] Keep the handoff one-time only. A regular contribution request remains
          in the simulator with an explanation; never copy a contribution amount
          into initial capital without an explicit user choice.
    - [x] Preview each security's usable history and proposed common window
          before calculation.
    - [x] Compute/display actual resolved start/end dates per result; state
          periods are equal only after actual date equality is checked.
    - [x] Offer a common-available-dates action where supported; otherwise
          explain the unequal window or let the user exclude the unsupported
          security explicitly.
    - [x] Add the QQQ/VALL unequal-history regression with fixed fixtures.
  - **Evidence:** QQQ/VALL fixture output that demonstrates equal-window and
    unequal-window behavior, including the displayed dates and status.

- [x] **S12-US02 — Understand every comparison value on mobile** (P1, 3 SP;
      owner: main instance; review: subsequent main-instance self-review).
  - **Given** a populated comparison at a narrow viewport, **when** a user
    reads a result card, **then** each value names its metric, currency/unit,
    and actual period without relying on a hidden table header. (F06)
  - Tasks:
    - [x] Present SGD ending value and return as primary comparison measures;
          show native-currency return as a clearly secondary measure.
    - [x] Use responsive labeled cards/table; each mobile metric repeats its
          own label, unit, and period.
    - [x] Provide inspectable coverage and warning details per security,
          including a clear status for a partially completed comparison.
    - [x] Verify two to six entries, duplicate identities, removals, invalid
          inputs, partial failures, and pending/previous result states.
  - **Evidence:** browser captures at 320px, 390px, and desktop widths, plus
    metric-label assertions for every card.

- [x] **S12-US03 — Keep comparison setup and partial results honest** (P1,
      3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Given** an edited comparison setup or an unsupported security, **when** a
    request fails or succeeds partially, **then** the view identifies which
    request each result belongs to, retains valid alternatives, and never marks
    the whole comparison equal or complete without evidence. (F03, F15)
  - Tasks:
    - [x] Use the common assumptions and date setup copied from the simulator;
          expose the same assumptions summary and shared warning language.
    - [x] Show per-security loading, invalid, unavailable, failed, and ready
          states while preserving valid completed results with their identity.
    - [x] Check removal/reordering and edits for stale outputs; add deterministic
          browser fixtures after the shared comparison contract is frozen.
  - **Evidence:** partial-failure fixture traces and comparison request-identity
    assertions.

## Exit criteria

- [ ] Human Product Owner reviews the sprint outcome and evidence; record
      actual acceptance or requested changes before starting the next sprint.

- [x] Inspect the actual locally served webpage design after this sprint at
      desktop and mobile widths; record captures, changed-state checks, and
      findings under `docs/ux-redesign-evidence/sprint-12/`.
- [ ] Open the sprint PR in `ashcx/sg-investing-v1` with the sprint plan,
      implementation changes, checks/results, and remaining gaps; record its URL.


- [x] F04 common-window logic verifies actual resolved date equality and
      discloses periods/security; the QQQ/VALL regression passes.
- [x] F06 mobile cards retain the label, unit, and period for every visible
      value at 320px and 390px.
- [x] Two-to-six security comparison supports direct entry, simulator handoff,
      duplicates/removals, partial failures, pending changes, and honest
      coverage/warnings.
- [x] No unsupported security is represented as a completed, equal-period
      result; valid alternatives remain understandable after partial failure.
- [x] Sprint evidence is recorded under `docs/ux-redesign-evidence/sprint-12/`;
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

### 20 October 2026 — takeover, review and comparison contract freeze

User explicitly authorized completing Sprint 12 alone, with numerical,
behavioral and actual Chrome visual verification. Sprint 11 technical/design/PR
exits were re-read: all are checked; human review remains separately pending
under the existing entry amendment. No Sprint 13 task is authorized or started.

Inherited implementation reviewed before reuse: the pure coverage-boundary
helper and card layout are useful foundations. Repairs required: local result
envelopes were read as inner results (blank metrics/dates), warning lookup used
the wrong field, missing dates/source metadata were treated as equality,
Tier-2 coverage was skipped, and provisional results could displace previous
completed output. Existing boundary tests do not exercise these integration
contracts. All inherited task checkboxes correctly remain open.

Frozen presentation contract (no financial-engine or envelope change): each
row retains its security ID, source envelope, actual engine-resolved period,
coverage and warnings. Published windows are previews, not proof of trading-date
equality. Requested dates remain unchanged unless the user explicitly chooses
the shared-window action. Equality requires at least two valid actual periods;
partial results and missing provenance never establish whole-selection equality.
Coverage is resolved against the same Tier-1/Tier-2 origin as calculation.
Completed result identity and content survive edits and failed replacements;
in-flight work has its own clearly labeled submitted setup.

Sequential position: S12-US01. Review/repair inherited handoff, date previews,
actual period verification and fixed QQQ/VALL cases first; record checks and
self-review before proceeding to US02. Chrome connection is currently
unavailable; installation/native-host diagnostics pass, but browser discovery
does not expose Chrome. Actual browser evidence remains required and open.

Planning amendment, 15 October 2026: sequential main-instance ownership and
6-SP commitment plus 3-SP stretch recorded. Implementation remains Not started;
no implementation evidence or completed task is claimed by this amendment.

For each task, record date/ID, status, changed files, checks and exact results,
evidence paths, separate self-review findings, blockers, and next sequential
action here before proceeding. Human acceptance is recorded only when given.

19 October 2026 — entry gate. Sprint 11's technical exits verified directly in
`Todo/sprint-11-investment-simulator.md` (unified simulator, accurate price
chart, isolated simulator → comparison handoff all checked); the only open
Sprint 11 exit is human Product Owner review, which stays unticked and
non-blocking under the 18 October 2026 authorization. Sprint 7.5 Track B
scheduled-run recovery remains open and externally gated in this environment;
it is recorded here as a known dependency gap rather than a Sprint 12 blocker
because this sprint changes only browser-side comparison behaviour and touches
no updater, schema, or workflow code. Status set to In progress; no
implementation task or evidence is claimed by this entry. Next sequential
action: S12-US01.


### 20 October 2026 — S12-US01 complete; separate self-review

Implemented and checked the explicit one-time handoff, two empty selection
slots, isolated custom assumptions, regular initial-only opt-in (never recurring
cash), per-origin coverage preview, explicit shared-date action and actual
engine date equality. Fixed stale hidden DCA dates in the inherited handoff.
The common action proposes requested-window intersection, or the full overlap
when the request misses it; requests are never silently shortened. Unknown
coverage can reach engine validation; explicitly unavailable rows remain labeled.

Checks: compare-window selftest passes all 11 named cases; compare-result
selftest passes four independently calculated amount/scenario/date cases plus
actual QQQ/VALL equal/unequal-period, envelope, partial and source checks;
Python independently passes the same four expected-value cases. UI contract
harness runs actual app functions and verifies slots, copy isolation, regular
opt-in, correct simulator dates and Tier-2 lookup. Initial fixture construction
omitted required currency/source fields; fixture schema was corrected without
changing financial expectations. Evidence: sprint-12/{window-tests,result-tests,
ui-contract-tests,numerical-python}.txt and tests/fixtures/redesign/sprint-12.json.

Self-review: shared-window preview must never be called an actual period;
missing dates, one successful security and missing provenance cannot prove
whole-selection equality. Envelope normalization preserves source metadata and
rejects incomplete or wrong-security output. No engine/envelope contract changed.
Actual Chrome review is still pending at the sprint exit; this deterministic
harness makes no visual/focus/accessibility claim. Next sequential action:
S12-US02 cards, repeated metric context and inspectable warnings.


### 20 October 2026 — S12-US02 complete; separate self-review

Reviewed the inherited labeled-card implementation and verified every metric
against actual worker output in Chrome: SGD ending value and total return lead;
native return is secondary. Every metric repeats its currency/unit and actual
period. Warning disclosures expose pack notes, coverage, snapshot, methodology
and calculation source and work with Enter. Desktop unequal-period and exact
320/390 CSS-pixel captures are retained in the sprint evidence folder;
`mobile-labels.json` records all six metric labels/periods and confirms no page
overflow (scroll width equals viewport width). Browser zoom affected the initial
viewport override; exact device metrics were used for the retained mobile proof.

Checks: compare UI controller and renderer selftests pass, including two/six
entries, duplicates, invalid capital/dates, unavailable/failed rows, prior output
retention and late-response rejection. Pack→worker→card pipeline passes all four
independent financial cases plus Tier-2 recovery. Separate self-review confirms
no hidden-header dependence and no claim that a published overlap guarantees
actual equality. Next: S12-US03 browser changed-state and partial-result review.


### 20 October 2026 — S12-US03 complete; separate self-review

Verified shared assumptions, copied setup isolation, per-security loading/queued,
ready, unavailable and failed output; invalid setup retains previous results.
Actual Chrome journeys demonstrate direct entry, explicit equal-window action,
six selections with four valid alternatives (including Tier-2), missing CHF FX,
503 pack failure, zero-capital rejection, removal/re-addition changing order,
new capital, all-failed replacement preservation, one-time setup copy and regular
contribution guard. Evidence: partial-result.txt, changed-states.json,
all-failed.json, handoff.json and desktop equal/partial/previous captures.
Controller tests deterministically hold and release old requests to prove stale
response rejection after edits/reordering; browser checks exercise the actual
pack loader, worker and display with synthetic data, without production writes.

Self-review: partial completion is never described as whole-selection equal;
failed rows show no invented metrics. The retained result still identifies its
original capital, selection, dates and assumptions when the draft changes or
replacement fails. Warning/provenance content survives envelope normalization.
No financial calculation, result-envelope or worker-protocol contract changed.

### 20 October 2026 — final checks and Sprint Review preparation

All three stories and technical/design exits are complete. Python: 281 passed,
8 opt-in smoke deselected. Browser engine: 68 selftests, 27 golden fixtures,
90 worker checks, 19 property groups / 1,473 cases and initial-lump cases pass.
Comparison window/result/controller/pipeline checks pass; static-site checks,
module syntax, changed-test Ruff and whitespace checks pass. Pack integration
against the full production snapshot is not claimed: generated packs are absent;
the fixed-data pipeline does exercise the real loader and worker offline.
Chrome captures and findings are indexed in the evidence README.

Retrospective: retain the real pack→worker→renderer pipeline regression because
boundary-only tests missed the inherited envelope bug; measure CSS viewport
width directly before labeling mobile captures. Human Product Owner acceptance
remains pending and is not inferred from this request to implement/test/PR.
Roadmap remains In progress under its all-exits rule. Next action: publish the
Sprint 12 PR, then present evidence for product review. No Sprint 13, merge or
deployment is performed.

Chrome delayed-request follow-up: `loading.txt` demonstrates ready and calculating
rows together. Editing capital before the 1.5-second fixture failure clears
progress; `cancelled.json` confirms the late response leaves the original
completed result intact. No additional implementation was needed.
