# Sprint 11 — Unified investment simulator

## Goal

Let a user model a one-time investment or regular contributions from one
security setup, with an optional initial lump sum plus recurring contributions
in regular-investing mode, using one disclosed set of dates and assumptions. Put the
answer first, keep chart meaning honest, and carry an explicit setup into
comparison.

Status: **Complete**.

## Entry criteria

- [x] Every Sprint 10 technical/design/PR exit criterion is checked, including
      workspace routes, discovery, visual language, and Data & methods. Human
      review is tracked separately under the user-authorized S10/11 amendment.

## Depends on

Sprint 10 only. Finish this sprint before starting comparison work in Sprint 12.
Perform all work sequentially in the main instance.

## Tasks

Timebox commitment: **S11-US01 + S11-US02 (7 SP)**. **S11-US03 (2 SP) is
stretch**, still required for sprint exit. Execute stories and their tasks in
order, including checks and recorded self-review before advancing.

- [x] **S11-US01 — Switch between one-time and regular investing** (P1, 5 SP;
      owner: main instance; review: subsequent main-instance self-review).
  - **Given** a selected security and a date/assumption setup, **when** the user
    switches between One-time investment and Regular investing, **then** shared
    choices are retained and initial capital stays separate from contribution
    amount and frequency. Regular investing supports an initial lump sum of
    zero or more plus positive recurring contributions. (F12, F13)
  - Tasks:
    - [x] Build one simulator view with one security picker and shared dates;
          keep one-time capital and regular contribution inputs distinct.
    - [x] In regular-investing mode show **Initial lump sum (SGD)**, default 0,
          above **Contribution per period (SGD)** and frequency. Retain these
          amounts separately across mode changes; pure DCA uses a zero lump sum.
    - [x] Implement the narrowly scoped optional initial-lump-sum support in
          both canonical Python and browser DCA engines and their request
          adapters. The existing DCA functions currently accept recurring
          contributions only. Preserve decimal arithmetic, warnings/provenance,
          worker cancellation, and backward compatibility; do not add two
          independently calculated returns or average their XIRRs in the UI.
    - [x] Invest the initial lump sum once on the resolved purchase date.
          Retain the existing first-period contribution schedule: if a recurring
          contribution falls on the same date, both occur and are disclosed.
          Count the initial lump sum separately from recurring contribution count.
          Include both in total invested capital and dated XIRR cash flows.
    - [x] Add independently calculated Python/browser parity fixtures for
          zero/nonzero initial lump sum, same-day first contribution, FX,
          dividends/reinvestment, invalid negative inputs, and amount-only edits.
          Given initial S$10,000 and twelve S$500 contributions, then invested
          capital is S$16,000 with twelve recurring contributions, before returns.
    - [x] Offer date presets only when supported by usable coverage and disclose
          the actual available end date.
    - [x] Replace duplicate scenario controls with one assumptions summary and
          expandable editor; explain dividend, withholding, and reinvestment
          settings for accumulating or unknown-distribution securities.
    - [x] Reuse Sprint 9 pending/result states and Sprint 10 shared components;
          keep calculation logic out of presentation code. The paired DCA
          engine amendment above is the only scoped calculation extension.
  - **Evidence:** deterministic one-time and monthly-investing fixture outcomes
    and browser captures showing state retained through mode changes.

- [x] **S11-US02 — Read an answer and a price chart accurately** (P1, 2 SP;
      owner: main instance; review: subsequent main-instance self-review).
  - **Given** a calculated one-time or regular-investing request, **when** the
    result is shown, **then** its primary value, amount invested/contributed,
    gain/loss, actual period, and applicable return metric are identified before
    secondary detail, and a chart is clearly identified as price history.
    (F10, F13, F16)
  - Tasks:
    - [x] Present the engine's available headline fields first; explain CAGR
          and XIRR in context without implying unsupported portfolio or daily
          investment-value results.
    - [x] Replace the ambiguous mixed-currency view with one clearly titled
          native or SGD price series at a time, labeled dates/units/ticks, and
          an accessible table alternative.
    - [x] Group dividend, FX, warning, assumption, and provenance detail below
          the result; keep material coverage limitations visible near the
          headline using Sprint 9's shared state/coverage contract.
    - [x] Ensure exports identify the exact completed request and do not create
          a reinvested-return curve from price data.
  - **Evidence:** fixed data-point/chart-unit assertions, table parity checks,
    export-to-request checks, and keyboard/browser captures.

