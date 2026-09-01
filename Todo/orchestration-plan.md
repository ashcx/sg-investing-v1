# Coordination plan — task-level sequencing across the eight sprints

This plan coordinates the tasks inside `Todo/sprint-0…7`. It complements the
rules in `TODO.md` ("How this Todo system works"). Where this plan and a
sprint file's entry/exit gates appear to conflict, **the sprint file wins**;
update both together if sequencing must change.

Legend: `→` must be sequential · `∥` can run in parallel

## Phase map

```text
Phase 0 — Foundations (Sprint 0)
  S0.1 ∥ S0.2 → S0.3
        │
        ├───────────────────────────────┐
        ▼                               ▼
Phase 1 — Data track               Phase 1 — Engine track
(Sprint 1)                         (Sprint 2 → Sprint 3)
  S1.1 → S1.2 ∥ S1.3 ∥ S1.4 ∥ S1.5   S2.2 → S2.1 (S2.3/S2.4 are
  → S1.6 ; S1.7 ∥ S1.8               checkpoints inside S2.1)
                                     → S3.1 ∥ S3.2 ∥ S3.3
        │                               │
        └───────────────┬───────────────┘
                        ▼
Phase 2 — Feature tracks (Sprint 4 ∥ Sprint 5)
  S4: S4.1 → S4.2 ∥ S4.3 ∥ S4.4 ∥ S4.6 → S4.5
  S5: S5.1 → S5.2–S5.5 ; S5.6 ∥ ; S5.8 any time → S5.7
                        │
                        ▼
Phase 3 — Integration (Sprint 6)
  S6.1 → S6.2 ∥ S6.3 ∥ S6.4 ∥ S6.5
                        │
                        ▼
Phase 4 — Release (Sprint 7)
  S7.1 ∥ S7.5 ∥ S7.8(draft) → S7.2 ∥ S7.4 ∥ S7.6 → S7.3 → S7.7
```

## The sequential backbone (critical path with one agent)

```text
S0.1/S0.2 → S0.3 → S2.2 → S2.1 → S3.1 → S4.1 → S4.2–S4.4 → S4.5
→ S6.1 → S6.2 → S7.2 → S7.3 → S7.7
```

Sprint 1 (S1.1 → S1.6) must also sit on the backbone before S4.1, but it has
slack: it can be interleaved anywhere during Phases 0–1 and only has to be
complete before Phase 2 starts.

## Parallel groups (the direct answer)

| # | Group | Tasks that run together | Precondition |
| --- | --- | --- | --- |
| P1 | Sprint 0 internal | S0.1 ∥ S0.2 | none |
| P2 | Whole sprints | Sprint 1 ∥ Sprint 2 | Sprint 0 complete |
| P3 | Sprint 1 internal | S1.2 ∥ S1.3 ∥ S1.4 ∥ S1.5 | S1.1 schema frozen |
| P4 | Sprint 1 internal | S1.7 ∥ S1.8 (∥ rest of sprint) | S1.8: none; S1.7 budgets need S1.2 output |
| P5 | Sprint 2 internal | domain-module porting (single-security analysis / DCA / portfolio cores) ∥ | arithmetic primitives (S2.2) done |
| P6 | Sprint 3 internal | S3.1 ∥ S3.2 ∥ S3.3 | Sprint 2 exit met |
| P7 | Whole sprints | Sprint 4 ∥ Sprint 5 | Sprints 1–3 exit met |
| P8 | Sprint 4 internal | S4.2 ∥ S4.3 ∥ S4.4 ∥ S4.6 | S4.1 wiring skeleton exists |
| P9 | Sprint 5 internal | S5.6 ∥ S5.1–S5.5 ; S5.8 any time | ledger schema agreed |
| P10 | Sprint 6 internal | S6.2 ∥ S6.3 ∥ S6.4 ∥ S6.5 | S6.1 mode contract frozen |
| P11 | Sprint 7 internal | S7.2 ∥ S7.4 ∥ S7.6 | Sprints 4–6 complete |
| P12 | Early lane (any time) | S1.8, S7.1, S7.5, S7.8 draft, Python-side golden fixture authoring (feeds S3.1), pack-loader prototype (feeds S1.7) | prep only — never tick the owning sprint's exit criteria early |

## Phase details

### Phase 0 — Sprint 0

