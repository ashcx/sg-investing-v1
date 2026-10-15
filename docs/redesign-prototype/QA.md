# Planning and wireframe verification — 13 October 2026

This is evidence for the planning artifacts and standalone wireframe only. It
does not complete a production sprint or establish human usability acceptance.

## Coordination review

- Three child agents were dispatched with `model: gpt-6-luna`,
  `reasoning_effort: max`, and `fork_turns: none`: Scrum plan author, prototype
  author, and independent read-only reviewer. Root coordinated integration and
  browser verification.
- Plan and prototype authors had separate write ownership. The reviewer made
  no file changes. Root took over edits after author handoff.
- The independent review checked dependency gates, financial scope, migration,
  prototype limitations, latest-data versus exported-snapshot semantics, model
  dispatch, and candidate versus deployed-baseline evidence.
- Root reconciled the old single Sprint 9 proposal into Sprints 9–14, updated
  the roadmap, sequencing instructions, and final acceptance, and verified
  documentation links and sprint structure.
- All six implementation sprints remain **Not started**. Only Sprint 9's
  historically verified dependency checks are ticked; no production tasks or
  exits were ticked by this planning work.

## Browser checks

Chrome was used to interact with the locally served standalone wireframe.
Widths below are desktop browser viewport overrides, not physical devices.

| Check | Observed outcome |
| --- | --- |
| All four views at 320, 390, 768, and 1280px | 16 combinations inspected; page width matched viewport width, with exactly one active view each time |
| One-time request preview | QQQ, SGD 10,000, and requested dates 2024-01-02–2025-01-02 appear in the completed preview; financial values explicitly remain uncalculated |
| Amount-only edit | Earlier request preview becomes visibly previous/pending, preserving its original amount |
| Regular contribution mode | Security/dates retained; initial-capital field hides and contribution/frequency fields appear |
| Regular-to-comparison attempt | User stays in Simulate and sees a one-time-only explanation; contribution is not reinterpreted as capital |
| One-time comparison handoff | Selected security, initial amount, dates, and assumptions copied; second security remains empty |
| Direct comparison entry after reload | Two empty security slots |
| Comparison security edit | Completed preview becomes previous/pending; selected listing metadata updates |
| Duplicate comparison selection | Explicit validation error |
| Coverage disclosure | Actual periods/common window explicitly unresolved; no claim of equal history or calculated returns |
| Invalid simulator amount/date order | Explicit error; previous request remains identified as previous |
| Cash-deposit entry | Security and quantity fields hidden; deposit amount labeled |
| Transaction add/edit/delete/undo | In-memory SGD 1,000 cash entry edited to 1,500, deleted, then restored |
| New transaction security | No automatic security selected; choosing QQQ updates the currency to USD |
| Back/Forward | Portfolio and Data & methods destinations restored |
| Keyboard skip link | Focus moved to `main` while comparison route was preserved |
| Help dialog Escape | Dialog closed |
| Console inspection | No captured error/warning messages during inspected flows |

During review, fixes were made for hidden fields leaking into the one-time
view, incorrect sample VALL identity, redundant initial empty states, unsupported
regular comparison, arbitrary second-security selection, stale comparison
previews, skip-link routing, and a stale regular-mode handoff explanation.

## Static checks and captures

- JavaScript syntax checked with Node.
- Duplicate HTML IDs and literal script element references checked.
- Roadmap/sprint/prototype documentation links checked: no missing targets.
- Fixed sprint section order, Given/When/Then story conditions, unchecked
  future gates/tasks, and Not started status checked for Sprints 9–14.
- Whitespace diff check passed; no production frontend or engine files changed.
- [Desktop capture](preview-desktop.jpg)
- [Mobile capture](preview-mobile.jpg)

## Limits

### Initial lump sum amendment

The subsequent user-requested regular-investing change was browser-checked:
S$10,000 initial lump sum and S$500 monthly contributions appear separately in
the request preview, zero lump sum is accepted, and negative lump sum is
rejected. JavaScript syntax and whitespace checks passed. This validates input
flow only; Sprint 11 still owns real engine support and Python/browser parity.
[Updated regular-investing capture](preview-dca-initial-lump.jpg).

Search by ticker/name/ISIN is represented by a short sample dropdown, not a
tested search implementation. No real coverage resolution, engine calculation,
ledger persistence/import/export, deployment, physical-device, screen-reader,
cross-browser, or human participant test was performed for this prototype.
Those remain in the relevant production sprint acceptance criteria.
