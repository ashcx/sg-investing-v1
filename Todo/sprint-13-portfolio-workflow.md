# Sprint 13 — Guided portfolio workflow

## Goal

Help a user create, correct, import, and review a local portfolio ledger without
invented transactions or unexplained fields. Keep the existing transaction and
weighted-average-cost calculation semantics and avoid unsupported portfolio
claims.

Status: **In progress**.

## Entry criteria

- [x] Every Sprint 12 exit criterion is checked, including honest comparison
      periods, labeled mobile metrics, partial-failure states, and retained
      request identity.

## Depends on

Sprint 12 only. This ordering is deliberate; Sprint 14 release validation waits
for the portfolio increment. No sprint may run alongside this one.

## Tasks

Timebox commitment: **S13-US01 + S13-US02 (6 SP)**. **S13-US03 (3 SP) is
stretch**, still required for sprint exit. Execute stories and their tasks in
order, including checks and recorded self-review before advancing.

- [x] **S13-US01 — Start empty or restore a saved ledger safely** (P1, 3 SP;
      owner: main instance; review: subsequent main-instance self-review).
  - **Given** a new browser or a browser with a previously saved ledger,
    **when** the portfolio view opens, **then** a new user sees an honest empty
    state and an existing ledger restores without data loss, with its browser-
    local save status clear. (F11)
  - Tasks:
    - [x] Replace unexplained sample BUY defaults with Add transaction and
          Import ledger actions; preserve existing saved ledger compatibility.
    - [x] Show saved/saving/error state and explain that storage is local to
          this browser; do not imply cloud synchronization.
    - [x] Make import validate and preview the content before any replacement;
          keep export compatible with existing formats.
    - [x] Add deterministic save/reload and legacy-ledger restoration fixtures.
  - **Evidence:** fixture ledger before/after snapshots, import preview traces,
    and browser evidence for empty and restored states.

- [x] **S13-US02 — Enter and correct the right transaction fields** (P1, 3 SP;
      owner: main instance; review: subsequent main-instance self-review).
  - **Given** a user adding, editing, or deleting a BUY, SELL, DIVIDEND,
    CASH_DEPOSIT, or CASH_WITHDRAWAL, **when** the transaction form changes
    type, **then** it exposes only relevant, explicitly labeled fields and lets
    the user recover a deletion. (F11, F16)
  - Tasks:
    - [x] Build a labeled type/date form with security, quantity, transaction
          total, and currency only where relevant; explain that transaction
          cash is the total rather than unit price.
    - [x] Use stable row IDs and support edit, per-row delete, and undo; keep
          engine transaction semantics unchanged.
    - [x] Link validation errors to the affected row/field and avoid hidden
          default values that can be mistaken for user entries.
    - [x] Add deterministic fixtures for every transaction type, correction,
          delete/undo, and invalid values after the form contract is frozen.
  - **Evidence:** accessible-name and field-relevance assertions, transaction
    fixture results, and add/edit/delete/undo browser trace.

