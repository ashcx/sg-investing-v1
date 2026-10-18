# Sprint 7.5 post-merge verification — 18 October 2026

Merged release: b66bd54f93afe56b55e796bab382d0f46b3ae272.
The Product Owner explicitly accepted Sprint 7.5 and merged PR #5. This report
checks the actual merged release; it does not represent later-sprint work.

## Verified so far

- Main backend, engine parity and static workflows pass. Retained excerpts:
  [main CI results](main-ci-excerpts.txt).
- Runtime, configuration, workflow, tests, frontend and canonical data match
  candidate 75ffcf9 exactly. The earlier full-catalog run remains applicable:
  [full-catalog evidence](../incremental-recovery-2026-10-18/shared-history-github-full-verification.json).
- Fresh four-listing update on main passes: QQQ, GRPN, ES3.SI and unavailable
  40F.SI. Five uncached calls/eight cache hits; no retry or circuit; event cache
  released to zero. The full post-update suite passes 277 tests.
  [main canary](main-canary.json), [job excerpt](main-canary-job-excerpt.txt).
- Both main-canary artifact digests verified. Applying its actual uploaded
  archive to a fresh disposable baseline reproduces the producer's snapshot:
  [application proof](update-application.json).
- [Pages deployment](https://github.com/ashcx/sg-investing-v1/actions/runs/39111805264)
  succeeded and the public build-info names that run.
- Live QQQ, recurring investing, previous-result identity and Tier-2 GRPN
  pass at 1440px and 390px. No page errors, HTTP errors, calculation API calls
  or unintended page overflow in those checked states:
  [browser results](browser.json), [desktop](live-qqq-1440.png),
  [mobile Tier-2](live-tier2-390.png).
- Live QQQ 2000–2001 calculation and pre-2003 USD/SGD conversion pass:
  [FX history check](fx-2000.json), [capture](live-fx-2000.png).
- Public Pages/R2 manifests share the expected snapshot; catalog has 3,170
  unique securities, both removed IDs are absent, sample QQQ/GRPN packs load,
  and browser-origin CORS is valid. These are public endpoint/sample checks,
  not a claim that the whole R2 synchronization has completed:
  [publication probe](publication-pending-deletion.json).

## Important limits

The update workflow uploads validated review artifacts; it does not automatically
apply/commit the fetched data or publish new prices. This merge publishes the
requested listing removals from the existing committed snapshot. The public
data-status date is still 2026-08-31; a new build date is not fresh market data.

No new canary data was applied to the source repository or published. Manual
workflow_dispatch success is not cron success. The schedule is 06:00 Singapore
Tue–Sat; its next opportunity after this Sunday merge is Tuesday 20 October.
Successive actual scheduled successes remain required by the operational exit.

The first browser-harness selector assumed whitespace between adjacent ticker
and name elements. It timed out; matching the actual ticker element fixed the
harness. No application code or financial expectation was changed.

## Publication checks in progress

R2 synchronization run 39112292001 is active. Manifest, catalog, CORS and real
Tier-2 calculations are verified, but old WBD/ATAI 2026 files still return 200
while synchronization is in progress. Their public deletion and the terminal
workflow result remain pending. The previous successful synchronization took
about 64 minutes; this current wait is not itself a diagnosed failure.

A pre-existing presentation inconsistency was observed in the GRPN result:
the detail text says dividend data is not confirmed, while the quality badge
reads “Data quality OK” and the material-note count is zero. The financial
disclosure is present; the badge should be reconciled during the already-planned
S14/S15 warning/copy review. No financial logic or UI changed during this test.

A headerless Python R2 probe received HTTP 403 during synchronization. A probe
using the real site's Origin and browser User-Agent returned HTTP 200, valid
CORS and the new snapshot ID. Final verification uses those public browser
request headers and actual Chrome requests; this is not treated as proof of a
general origin outage or a completed synchronization.