| Task | Depends on | Parallel with | Solo order |
| --- | --- | --- | --- |
| S0.1 confirm static/no-API target | — | S0.2 | 1st |
| S0.2 record calculation architecture | — | S0.1 | 1st |
| S0.3 update spec + README | S0.1 + S0.2 | — | 2nd |

### Phase 1 — Sprint 1 (data track)

| Task | Depends on | Parallel with | Solo order |
| --- | --- | --- | --- |
| S1.1 pack schemas | Sprint 0 exit | — (first) | 1st |
| S1.2 generate all-security packs | S1.1 | S1.3–S1.5 | 2nd |
| S1.3 security/year partitions | S1.1 | S1.2, S1.4, S1.5 | 2nd |
| S1.4 manifest metadata/provenance | S1.1 | S1.2, S1.3, S1.5 | 2nd |
| S1.5 support-status manifest | S1.1 | S1.2–S1.4 | 2nd |
| S1.6 refresh-workflow publishing | S1.2 works locally | — | 3rd |
| S1.7 budgets + caching | S1.2 output to measure (budgets draftable earlier) | S1.8, whole sprint | 4th |
| S1.8 self-host fonts decision | none | everything, any time | anytime |

Solo order: S1.1 → S1.2 → S1.3 → S1.4 → S1.5 → S1.6 → S1.7 (S1.8 anywhere).

### Phase 1 — Sprint 2 → 3 (engine track)

| Task | Depends on | Parallel with | Solo order |
| --- | --- | --- | --- |
| S2.2 decimal-safe arithmetic layer | S0.2 decision | — (first slice of the port) | 1st |
| S2.1 port domain calculations | S2.2 primitives | domain modules after primitives | 2nd |
| S2.3 methodology rules preserved | inside S2.1 | — | checkpoint |
| S2.4 Python-shaped envelopes | inside S2.1, verified vs `src/sg_investing/models.py` | — | checkpoint |
| S3.1 golden parity tests | Sprint 2 exit | S3.2, S3.3 | 1st |
| S3.2 property tests | Sprint 2 exit | S3.1, S3.3 | 1st |
| S3.3 Web Worker execution | Sprint 2 exit (module exists) | S3.1, S3.2 | 1st |

Note: S2.2–S2.4 are properties of S2.1's code, not separate later stages —
treat them as verification checkpoints of the port. Python-side golden
fixtures for S3.1 can be authored as prep work earlier (group P12).

### Phase 2 — Sprint 4 ∥ Sprint 5

Sprint 4 (DCA):

| Task | Depends on | Parallel with | Solo order |
| --- | --- | --- | --- |
| S4.1 wire local engine + packs (replace `/api/dca`) | Sprint 1–3 exits | — (first) | 1st |
| S4.2 monthly/quarterly/yearly schedules | S4.1 | S4.3, S4.4, S4.6 | 2nd |
| S4.3 dividends/tax/reinvestment outputs | S4.1 | S4.2, S4.4, S4.6 | 2nd |
| S4.4 warnings preserved | S4.1 | S4.2, S4.3, S4.6 | 2nd |
| S4.6 loading states + request isolation | S4.1 skeleton; uses S1.5 manifest + S3.3 workers | S4.2–S4.4 | 2nd |
| S4.5 DCA parity fixtures | S4.1–S4.4 | — | last |

Solo order: S4.1 → S4.2 → S4.3 → S4.4 → S4.6 → S4.5.

Sprint 5 (portfolio):

| Task | Depends on | Parallel with | Solo order |
| --- | --- | --- | --- |
| S5.1 move ledger reconstruction into local engine | Sprint 1–3 exits | — (first) | 1st |
| S5.2 transaction types + validation | S5.1 | S5.3–S5.5 | 2nd |
| S5.3 selective pack loading | S5.1 (+ S1.5) | S5.2, S5.4, S5.5 | 2nd |
| S5.4 output parity (WAC, P/L, cash) | S5.1, S5.2 | S5.3, S5.5 | 2nd |
| S5.5 as-of/missing-price rules + warnings | S5.1 | S5.2–S5.4 | 2nd |
| S5.6 IndexedDB persistence + clear/export/import | ledger schema only — independent of engine port | ∥ S5.1–S5.5 | 2nd |
| S5.8 exclude unsupported claims | — | any time | anytime |
| S5.7 portfolio parity fixtures | S5.2–S5.5 | — | last |

Solo order: S5.1 → S5.2 → S5.3 → S5.4 → S5.5 → S5.6 → S5.7 (S5.8 anywhere).

### Phase 3 — Sprint 6