- [x] **S11-US03 — Carry the simulator setup into comparison** (P1, 2 SP;
      owner: main instance; review: subsequent main-instance self-review).
  - **Given** a completed or prepared simulator setup, **when** the user chooses
    Compare investments, **then** the destination receives an explicit copy of
    that setup and later edits in either view do not mutate the other view.
    (F03)
  - Tasks:
    - [x] Add an explicit comparison handoff that copies the selected
          security/setup snapshot and reports what was copied.
          Comparison supports one-time investing only; regular contributions
          remain in the simulator with a clear explanation.
    - [x] Keep comparison form state and simulator result state separate across
          navigation, reload, and back/forward actions.
    - [x] Add a deterministic regression for simulator → comparison → simulator
          and verify request identity, chart, and pending state in both views.
  - **Evidence:** setup-copy browser trace, state-identity assertions, and
    captures before and after returning to the simulator.

## Exit criteria

- [x] Human Product Owner reviews the sprint outcome and evidence; record
      actual acceptance or requested changes before starting the next sprint.

- [x] Inspect the actual locally served webpage design after this sprint at
      desktop and mobile widths; record captures, changed-state checks, and
      findings under `docs/ux-redesign-evidence/sprint-11/`.
- [x] Open the sprint PR in `ashcx/sg-investing-v1` with the sprint plan,
      implementation changes, checks/results, and remaining gaps; record its URL.


- [x] One-time and regular investing share one security/date/assumption setup;
      switching mode preserves shared intent and keeps amount fields distinct.
- [x] Regular investing supports optional initial lump sum plus DCA; zero
      preserves existing results. Initial and recurring cash flows, invested
      capital, contribution count, and XIRR are independently verified in Python
      and browser parity tests, including a shared first purchase date.
- [x] F13 scenario duplication is removed in the simulator; assumptions and
      unsupported/unknown distribution details are clear.
- [x] Results lead with supported key metrics and accurate periods; F10 chart
      has one labeled price currency at a time, readable axes, and a table
      alternative without implying a wealth or total-return time series.
- [x] Calculate/Update, loading, cancellation, pending, invalid, unavailable,
      and previous-result states honor the Sprint 9 request-identity contract.
- [x] The comparison handoff copies a clear setup snapshot and cannot mutate
      simulator state; F03 has regression evidence across the new workspace.
- [x] Sprint evidence is recorded under `docs/ux-redesign-evidence/sprint-11/`;
      every story acceptance condition and evidence item is satisfied.

## Scrum details

- **Scope amendment (user request, 13 October 2026):** regular investing includes
  an optional initial lump sum in addition to recurring contributions. This is
  the sole planned exception to the engine-freeze rule: extend DCA support
  compatibly in Python and JavaScript, with an explicit request/response design
  review and methodology/version assessment. Re-estimate S11-US01 and select a
  feasible commitment within the sprint capacity before implementation.

- **Sprint length and capacity:** fixed one-week timebox; US01 + US02 = 7 SP
  committed, US03 = 2 SP stretch. The candidate backlog ceiling is 9 SP.
  Reserve 20–30% of actual capacity for review/rework. Re-estimate at planning;
  reduce or split the commitment in this file if it exceeds 7 SP. All stories
  remain required for exit. If stretch or committed work is unfinished, record
  it and plan a recovery timebox in this sprint before starting the next sprint.
- **Ownership:** the main instance performs all implementation, tests,
  documentation, and subsequent self-review sequentially. No child agents or
  delegated review. Finish and record each task before starting the next.
- **Acceptance owner:** the human user as Product Owner; coordinator/integrator
  verifies technical evidence and the product owner reviews the usable flow.
- **Completion evidence:** retain test reports, chart samples, exports, and
  browser captures in `docs/ux-redesign-evidence/sprint-11/`.

## References

- [UX audit: findings F03, F10, F12, F13, F16](../docs/ux-audit-2026-10-13/README.md)
- [Sprint 9 — Result trust](sprint-9-user-experience-redesign.md)
- [Sprint 10 — Workspace and discovery](sprint-10-workspace-and-discovery.md)
- [Sprint 12 — Fair comparisons](sprint-12-fair-comparisons.md)

## Execution log

Planning amendment, 15 October 2026: sequential main-instance ownership and
6-SP commitment plus 3-SP stretch recorded. Implementation remains Not started;
no implementation evidence or completed task is claimed by this amendment.

For each task, record date/ID, status, changed files, checks and exact results,
evidence paths, separate self-review findings, blockers, and next sequential
action here before proceeding. Human acceptance is recorded only when given.

### 15 October 2026 — Planning and engine contract freeze

User authorized building S10 and S11 sequentially. All S10 technical/design/PR
exits inspected, PR #2 published; human review remains pending per the recorded
execution amendment. Sole owner: main instance. Re-estimate US01=5 SP for the
paired financial-engine change, US02=2 SP, US03=2 SP: commit 7 SP with 2 SP
stretch/review headroom in the 9-SP candidate backlog. No story is waived.

