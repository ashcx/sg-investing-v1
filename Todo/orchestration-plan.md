# Coordination plan — sequential execution in the main instance

User decision, 15 October 2026: all implementation, verification, review, and
documentation runs sequentially in the main instance. Do not spawn child agents
or delegate work. This replaces all prior dispatch, staffing, and concurrent
execution instructions. Sprint files remain authoritative for entry/exit gates.

## Sprint order

```text
0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 7.5 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15
```

Select the lowest-numbered incomplete sprint. Verify its depended-on exits,
then tick its entry checklist before starting tasks. Finish and record one task
before starting the next. Completed historical evidence remains intact.

## Task sequence through Sprint 7

The task IDs below retain the earlier coordination references; the sprint
files hold the actual checkboxes. Follow this row order within each sprint.
S2.3/S2.4 are verification checkpoints within S2.1, not later implementation.

| Task | Prerequisite or checkpoint |
| --- | --- |
| S0.1 confirm static/no-API target | — |
| S0.2 record calculation architecture | — |
| S0.3 update spec + README | S0.1 + S0.2 |
| S1.1 pack schemas | Sprint 0 exit |
| S1.2 generate all-security packs | S1.1 |
| S1.3 security/year partitions | S1.1 |
| S1.4 manifest metadata/provenance | S1.1 |
| S1.5 support-status manifest | S1.1 |
| S1.6 refresh-workflow publishing | S1.2 works locally |
| S1.7 budgets + caching | S1.2 output to measure (budgets draftable earlier) |
| S1.8 self-host fonts decision | Owning sprint entry gate |
| S2.2 decimal-safe arithmetic layer | S0.2 decision |
| S2.1 port domain calculations | S2.2 primitives |
| S2.3 methodology rules preserved | inside S2.1 |
| S2.4 Python-shaped envelopes | inside S2.1, verified vs `src/sg_investing/models.py` |
| S3.1 golden parity tests | Sprint 2 exit |
| S3.2 property tests | Sprint 2 exit |
| S3.3 Web Worker execution | Sprint 2 exit (module exists) |
| S4.1 wire local engine + packs (replace `/api/dca`) | Sprint 1–3 exits |
| S4.2 monthly/quarterly/yearly schedules | S4.1 |
| S4.3 dividends/tax/reinvestment outputs | S4.1 |
| S4.4 warnings preserved | S4.1 |
| S4.6 loading states + request isolation | S4.1 skeleton; uses S1.5 manifest + S3.3 workers |
| S4.5 DCA parity fixtures | S4.1–S4.4 |
| S5.1 move ledger reconstruction into local engine | Sprint 1–3 exits |
| S5.2 transaction types + validation | S5.1 |
| S5.3 selective pack loading | S5.1 (+ S1.5) |
| S5.4 output parity (WAC, P/L, cash) | S5.1, S5.2 |
| S5.5 as-of/missing-price rules + warnings | S5.1 |
| S5.6 IndexedDB persistence + clear/export/import | ledger schema only — independent of engine port |
| S5.7 portfolio parity fixtures | S5.2–S5.5 |
| S5.8 exclude unsupported claims | — |
| S6.1 explicit local-compute mode in UI | Sprint 4 + 5 exits |
| S6.2 replace runtime `/api` calls | S6.1 |
| S6.3 comparison fallback fix | S6.1 |
| S6.4 missing/stale pack unavailable states | S6.1 (uses S1.5) |
| S6.5 currency-switching contract in both modes | S6.1 |
| S7.1 verify workflow/default branch | Sprint 6 exit |
| S7.5 pin action/library versions | Owning sprint entry gate |
| S7.8 repo/Pages docs | Finalize before S7.3 |
| S7.2 CI static-path/pack/JSON checks | S1.6 packs published; Sprint 6 done |
| S7.4 build identifier + snapshot date | S1.6 artifacts |
| S7.6 CSP + request/storage review | S6.2 (final external-request inventory) |
| S7.3 full suites before publish | S7.2, S7.4 in place |
| S7.7 Chrome QA desktop + mobile | everything above |

S1.8 is performed after S1.7. S5.8 follows S5.7. Sprint 7 completes S7.1,
S7.5, S7.8, S7.2, S7.4, S7.6, S7.3, then S7.7; finalize release documentation
before the final suite and browser checks.

## Contract gates

- Record pack schema and support-manifest contracts before downstream consumers
  use them; agree the schema before generating packs.
- Freeze Python-shaped result envelopes before Sprint 3 fixtures.
- Freeze worker request/response protocol and deterministic request keys before
  dependent UI wiring. Keep IndexedDB naming/versioning consistent between
  caching and portfolio persistence.
- Freeze the mode/API-base contract at S6.1 before S6.2–S6.5.
- Sprint 7.5 follows its task list A → B → C, preserving the recorded A0 FX
  decision and evidence. Sprint 8 follows after Sprint 7.5 is complete.
- **Sprint 9 hard gate:** complete and evidence the S9-US01 request-identity
  contract freeze and per-view state isolation before any other S9 story or
  dependent fixture/test work. Then finish S9-US01 regressions, S9-US02, and
  S9-US03 in order. A failed gate blocks downstream work.

## Redesign sequence, Sprints 9–15

The [Scrum plan](redesign-scrum-plan.md) defines events, capacity, and acceptance.
Within each sprint, finish US01 → US02 → US03 in order, including verification
and self-review. US01 + US02 are the 6-SP timebox commitment; US03 is 3-SP
stretch. Reserve 20–30% for review/rework. All stories remain required for exit;
uncompleted stretch requires a recovery timebox, never a waived exit gate.
Do not start a later sprint while an earlier exit remains open.

Preserve financial engines, result envelopes, worker protocol, warnings,
provenance, and existing ledgers. Sprint 11's user-authorized optional initial
lump sum plus recurring DCA is the narrow compatible engine extension; re-estimate
its story before starting and adjust the commitment to remain at or below 7 SP.
Product Owner decision, 15 October 2026: S9-US02 adopts explicit Calculate/Update
and labels edited outputs previous until recalculated, superseding Sprint 7.5's
automatic financial recalculation. Series/data loading may remain automatic.

Sprint 14 uses the frontend-design skill for an interface audit, concrete visual
direction proposals, and a separately reviewed implementation. Preserve the four
workspaces and existing behavior. Record the Product Owner’s selected direction
before visual implementation; do not invent acceptance. Sprint 15 retains the
former Sprint 14 validation backlog, with its five-person gate replaced by
technical/design verification under the explicit 18 October user decision.
This 18 October planning amendment does not start either sprint.

## Recording and review

After each task, update its checkbox only when supported by evidence. Record in
the owning sprint file: task ID, status, changed files, checks and exact results,
evidence paths, self-review findings, blockers, and next action. Supporting
redesign artifacts belong under `docs/ux-redesign-evidence/sprint-N/`.
The main instance reviews its own work in a separate step and identifies it as
self-review. Human product/release acceptance remains required where specified; Sprint 15
uses technical/design task evidence under the 18 October amendment. Update `TODO.md` only when sprint status changes.
Planning amendments do not mark implementation tasks complete or start S9.
