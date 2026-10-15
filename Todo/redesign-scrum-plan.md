# Scrum plan — SG / Invest redesign

User authorization, 15 October 2026: begin the redesign in the main instance,
following the detailed sprint gates. Check in with the Product Owner when a
material product, scope, or design decision is unclear. Sprint 9 is In progress;
later sprints remain Not started until their dependency and acceptance gates pass.
Production deployment is outside this authorization.

At the end of every sprint, inspect the actual locally served webpage at desktop
and mobile sizes, including changed states, keyboard behavior, labels, and
layout. Retain captures and findings before claiming completion. Open a pull
request to `ashcx/sg-investing-v1` for each sprint containing its plan, changes,
checks, results, and unresolved gaps; link it in the sprint execution log.
Do not merge or publish from this instruction alone.

## Product Goal

Help Singapore investors understand what a historical investment or recorded
portfolio means in SGD. Each screen should make the user's task clear and each
financial result should state what it represents, which request produced it,
what dates and coverage it used, and where uncertainty remains. Preserve the
existing Python and browser engines, decimal behavior, worker protocol,
result-envelope contracts, provenance, and warnings.

User amendment, 13 October 2026: regular investing supports **optional initial
lump sum (default S$0) + recurring DCA**. Sprint 11 owns the narrowly scoped,
backward-compatible Python/browser DCA extension and parity tests needed for
this feature; existing DCA currently accepts recurring contributions only.
All other engine-freeze constraints remain. Do not implement combined returns
or XIRR in presentation code. Re-estimate the affected story at planning.

The low-fidelity review artifact is
[the redesign prototype](../docs/redesign-prototype/index.html). It can help
review layout and flow; it is not production code, implementation evidence, or
proof that users can complete tasks. The main instance owns prototype authoring,
integration, and self-review sequentially. Prototype code is not promoted into
production until the owning implementation sprint starts under its gates.

### Scope boundary

Compare remains a **one-time investment comparison** in this program.
Multi-security DCA/regular-contribution comparison is not included. A regular
contribution request must never be silently reinterpreted as initial capital.
Also out of scope: forecasts, live trading, new portfolio return/risk/allocation
metrics, invented wealth/total-return curves, accounts/cloud ledger sync, and a
new framework or build pipeline solely for this redesign. Any scope change is
recorded in its sprint file before implementation.

## Product and sprint backlog

Work is split into six sequential sprint candidates. All tasks run one at a
time in the main instance. Each fixed one-week timebox commits US01 + US02
(6 SP); US03 (3 SP) is stretch. The 9-SP backlog ceiling is not a commitment.
Reserve 20–30% of actual capacity for review and rework. Re-estimate at planning;
reduce or split the commitment through the sprint file if it would exceed 7 SP.
Points describe relative effort and risk, not hours. All three stories remain
required for exit. Unfinished work requires a recovery timebox in the same
sprint before the next sprint starts. Six initial timeboxes are a minimum
forecast, not a six-week completion promise; required stretch work and participant
scheduling may need additional timeboxes.

