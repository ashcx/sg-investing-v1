# Sprint 13 — Guided portfolio workflow

## Goal

Help a user create, correct, import, and review a local portfolio ledger without
invented transactions or unexplained fields. Keep the existing transaction and
weighted-average-cost calculation semantics and avoid unsupported portfolio
claims.

Status: **Not started**.

## Entry criteria

- [ ] Every Sprint 12 exit criterion is checked, including honest comparison
      periods, labeled mobile metrics, partial-failure states, and retained
      request identity.

## Depends on

Sprint 12 only. Sprint 14 interface design follows this complete portfolio
increment; Sprint 15 then validates the integrated redesign. No sprint may run
alongside this one.

## Tasks

Timebox commitment: **S13-US01 + S13-US02 (6 SP)**. **S13-US03 (3 SP) is
stretch**, still required for sprint exit. Execute stories and their tasks in
order, including checks and recorded self-review before advancing.

- [ ] **S13-US01 — Start empty or restore a saved ledger safely** (P1, 3 SP;
      owner: main instance; review: subsequent main-instance self-review).
  - **Given** a new browser or a browser with a previously saved ledger,
    **when** the portfolio view opens, **then** a new user sees an honest empty
    state and an existing ledger restores without data loss, with its browser-
    local save status clear. (F11)
  - Tasks:
    - [ ] Replace unexplained sample BUY defaults with Add transaction and
          Import ledger actions; preserve existing saved ledger compatibility.
    - [ ] Show saved/saving/error state and explain that storage is local to
          this browser; do not imply cloud synchronization.
    - [ ] Make import validate and preview the content before any replacement;
          keep export compatible with existing formats.
    - [ ] Add deterministic save/reload and legacy-ledger restoration fixtures.
  - **Evidence:** fixture ledger before/after snapshots, import preview traces,
    and browser evidence for empty and restored states.

- [ ] **S13-US02 — Enter and correct the right transaction fields** (P1, 3 SP;
      owner: main instance; review: subsequent main-instance self-review).
  - **Given** a user adding, editing, or deleting a BUY, SELL, DIVIDEND,
    CASH_DEPOSIT, or CASH_WITHDRAWAL, **when** the transaction form changes
    type, **then** it exposes only relevant, explicitly labeled fields and lets
    the user recover a deletion. (F11, F16)
  - Tasks:
    - [ ] Build a labeled type/date form with security, quantity, transaction
          total, and currency only where relevant; explain that transaction
          cash is the total rather than unit price.
    - [ ] Use stable row IDs and support edit, per-row delete, and undo; keep
          engine transaction semantics unchanged.
    - [ ] Link validation errors to the affected row/field and avoid hidden
          default values that can be mistaken for user entries.
    - [ ] Add deterministic fixtures for every transaction type, correction,
          delete/undo, and invalid values after the form contract is frozen.
  - **Evidence:** accessible-name and field-relevance assertions, transaction
    fixture results, and add/edit/delete/undo browser trace.

- [ ] **S13-US03 — Read holdings and ledger details at any width** (P1/P2,
      3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Given** a populated portfolio with holdings, cash, and P&L, **when** the
    user reviews it on a narrow screen or changes the valuation date, **then**
    transactions and holdings remain readable and the result explains its
    usable valuation coverage without claiming unsupported analytics. (F11,
    F16)
  - Tasks:
    - [ ] Use responsive transaction cards and holding summaries with visible
          labels instead of requiring a wide spreadsheet.
    - [ ] Default the valuation date to a disclosed usable date and show
          date/coverage errors on the affected result and transaction context.
    - [ ] Retain holdings, cash, weighted-average cost (Average cost), and
          realized/unrealized P&L only; keep return, allocation, risk, and
          wealth-over-time claims out of the UI.
    - [ ] Verify buy/sell/dividend/cash flows, save/reload, import/export, and
          unavailable valuation coverage at mobile and desktop sizes.
  - **Evidence:** fixed transaction outputs, accessible mobile captures, and
    import/export compatibility report.

## Exit criteria

- [ ] Human Product Owner reviews the sprint outcome and evidence; record
      actual acceptance or requested changes before starting the next sprint.

- [ ] Inspect the actual locally served webpage design after this sprint at
      desktop and mobile widths; record captures, changed-state checks, and
      findings under `docs/ux-redesign-evidence/sprint-13/`.
- [ ] Open the sprint PR in `ashcx/sg-investing-v1` with the sprint plan,
      implementation changes, checks/results, and remaining gaps; record its URL.


- [ ] F11 empty-state, restore, labeled transaction entry, edit/delete/undo,
      import preview, local save status, and mobile readability are evidenced.
- [ ] Existing saved ledgers remain readable and export/import compatible;
      no destructive clearing or replacement happens without a clear recovery
      path.
- [ ] Current engine transaction semantics, weighted-average cost, holdings,
      cash, and P&L outputs are preserved; unsupported claims are absent.
- [ ] Every transaction control has an accessible name, relevant fields change
      with type, and errors identify the affected transaction.
- [ ] Sprint evidence is recorded under `docs/ux-redesign-evidence/sprint-13/`;
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
- **Acceptance owner:** the human user as Product Owner. The coordinator checks
  data-preservation evidence; only the actual owner of the existing ledger can
  confirm their personal data is intact if a live user ledger is used.
- **Completion evidence:** store anonymized fixtures, compatibility results,
  accessibility checks, and captures in
  `docs/ux-redesign-evidence/sprint-13/`; never include private ledger contents.

## References

- [UX audit: findings F11 and F16](../docs/ux-audit-2026-10-13/README.md)
- [Portfolio static workflow](../docs/portfolio-static.md)
- [Sprint 12 — Fair comparisons](sprint-12-fair-comparisons.md)
- [Sprint 14 — Interface design overhaul](sprint-14-interface-design-overhaul.md)
- [Sprint 15 — Release and usability](sprint-15-release-and-usability.md)

## Execution log

Planning amendment, 15 October 2026: sequential main-instance ownership and
6-SP commitment plus 3-SP stretch recorded. Implementation remains Not started;
no implementation evidence or completed task is claimed by this amendment.

For each task, record date/ID, status, changed files, checks and exact results,
evidence paths, separate self-review findings, blockers, and next sequential
action here before proceeding. Human acceptance is recorded only when given.
