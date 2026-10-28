# Sprint completion review, 28 October 2026

Sequential main-instance interrogate review. No application fixes were made.
Scope is Sprint 7.5, 10 and 11 completion, not a new sprint or release.

## Sprint 7.5 complete

Seven consecutive actual scheduled update successes were inspected, on
20, 21, 22, 23, 24, 27 and 28 October 2026 in Singapore time. Latest run:
https://github.com/ashcx/sg-investing-v1/actions/runs/40612140052
Prior run:
https://github.com/ashcx/sg-investing-v1/actions/runs/40430811806
Latest refresh step took 24m36s. Canonical validation passed 281 tests with
8 opt-in smoke tests deselected; complete-summary validation and artifact
upload succeeded. This is actual cron evidence, not manual canary evidence.
The previously documented full-baseline, scoped pack build and artifact
application proofs remain in the Sprint 7.5 execution log.

Latest successful R2 publication:
https://github.com/ashcx/sg-investing-v1/actions/runs/40299324539
The earlier pending run 39112292001 was cancelled and is superseded by later
successful publications, not relabeled successful. Live Pages/R2 manifests
return HTTP 200 and share snapshot
sha256-04cb723d8f46447a0749e02f522034aa5b068ea61842aa1ef27eaef8a5ecdfb1.
Pages contains 1,241 securities; R2 contains 3,186. The two removed listings'
2026 packs return 404 at both origins. Retained publication.json records the
responses and CORS. This does not claim freshly fetched daily artifacts are
automatically applied or published; the workflow deliberately requires review.
Human acceptance of Sprint 7.5 was already recorded on 18 October.

## Sprint 10 and 11 technically complete, acceptance pending

All implementation/design/PR exit items are checked. PRs 2, 3 and release PR 4
are merged. Their GitHub review records and sprint logs contain no additional
explicit product acceptance for Sprint 10 or 11. Publication authorization is
not substituted for acceptance. Their human review exit remains unchecked.

Fresh local Chrome checks passed using synthetic fixtures, not live prices:
- Sprint 10 routes, active destinations, Back/Forward, reload, skip link,
  ISIN/keyboard search, draft identity, pagination through 1,051 entries,
  coverage/methods, reduced motion and responsive layouts.
- Sprint 11 shared setup, independent amounts, initial plus monthly capital,
  price charts, previous-result export, invalid amount, comparison handoff,
  reload-safe drafts, date coverage and responsive layouts.
- Both probes report no browser errors. Mobile captures were visually inspected.

Commands used the installed Playwright module with Chrome and the local static
server on port 4173. Sprint 10 ran tests/browser/sprint-10.cjs with evidence
redirected to /tmp. Sprint 11 ran a temporary copy of tests/browser/sprint-11.cjs
with its comparison count restricted to button:not(.empty-slot). The original
assertion counted all buttons and failed 2 != 1 because Sprint 12 deliberately
adds an empty selection slot. This one candidate finding is dropped as test
expectation drift, proven by frontend/app.js rendering and the successful rerun.
No repository test or application code was changed to make the review pass.

No independent reviewers ran under the project's explicit no-delegation rule.
No product acceptance or deployed DCA-repair verification is inferred.

Focused deterministic verification also passed 97 tests in 4.11s:
`python -m pytest tests/test_incremental_update.py tests/test_incremental_coverage.py tests/test_shared_history.py tests/test_listing_removal.py tests/test_provider_guard.py tests/test_yahoo_provider.py tests/test_dca_initial_lump.py tests/test_dca_regressions.py`.

## Subsequent human acceptance

On 28 October 2026, after the review results were presented, the human Product
Owner explicitly accepted Sprints 10 and 11 with "yes go ahead and accept".
Their acceptance exits and roadmap statuses are now Complete. Earlier pending
acceptance statements in this report describe the review-time state and are
superseded by this recorded decision.