- [x] **S13-US03 — Read holdings and ledger details at any width** (P1/P2,
      3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Given** a populated portfolio with holdings, cash, and P&L, **when** the
    user reviews it on a narrow screen or changes the valuation date, **then**
    transactions and holdings remain readable and the result explains its
    usable valuation coverage without claiming unsupported analytics. (F11,
    F16)
  - Tasks:
    - [x] Use responsive transaction cards and holding summaries with visible
          labels instead of requiring a wide spreadsheet.
    - [x] Default the valuation date to a disclosed usable date and show
          date/coverage errors on the affected result and transaction context.
    - [x] Retain holdings, cash, weighted-average cost (Average cost), and
          realized/unrealized P&L only; keep return, allocation, risk, and
          wealth-over-time claims out of the UI.
    - [x] Verify buy/sell/dividend/cash flows, save/reload, import/export, and
          unavailable valuation coverage at mobile and desktop sizes.
  - **Evidence:** fixed transaction outputs, accessible mobile captures, and
    import/export compatibility report.

## Exit criteria

- [ ] Human Product Owner reviews the sprint outcome and evidence; record
      actual acceptance or requested changes before starting the next sprint.

- [x] Inspect the actual locally served webpage design after this sprint at
      desktop and mobile widths; record captures, changed-state checks, and
      findings under `docs/ux-redesign-evidence/sprint-13/`.
- [x] Open the sprint PR in `ashcx/sg-investing-v1` with the sprint plan,
      implementation changes, checks/results, and remaining gaps; record its URL.


- [x] F11 empty-state, restore, labeled transaction entry, edit/delete/undo,
      import preview, local save status, and mobile readability are evidenced.
- [x] Existing saved ledgers remain readable and export/import compatible;
      no destructive clearing or replacement happens without a clear recovery
      path.
- [x] Current engine transaction semantics, weighted-average cost, holdings,
      cash, and P&L outputs are preserved; unsupported claims are absent.
- [x] Every transaction control has an accessible name, relevant fields change
      with type, and errors identify the affected transaction.
- [x] Sprint evidence is recorded under `docs/ux-redesign-evidence/sprint-13/`;
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
- [Sprint 14 — Release and usability](sprint-14-release-and-usability.md)

## Execution log

Planning amendment, 15 October 2026: sequential main-instance ownership and
6-SP commitment plus 3-SP stretch recorded. Implementation remains Not started;
no implementation evidence or completed task is claimed by this amendment.

For each task, record date/ID, status, changed files, checks and exact results,
evidence paths, separate self-review findings, blockers, and next sequential
action here before proceeding. Human acceptance is recorded only when given.


### Authorized sequential implementation, 28 October 2026

Sprint 12 exit checklist was verified and rechecked with fresh comparison
engine/controller/worker and Chrome tests; review PR #10 is published.
User explicitly requests continued technical progression after each tested PR.
Human product review may follow increments; no human acceptance is inferred.
S14 may begin after all S13 technical/design/PR gates, while the human
product review exit remains separately tracked. Final release acceptance and
five unfamiliar participant sessions remain mandatory.

Grounding/design: existing DOM ledger rows are canonical transaction fields
with decimal strings. Keep the engine and IndexedDB schema. Add optional row_id
for UI identity while preserving transaction IDs and fees when importing.
Choose a transaction-type field registry over repeated visibility conditions.
One serialized save queue prevents older asynchronous writes replacing newer
ledger edits. Invalid drafts retain the last saved ledger. Import is parsed
without writing, previewed in a modal, and committed only on Replace.
One in-memory undo snapshot covers deletion, clearing and replacement.
A separate full editor model was rejected because it would duplicate the
existing form/request ownership state without changing engine behavior.

### Implementation, verification and subsequent interrogate review

US01: honest empty ledger; local save status and failed-read protection; legacy
restore; parse-only import preview/cancel/explicit replacement; recoverable clear
and import. Injectable storage-driver checks prove preview purity and explicit
write failure. Browser checks prove save/reload and legacy fees survive.
US02: type-field registry, labeled transaction fields with row IDs, in-place
editing, per-row deletion and undo, row-specific validation. Unsupported/invalid
drafts do not overwrite the last valid stored ledger. All five types are
checked. Numeric strings, engine transaction order and weighted-average rules
are preserved. Imported fees are no longer silently replaced with zero.
US03: mobile transaction/holding cards, visible metric labels, suggested
valuation from published coverage with explicit limits, and unavailable-date
errors retain old results. Five viewport widths have no horizontal page overflow.

Checks: 289 Python tests pass, 8 opt-in smoke deselected. Engine selftest 83/83,
ledger editor/store checks, module syntax, static site and diff whitespace pass.
`tests/browser/sprint-13.cjs` passes real IndexedDB restoration, legacy preview/
cancel/replace, S$2.50 fee retention, S$1,027.50 portfolio value with S$27.50
unrealised P/L, export, invalid-draft preservation, all transaction types,
unavailable-date failure, delete/undo and clear/undo. Mobile capture inspected.

Sequential interrogate surfaced duplicate imported row IDs, reproduced by
`ledger-editor-selftest.mjs` as Missing expected exception. Implementation now
rejects duplicates before preview/write, and rerun passes. An early probe
expected a pre-transaction valuation to fail, but the engine legitimately
returns an empty portfolio; this candidate was dropped. The corrected beyond-
coverage probe fails explicitly as intended. No remaining verified finding
against technical exits. This is self-review, not independent review or human
acceptance. User-authorized technical progression permits S14 next.

Sprint PR: https://github.com/ashcx/sg-investing-v1/pull/11.

Sprint 14 integration recheck caught a save-status defect while typing: the
label stayed Saved until blur. `tests/browser/sprint-13.cjs` reproduced
Expected /Unsaved/ but got Saved in this browser. Immediate input events now
mark edits unsaved and invalidate older save-status completions. Persistence
continues on change, retaining the last valid stored ledger. The new browser
assertion verifies this distinction. This small repair is included in the
release-validation PR and tracked here as the owning sprint.