| Sprint | Sprint backlog | Main outcome | Audit findings | Depends on | Status |
| --- | --- | --- | --- | --- | --- |
| 9 | [Result trust and shared result contracts](sprint-9-user-experience-redesign.md): S9-US01–03, 6 SP committed + 3 SP stretch | Results, charts, warnings, and exports stay with the request that produced them; current, pending, previous, coverage, and currency states are clear. | F01–F03, F07–F09, F15 | 7, 7.5, 8 | Complete |
| 10 | [Workspace and security discovery](sprint-10-workspace-and-discovery.md): S10-US01–03, 6 SP committed + 3 SP stretch | Task navigation, reusable security search, coherent visual language, and security-specific Data & methods. | F05, F12, F14, F16–F19 | 9 | In progress |
| 11 | [Unified investment simulator](sprint-11-investment-simulator.md): S11-US01–03, 6 SP committed + 3 SP stretch | One-time and regular investing share one setup, show an honest answer/chart, and explicitly hand off to comparison. | F03, F10, F12, F13, F16 | 10 | Not started |
| 12 | [Fair investment comparisons](sprint-12-fair-comparisons.md): S12-US01–03, 6 SP committed + 3 SP stretch | Common windows are checked against actual resolved dates; partial results and mobile values remain honest. | F04, F06, F15 | 11 | Not started |
| 13 | [Guided portfolio workflow](sprint-13-portfolio-workflow.md): S13-US01–03, 6 SP committed + 3 SP stretch | Users can add, edit, undo, import, and read a local ledger without losing existing data or seeing unsupported claims. | F11, F16 | 12 | Not started |
| 14 | [Release validation and usability](sprint-14-release-and-usability.md): S14-US01–03, 6 SP committed + 3 SP stretch | Full calculation, responsive/accessibility, pack smoke, audit, and real-human usability evidence is recorded. | F01–F19 | 13 | Not started |

Every sprint file owns its full task and exit checklist. The sprint-file gate
wins over this summary or a Scrum event: a dependent sprint cannot start until
every exit criterion of its dependency is checked. The Sprint 9 historical
entry checks are checked only because the referenced Sprint 7, 7.5, and 8 exit
files were inspected and all their listed exit items were checked.

## Migration map from the monolithic Sprint 9 draft

The original Sprint 9 task sections are superseded as one large batch and split
as follows. The new sprint files are the authoritative checklists; this map
keeps old references traceable and prevents undocumented scope loss.

| Old Sprint 9 section | New backlog destination |
| --- | --- |
| A1 request/result ownership | S9-US01 |
| A2 cross-panel chart regression | S9-US01 |
| A3 initial/example/pending/error states | S9-US02 |
| A4 equal-period checks and date disclosure | S12-US01 |
| A5 FX direction and native currency | S9-US03 |
| A6 contrast, mobile comparison labels, and chart meaning | S10-US03, S12-US02, S11-US02 respectively |
| A7 deterministic browser regressions | Focused fixtures in S9–S13; complete journey matrix in S14-US01 |
| B1 wireframes and task flows | S10-US01 plus flow acceptance in S11–S13 |
| B2 shared picker, coverage, assumptions, result, warning, and state components | S9-US03, S10-US02/03, S11-US01/02 |
| B3 explicit Calculate/Update behavior | S9-US02 and S11-US01 |
| B4 result states, focus, and announcements | S9-US02 and S11-US02 |
| B5 visual tokens, responsive behavior, labels, chart units, and copy | S10-US03; chart specifics in S11-US02; checked in S14-US02 |
| B6 URLs, legacy links, and snapshot semantics | S10-US01 and S14-US01 |
| C1–C2 workspace destinations, navigation, and landing view | S10-US01 |
| C3–C5 reusable search, progressive filters, recovery, identity, and pagination | S10-US02 |
| C6 security-specific Data & methods | S10-US03 |
| D1–D4 combined simulator, coverage defaults, assumptions, and calculation states | S11-US01, using S9-US02 states |
| D5–D7 result hierarchy, price chart, coverage/warnings, and details | S11-US02 |
| D8 explicit comparison handoff | S11-US03 |
| E1–E2 copied setup, history preview, common dates, actual periods | S12-US01 |
| E3–E4 labeled comparison values, warnings, and partial failures | S12-US02/03 |
| E5 security count, identity, removal, edits, and stale outputs | S12-US03 |
| F1 saved-ledger restore and honest empty state | S13-US01 |
| F2–F4 transaction form, labels, IDs, edit/delete/undo, import recovery | S13-US01/02 |
| F5–F6 save/export, mobile ledger, valuation date, and errors | S13-US01/03 |
| F7 portfolio transaction and persistence verification | S13-US01/02/03; end-to-end check in S14-US01 |
| G1 deterministic browser journeys | S14-US01 |
| G2 viewports, keyboard, zoom, contrast, labels, and motion | S14-US02 |
| G3 unchanged suites and pack integrations | S14-US01 |
| G4 read-only Tier-1/Tier-2 and failure checks | S14-US01 |
| G5 exports, shares, request identity, and snapshot behavior | S14-US01 |
| G6 unfamiliar-user sessions and measured targets | S14-US03 |
| G7 evidence, docs, audit reconciliation, and exit gates | S14-US01/02/03 and sprint exit criteria |