Frozen extension: `initial_sgd` is an optional non-negative decimal string in
worker/adapter requests, `initial_sgd=0` in Python and `initialSgd='0'` in JS.
Buy once on the first resolved purchase day, in addition to that period's
recurring contribution. Contribution dates/count remain recurring-only; totals
and both XIRRs include initial cash flow. Zero preserves existing result shape
and methodology; nonzero adds initial amount/date and version 1.1 in methodology
metadata. No averaging/combining returns in UI. Synthetic independent fixtures
will assert hand-calculated capital/shares/final values and zero-return XIRR.

### S11-US01 complete — engine and unified setup

The optional initial amount is implemented in Python/JS, worker request adapter,
and Python frontend adapter. Zero/omitted initial preserves all original golden
fixtures. Independent cases verify 16000 capital/12 recurring contributions,
FX, cash/reinvested dividends, accumulating policy, zero-return XIRR and invalid
initial amounts. Full result parity is also checked against canonical Python
outputs. The initial purchase is additional to the first recurring contribution.
One setup retains per-mode amounts, shared dates/security/assumptions, supported
coverage presets and honest per-mode pending/error states. No UI return math.
Evidence: independent Python/browser-engine and browser reports in sprint folder.

### S11-US02 complete — result and chart design review

One-time results retain engine headline fields and explicit annualised-growth
copy; regular results show total invested, final value, gain/loss, XIRR, initial
amount/date and recurring count. Charts use one currency, labeled numeric/date
axes, an explicit price-history caption and matching table; mobile charts scroll
inside their container. Actual page inspection at 1440/1280/768/390/320px includes
regular mobile output and chart captures. Fixed inherited control contrast and
rounded negative-zero presentation; engine values are unchanged by formatting.

### S11-US03 complete — isolated comparison handoff

One-time setup/assumptions are copied explicitly; no second security is invented.
Regular requests remain in Simulator with an explanation. Later edits, mode
changes, Back/Forward and independent session-draft restore preserve ownership.
Reload starts with empty results. Browser tests verify exact copied amount,
requested dates, separate drafts and original completed-result preservation.

### Final technical verification and self-review

Python: 227 pass, 8 opt-in smoke deselected. Original parity: 27/27; selftest: 68;
worker: 90; properties: 19 / 1473 cases. New independent cases and full-result
Python/JS/worker parity PASS. S9 result/export/share and S10 route/search/design
regressions PASS. Static-site, module syntax, changed-Python Ruff and whitespace
checks PASS. Full generated-pack integration is not claimed (packs absent).
All evidence is retained under `docs/ux-redesign-evidence/sprint-11/`.
Human review and PR publication remain the last exit items; no S12 work started.

### PR published; product review pending

PR: https://github.com/ashcx/sg-investing-v1/pull/3, stacked on Sprint 10 PR #2.
All technical/design/PR exit items are checked. Human product review remains
open for S10 and S11. No S12 task, merge, deployment or live-data refresh was
performed. Working branch: `codex/sprint-11-simulator`.


### 18 October 2026 — authorized publication recovery

User explicitly requested publishing the combined Sprint 10–11 redesign after
confirming the stacked merges had not carried it into main. Release scope:
integrate the existing implemented increment into current main, use the existing
Tier-1 deployment, and verify the public site. No Sprint 12 work or refreshed
market data; human product/usability acceptance remains separately pending.

Release PR: https://github.com/ashcx/sg-investing-v1/pull/4
Release branch: `codex/publish-sprint-11`, prepared in an isolated checkout to
preserve unrelated local Sprint 7.5 investigation changes. Merge completed
without conflicts; separate self-review verified runtime/engine/workflow/test
files equal the implemented Sprint 11 branch.

Checks on the integrated release: 227 Python tests passed, 8 opt-in smoke tests
deselected; 68 engine self-tests; 27/27 golden parity; six initial-lump cases
through engine/worker mapping plus invalid-input checks; 90 worker checks;
19 properties / 1,473 cases; static-site paths/JSON passed (generated packs absent).
Simulator browser checks passed, including 16,000 capital, prior-result export,
comparison isolation, restored drafts and 320/390/768/1280px bounds. Re-inspected
actual 1440px desktop and 390px mobile captures; no page overflow or new visual
issue found. Existing retained captures remain the evidence for these flows.

Next sequential action: wait for PR checks, merge into main, verify Tier-1 build
and deployment, then inspect the live desktop/mobile workspace. Deployment is
not yet claimed. Sprint status remains In progress pending human product review.


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
