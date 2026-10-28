# Sprint 4 — DCA, full static-site support

## Goal

Arbitrary DCA requests run entirely in the browser using the local engine and
lazily loaded data packs — no `/api/dca` dependency.

## Entry criteria

- [x] Sprint 1 exit criteria are all met: packs exist for every supported
      security with support manifests.
- [x] Sprint 2 exit criteria are all met: browser engine returns Python-shaped
      envelopes.
- [x] Sprint 3 exit criteria are all met: parity and property suites are green;
      workers are cancellable and non-blocking.

## Depends on

Sprints 1, 2, 3.

## Tasks

- [x] Replace the static-mode `/api/dca` dependency with the local calculation
      engine and lazily loaded security data packs.
- [x] Support monthly, quarterly and yearly contribution schedules using the
      backend's first-available-trading-day rule.
- [x] Support dividends, withholding tax, reinvestment, fractional shares,
      native-currency output, SGD output and both XIRR fields.
- [x] Preserve explicit warnings for estimated/missing pay dates, missing FX,
      incomplete price history and unverified dividend coverage.
- [x] Add parity fixtures for USD ETFs, SGX/SGD securities, accumulating funds,
      zero-dividend cases and invalid date/amount inputs.
- [x] Show a clear loading/progress state while a data pack or worker result is
      being resolved; never show a result from a different request.

## Exit criteria

- [x] A fresh static deployment can calculate a new supported DCA request for
      any covered security without a network call to `/api`.
- [x] All warning and provenance behavior matches the Python engine.
- [x] DCA parity fixtures pass for the listed cases.


## DCA correctness repair, 28 October 2026

User-authorized repair of the two defects reproduced by the interrogate review.
This repairs existing Sprint 4 behavior without advancing the roadmap or
changing the open Sprint 7.5 operational gate. Sprint 1, 2 and 3 historical
exit checklists and the Sprint 4 entry checklist were inspected.

- [x] Reproduce it yourself on the matching surface via the driver skill.
- [x] Binary-search the cause.
- [x] Plan the fix.
- [x] Verify on the same surface.
- [x] Stage the commits so the failing repro lands before the fix in git history.
- [x] Run Opening a PR.

Delegation is skipped under the project's explicit sequential-ownership rule.
Architecture exploration is a sequential pass. Cash flows remain date/Decimal
pairs with an optional XIRR result. FX lookups retain rate and age, with a
request-local currency/date cache preventing duplicate warnings. Reusing the
existing stale-FX helpers preserves the seven-day threshold and warning text.
A separate global warning pass was rejected because it could warn about FX
that the calculation never uses.

Before repair, `python -m pytest tests/test_dca_regressions.py` reports
7 failed, 1 passed. Same-day XIRR is 4.50005; stale FX warnings are empty
for purchase, valuation and dividend conversion. Throughput checkpoint is
one defect at a time, followed by focused regressions, the full offline
Python suite, browser engine batteries and separate self-review.

Repair verification passes. `python -m pytest -m "not smoke"` reports
289 passed and 8 opt-in smoke tests deselected. Browser self-tests pass 83/83,
parity 29/29, property checks 19 properties across 1,473 cases, and worker
checks 90/90. `python scripts/check_static_site.py`, focused Ruff and
`git diff --check` pass. Generated packs are absent, so pack integration
checks and live deployment verification are not claimed.

The original Python and JavaScript probes now report None/null XIRR for
same-day cash flows and WARNING with dated stale-FX messages. Eight Python
regressions and fifteen added browser self-checks cover initial capital,
seven/eight-day boundaries, old FX, valuation and dividend currencies. Two new
golden fixtures preserve the fixed cases. Regenerating golden fixtures changed
only data_quality in five older envelopes; every financial value is unchanged.
Regeneration command: `PYTHONPATH=src python scripts/generate_parity_fixtures.py`.

Separate self-review checked all DCA FX lookup sites, warning order and
deduplication, SGD behavior, unchanged envelope keys, missing-FX errors,
and the existing nonzero-duration XIRR tests. No added code comments or
constraint comments required removal. This is self-review, not independent
review or human product acceptance. Next action is review and normal release;
no deployment, data refresh or roadmap gate completion is part of this repair.

Repair PR: https://github.com/ashcx/sg-investing-v1/pull/9. Regression tests
precede the fix in two commits. The PR targets the merged main baseline;
merge, CI outcome and publication are not claimed.