Audit-finding ownership is also explicit: F01/F02/F03/F07/F08/F09/F15 → Sprint
9; F04/F06 → Sprint 12; F05/F12/F14/F16/F17/F18/F19 → Sprint 10 (contextual
terminology is completed in Sprints 11 and 13); F10/F13 → Sprint 11; F11 →
Sprint 13. Sprint 14 verifies every F01–F19 finding against evidence. A finding
can be referenced by multiple tests, but its implementation home is the one
listed here.

## Roles and sequential ownership

User decision, 15 October 2026: perform every task in the main instance.
No child-agent dispatch, model requirement, delegation, or overlapping tasks
remain authorized by this plan.

- **Human user — Product Owner:** owns priorities, scope decisions, product
  acceptance, and final release acceptance. Routine edits do not need approval.
  The main instance cannot claim human acceptance on the user's behalf.
- **Main instance — sole implementation and verification owner:** checks gates,
  edits all files, runs checks, performs a separate self-review, records evidence,
  maintains the sprint files and roadmap, and facilitates planning/review.
  Self-review must not be presented as independent review.
- **Execution rule:** one sprint, one story, one task at a time. Complete and
  record implementation, verification, and self-review before moving on.
- **S9 prerequisite:** freeze the request-identity contract and implement per-view
  state isolation at the start of S9-US01. Record evidence before proceeding to
  dependent tests or any other story. No downstream work bypasses this gate.
- **No contract drift:** if implementation appears to require a calculation,
  tax, decimal, engine, worker-protocol, or result-envelope change, stop that
  work, record the issue in the owning sprint file, and let the Product Owner
  decide whether to revise scope through the sprint file and roadmap.
  Sprint 11's documented optional-initial-lump-sum DCA amendment is already
  within planned scope; design and verify it compatibly instead of blocking
  it as an unapproved exception. Other changes still follow this rule.

Product Owner decision, 15 October 2026: adopt explicit Calculate/Update in
S9-US02. Financial edits mark retained results previous until recalculated.
This supersedes Sprint 7.5 automatic financial recalculation; the exact scope
and preserved request-safety invariant are recorded in Sprint 9.

## Definition of Ready

A story is ready to enter a sprint only when all of the following hold:

- The sprint's depended-on exit files have every exit criterion checked, and
  its entry checklist is complete.
- The story has an ID, priority, relative point estimate, the main instance as
  implementation owner, concrete Given/When/Then acceptance, and named evidence.
- Required fixtures, route/result contracts, and visual references are available.
  Freeze each contract before dependent implementation or fixture work.
- The task has a recorded sequential position and verification plan; the main
  instance completes and logs its predecessor before starting it.
- The work stays within the existing engine/result contracts and the stated
  scope. Any change to the sprint backlog is written into the sprint file and
  coordinated with the roadmap before work starts.

## Definition of Done

A story is done when its Given/When/Then behavior is demonstrated, its checklist
is complete, and its stated evidence is recorded. A sprint is done only when
all tasks and every exit criterion in its sprint file are checked, the human
Product Owner has reviewed product evidence, and the coordinator has updated
the roadmap status. Green tests alone do not establish accessibility,
understandability, ledger safety, pack behavior, or human usability.

