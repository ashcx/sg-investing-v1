# Sprint 12 — Fair comparisons review

20 October 2026. Sole implementation and separate self-review: main instance.
All stories are technically complete; human product acceptance remains pending.
No production data, financial engine, worker protocol or result-envelope changes.

## Chrome review

Actual Chrome browser, locally served production frontend with fixed synthetic
packs (`node tests/browser/sprint-12-server.mjs`). All synthetic securities are
explicitly labeled as such; values are not claims about market returns.

- Direct visit: two empty slots and shared inputs; duplicates are excluded.
- QQQ/VALL requested 2024-01-01 → 2024-05-01, S$1,000, price only:
  actual starts differ (January 2 / February 1), ending values S$1,920 / S$1,800,
  SGD returns 92% / 80%; native returns 60% / 50%.
- Explicit shared-date action: both start February 1; actual equality confirmed;
  QQQ S$1,600 / 60%, VALL S$1,800 / 80%.
- Six entries: four compute, including the external-origin security. NOFX has
  no CHF/SGD history and BROKEN returns 503. Whole selection is partial, with
  matching dates claimed only among completed rows. See `partial-result.txt`.
- Zero capital is rejected and retains the prior result; removing/re-adding QQQ
  changes selection order; S$2,000 doubles its ending value. An all-failed
  replacement retains those values and their original identity. See
  `changed-states.json` and `all-failed.json`.
- Delayed BROKEN pack exposes calculating/ready rows together; editing capital
  clears progress and its late failure cannot overwrite prior output. See
  `loading.txt` and `cancelled.json`.
- One-time handoff copies dates/capital/custom assumptions; editing Compare
  leaves Simulator unchanged. Regular investing stays in Simulator with an
  explicit initial-lump-only choice. See `handoff.json`.
- Enter expands coverage/warning details, including pack warnings, snapshot,
  methodology and source. All six financial metrics repeat their label, unit
  and actual period at exact 320px and 390px CSS widths; no page overflow.
  See `mobile-labels.json` and mobile captures.

## Visual findings

Inspected desktop unequal/equal/partial/previous states and mobile cards with
expanded notes. The SGD ending value and SGD return are visibly primary;
native return is separated below. Dates and long errors wrap inside cards;
controls and status labels stay visible. No reproduced layout defect remains
in these comparison states. Focus rings were retained in keyboard captures.
The initial browser viewport override was affected by existing zoom; mobile
captures were replaced after measuring exact CSS widths through device metrics.
Temporary viewport/device overrides were cleared after review.

Captures: `desktop-unequal.jpg`, `desktop-equal.jpg`, `desktop-partial.jpg`,
`desktop-previous.jpg`, `mobile-320.jpg`, `mobile-390-notes.jpg`.

## Deterministic verification

- Python normal suite: 281 passed, 8 smoke tests deselected (`python-tests.txt`).
- Independent Python amounts: four hand-calculated fixtures (`numerical-python.txt`).
- Browser engine: 68 selftests, 27/27 golden fixtures, 90 worker checks,
  19 properties / 1,473 cases; initial-lump regressions pass.
- Common-window regressions: 11 named cases (`window-tests.txt`).
- Independent amounts, QQQ/VALL resolved equality, missing/mismatched envelopes,
  partial results and provenance pass (`result-tests.txt`).
- Actual renderer/controller: handoff, six entries, input validation, warning
  escaping, retained prior output, edits/reordering, late responses and adapter
  fallback pass (`ui-contract-tests.txt`).
- Real loader→application→worker→card pipeline: four financial cases and
  external-origin recovery pass (`pipeline-tests.txt`).
- Static asset checks, module syntax, changed-Python Ruff and whitespace pass.

Full generated-production-pack integrations are not claimed: packs are absent.
Synthetic pipeline coverage complements the production parity fixtures. These
agent checks are not human acceptance or unfamiliar-user usability sessions.

## Review and next action

Story evidence is complete. Product Owner reviews this evidence and the PR
before Sprint 13. Merge and deployment are outside this request.

PR: [Sprint 12 #8](https://github.com/ashcx/sg-investing-v1/pull/8).