| Task | Depends on | Parallel with | Solo order |
| --- | --- | --- | --- |
| S6.1 explicit local-compute mode in UI | Sprint 4 + 5 exits | — (first, freezes the mode contract) | 1st |
| S6.2 replace runtime `/api` calls | S6.1 | S6.3–S6.5 | 2nd |
| S6.3 comparison fallback fix | S6.1 | S6.2, S6.4, S6.5 | 2nd |
| S6.4 missing/stale pack unavailable states | S6.1 (uses S1.5) | S6.2, S6.3, S6.5 | 2nd |
| S6.5 currency-switching contract in both modes | S6.1 | S6.2–S6.4 | 2nd |

### Phase 4 — Sprint 7

| Task | Depends on | Parallel with | Solo order |
| --- | --- | --- | --- |
| S7.1 verify workflow/default branch | none — safe any time | early lane (P12) | anytime |
| S7.5 pin action/library versions | none | early lane (P12) | anytime |
| S7.8 repo/Pages docs | draft any time; finalize at release | early lane (P12) | draft early |
| S7.2 CI static-path/pack/JSON checks | S1.6 packs published; Sprint 6 done | S7.4, S7.6 | 1st |
| S7.4 build identifier + snapshot date | S1.6 artifacts | S7.2, S7.6 | 1st |
| S7.6 CSP + request/storage review | S6.2 (final external-request inventory) | S7.2, S7.4 | 1st |
| S7.3 full suites before publish | S7.2, S7.4 in place | — | 2nd |
| S7.7 Chrome QA desktop + mobile | everything above | — | 3rd (strictly last) |

## Never parallelize

- **S6.2** with anything in Phase 2 — it rewrites every `/api` call site and
  will conflict with S4.1/S5.1 wiring.
- **S7.3 and S7.7** — the release gate; strictly last and sequential.
- **Two workers editing `frontend/app.js` at once.** Sprints 4, 5 and 6 all
  touch this single monolithic file: keep one owner per time window, or split
  it into modules first as part of S4.1/S5.1 scaffolding.
- **S1.7 and S5.6** share IndexedDB — fix database naming/versioning in S1.7
  before S5.6 starts.

## Freeze points (interfaces that unlock parallel work)

1. **Pack schema + support manifest** (S1.1, S1.5) — freeze before S1.2+ and
   before any engine/loader consumer builds against it.
2. **Result envelopes** (S2.4, mirroring `src/sg_investing/models.py`) —
   freeze before Sprint 3 fixtures are authored.
3. **Worker request/response protocol + deterministic request keys**
   (S3.2, S3.3, S4.6) — freeze before Phase 2 wiring.
4. **Mode flag / API-base contract** (S6.1) — freeze before the
   S6.2–S6.5 parallel batch.

## Staffing patterns

- **One agent (solo):** collapse every ∥ group into the "Solo order" column
  of each table. Run Sprint 1 before Sprint 2 if in doubt — it is shorter and
  unblocks Phase 2 earlier; Sprint 2's port can proceed against fixtures in
  the meantime.
- **Two or three agents:** assign whole tracks to one owner each to minimize
  conflicts: Data track (Sprint 1: scripts/workflows/packs), Engine track
  (Sprints 2–3: engine + fixtures), UI track (Sprints 4–6: `frontend/`).
  Re-sync at every freeze point listed above.

## Phase 4.5 — Sprint 7.5 (added 2026-09-01)

Sprint 7.5 (`Todo/sprint-7.5-fx-incremental-reactive.md`) closes three
usability gaps after the launch: FX history back to 2000 from a reputable
source (plan requires user sign-off at task A0 before implementation),
incremental date-range updates without full rebuilds, and staged auto-loading
(series → analysis → DCA/portfolio) in the UI. Independent of Sprint 8; only
minor CI-workflow coordination if run in parallel. Track A gates on the A0
decision; Tracks B and C are parallelizable with each other (Python backend
vs frontend UI — disjoint areas).

## Phase 5 — Sprint 8 (added 2026-08-31)

Sprint 8 (`Todo/sprint-8-pack-origin.md`) trails Sprint 7 and decides the
Tier-2 pack origin (hosted object storage vs self-hosted WSL behind a
tunnel) for the full 3,188-security set. Research may run in the early lane
at any time; decision and implementation gate on Sprint 7's exit criteria.
The frozen `pack-loader.js` baseUrl makes Tier 2 a configuration switch.