For Sprint 14, usability evidence must come from five actual people unfamiliar
with the product. Record observed completion, coaching, mistakes, comprehension,
and time; preserve participant privacy. Do not invent participants, timings,
quotes, or successful outcomes. If participants cannot be recruited, sessions
cannot be run, or the audit's proposed targets are missed, keep Sprint 14 in
progress and record a recovery/retest plan. The root agent cannot accept the
product on behalf of the human Product Owner.

## Sprint events and timeboxes

The planned sprint is one fixed week. Use these event limits as maximums and
keep the events within that week; no event extends the sprint.

| Event | Timebox | Expected outcome |
| --- | --- | --- |
| Sprint Planning | 60 minutes | Recheck the entry gate, commit at most 7 SP (initially US01 + US02 = 6 SP), mark US03 stretch, freeze task interfaces/fixtures, and publish the sprint goal. |
| Daily sync | 15 minutes each working day | The main instance records completed work, exact check results, next work, and blockers in the sprint file. This may be an asynchronous written sync. |
| Sprint Review | 45 minutes | Demonstrate the integrated increment and evidence to the Product Owner; record accepted behavior, gaps, and product backlog changes. |
| Retrospective | 45 minutes | Inspect sequential execution, accuracy, and evidence; record one or two practical changes for the next sprint. |

If the timebox expires with unfinished stories, do not extend it or check the
exit gates. Record what shipped and what did not, leave the roadmap **In
progress**, return incomplete work to the same sprint backlog, and plan a
recovery timebox for that sprint before starting its dependent sprint. Update
the sprint file and roadmap together. Scope or sequencing changes are never
left as undocumented chat notes.

## Task execution record

Keep the checklist authoritative. Add one dated entry to the owning sprint's
execution log after each task, including failures; supporting reports live in
that sprint's evidence folder. Do not create a competing task list.

```text
Date and sprint/story/task ID:
Status: in progress / complete / blocked
Main-instance changes and file paths:
Acceptance conditions demonstrated:
Checks run, exact results, and evidence paths:
Separate self-review findings and resolution:
Remaining gaps or blocker and its source:
Next sequential action:
Contract/scope change, if any, and recorded decision:
```

## Stop conditions

- A dependency gate is unchecked or its referenced exit evidence is missing.
- Work would be delegated outside the main instance or a second task would
  start before the current task is verified and recorded.
- Dependent work would start before its contract/fixture gate, including S9
  request identity and per-view isolation, is complete and evidenced.
- Results cannot be tied to their request, user data could be lost, or a test
  would depend on live network data in the normal deterministic suite.
- Work requires a change to engine calculations, decimal behavior, methodology,
  result envelopes, or worker protocol outside this redesign scope.
- Sprint 14 has no actual participant evidence or has unmet usability targets.
- A timebox expires with any required task or exit criterion open.

When a stop condition occurs, record the specific blocker in the active sprint
file, leave it **In progress**, and do not start its dependent sprint. Continue
only independent work that does not depend on the blocker.

## References

- [Official Scrum Guide](https://scrumguides.org/scrum-guide.html)
- [Roadmap and sprint gates](../TODO.md)
- [Coordination plan](orchestration-plan.md)
- [Project overview](../README.md)
- [Product design document](../product_design_document.md)
- [13 October UX audit](../docs/ux-audit-2026-10-13/README.md)
- [Low-fidelity redesign prototype](../docs/redesign-prototype/index.html)

## Execution authorization — Sprints 10 and 11, 15 October 2026

The user explicitly authorized building both described increments sequentially.
Sprint 9 is accepted for progression. Complete Sprint 10 implementation, tests,
actual desktop/mobile design inspection and PR before Sprint 11 starts. For this
authorized pair, final human product review may occur after both increments;
record it as pending, never infer acceptance of unseen work. Sprint 11's entry
therefore requires every Sprint 10 technical/design/PR exit, with human review
tracked separately. No later sprint, merge, or deployment is authorized here.
