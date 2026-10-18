# Incremental-update recovery — 18 October 2026

**Current status: draft; full GitHub-runner recovery is reopened.** The local full run and GitHub canary passed, but the actual full GitHub run failed safely after its circuit classified a response as rate limiting. Only diagnostics uploaded. R7 must repair and reverify the full workflow before merge.

Implementation and subsequent self-review performed sequentially in the main
instance. No UI changes, engine formula changes, canonical production refresh,
automatic commit or deployment are included. This work is the user-required
prerequisite to the separate Sprint 12–15 PRs.

## Changes

- Exact-window price groups, bounded batch-capable calls, and incoming-key-only
  comparisons per market/year. Healthy listings cannot inherit a stale peer's
  thirteen-year download. Listing/currency identity is checked before upsert.
- The incremental live Yahoo path uses individual, raised-error price queries
  and explicitly dated event history. All datasets share request pacing,
  transient-only retry/backoff, a rate-limit circuit and request/time budgets.
- Successful empty action queries persist their coverage cursor; missing or
  failed history retains failed coverage. Explicit provider no-history windows
  are reported separately for operator review, preserving old rows and unknown
  event coverage; they never establish delisting or zero events. Broken requests,
  missing FX and a refresh with no updated listings remain fatal.
  FX rows outside inclusive requested dates
  are filtered at the provider boundary.
- Journaled stages, completed counts, elapsed time and peak process memory;
  nonzero CLI status on incomplete input or pack failures; full-refresh schedule
  removed; bounded/shared-concurrency daily workflow with diagnostic uploads.
- Scoped updater builds refuse a missing, filtered, unsafe or incomplete pack
  baseline, including compatible catalog/schema/methodology and every canonical
  priced security/year. CI defaults to canonical review artifacts; optional packs are a full
  build. Operator application/publication remains an explicit separate step.
- Test runtime constraints plus dependency inventories. The clock-dependent
  pack-byte test now controls its generation-time input, retaining exact byte
  assertions without relying on two builds completing in the same wall second.

## Checks

| Check | Result | Record |
| --- | --- | --- |
| Python normal suite | 265 passed, 8 opt-in smoke deselected | [pytest.txt](pytest.txt) |
| Ruff, changed Python | Passed | [ruff.txt](ruff.txt) |
| Engine | 68/68 | [engine-selftest.txt](engine-selftest.txt) |
| Golden parity | 27/27 | [parity.txt](parity.txt) |
| Initial plus recurring cases | Passed | [initial-lump.txt](initial-lump.txt) |
| Workers | 90/90 | [worker.txt](worker.txt) |
| Properties | 19 / 1,473 cases | [properties.txt](properties.txt) |
| Full pack build | 3,188 securities; 55,574 packs; 13,422,888 price rows | [pack-build.json](pack-build.json) |
| DCA pack integration | 29 checks passed | [dca-packs.txt](dca-packs.txt) |
| Portfolio pack integration | 14/14 | [portfolio-packs.txt](portfolio-packs.txt) |
| Static site with generated packs | Passed | [static-site.txt](static-site.txt) |

The full pack build is 1,855,763,530 bytes. Existing coverage gaps are preserved:
four catalog entries lack prices; the snapshot lacks required CNY/EUR/GBP FX
history. A generated complete pack set is not a claim of complete market data.

A read-only whole-catalog recording probe selected 3,172 listings, made 106
fake batch calls capped at 32, and kept QQQ at 2026-07-13 while M12.SI remained
alone at 2013-01-21. It made zero network calls/canonical writes.

## Live canary

The initial QQQ/ES3.SI/VALL.SW canary failed closed on a Yahoo FX observation
outside requested dates. The corrected adapter was regression-tested; a fresh
copied-snapshot run completed with all three updated, 141 price rows, 67 FX rows,
nine requests, no retries/rate-limit circuit, approximately ten seconds elapsed
and approximately 1.8 GiB peak process memory. No copied data was applied to the
repository. Full current canonical snapshot identity was verified unchanged:
`sha256-8121f966801bd011f59892f8a71cf3d872b6358ad5557aa5032f2ce46e769d67`.

- [Initial incomplete outcome](live-canary-summary.json)
- [Initial diagnostic trace](live-canary-diagnostics.log)
- [Corrected complete outcome](live-canary-fixed-summary.json)
- [Corrected diagnostic trace](live-canary-fixed-diagnostics.log)

The compact summaries omit the thousands of unselected dividend-coverage rows
and the raw change-key list; full responses remain in the disposable canary
folders for inspection. Selected outcomes, errors and telemetry are retained.

## Full-universe rehearsal and final policy canaries

The first full-universe rehearsal finished in 1,601.935 seconds (26m42s), peak
process RSS 2,183.34 MiB. It made 9,515 provider requests with no retries or
rate-limit circuit, fetched 214,653 price observations and updated 3,138 listings.
It exited 1/incomplete: 32 explicit no-history price errors, two empty usable-price
results, 34 dividend errors and 32 action errors. FX completed without errors.
This run used the stricter initial absence policy; it is retained as an actual
failure, not relabeled using later code.

The final candidate's QQQ/WBD/ATAI/40F.SI canary also exited 1 correctly.
40F.SI is explicitly reported unavailable across all three datasets. WBD and
ATAI remain unexplained unusable-price warnings: direct provider inspection
found one row each, with opening price zero. No replacement price was inferred.
A subsequent QQQ/40F.SI-only canary passed with
`ready_for_review_with_unavailable`, proving the typed absence policy while
retaining old observations and failed/unknown event coverage. These manual runs
are not scheduled-run or publication evidence. All six GitHub checks for
candidate 621e37a passed.

- [Full rehearsal failed listings, reasons and telemetry](live-full-initial-summary.json)
- [Full rehearsal stage/resource trace](live-full-initial-progress.json)
- [Full rehearsal diagnostics](live-full-initial-diagnostics.log)
- [Final candidate with malformed listings: incomplete](live-policy-canary-incomplete-summary.json)
- [Supported plus explicit absence: review-ready with warnings](live-policy-supported-absent-summary.json)

Compact full-rehearsal summaries retain every failed/warning listing, event-query
error and provider telemetry, while omitting successful per-listing rows and raw
change keys. Full responses remain in the disposable folders.

## Remaining gates

Product Owner explicitly chose to remove WBD and ATAI entirely. Migration
removed 6,622 observations from 22 US year partitions and three memberships.
All remaining row values/schema were verified unchanged. Active catalog,
coverage/backfill records and public catalog are rebuilt; 3,170 catalog entries
remain. Permanent exclusions prevent restoration through catalog refreshes or
full/scoped pack builds. Rebuilt full packs: 3,186 securities, 55,546 packs,
13,416,266 price rows. Static checks and DCA (29)/portfolio (14) integrations pass. Desktop/mobile
search checks at 1440/390px confirm both tickers absent and QQQ discoverable,
with no page errors; retained captures were visually inspected. Final suite:
262 passed, 8 smoke deselected using explicit PYTHONPATH=src so subprocesses
load this checkout. The initial shared-editable-path failure is retained.
[Removal record](listing-removal.json), [pack build](pack-build-after-removal.json).
The final full live fetch passed on its disposable copy: 3,138 updated listings,
32 explicit unavailable price windows, zero failed updates or FX errors;
9,509 provider requests, zero retries/rate-limit circuit, 1,607.129s elapsed,
peak RSS 2,241.19 MiB. This is handled-run success with explicit coverage gaps.
[Final live summary](live-full-after-removal-summary.json),
[resource trace](live-full-after-removal-progress.json).

Corrected scoped rebuilding then passed: 55,161 packs replaced across 3,167
touched listings, 85 year-pack coverage records verified, 387 untouched packs
byte-identical. Final set: 3,186 securities / 55,548 packs / 13,525,569 prices;
168.842s build time. Complete post-update baseline and disk/manifest consistency
pass; neither removed ID remains. DCA 29/29 and portfolio 14/14 integrations pass
on these actual live-data packs. The initial missing-vendor-asset harness failure
is retained separately; the unchanged asset was copied and integrations rerun.
[Scoped verification](live-scoped-pack-verification.json),
[DCA](dca-live-scoped-packs.txt), [portfolio](portfolio-live-scoped-packs.txt),
[consistency](live-scoped-consistency.txt).

These are a live no-build fetch and a subsequent corrected scoped build, not an
actual scheduled workflow run. Earlier failures are retained. No production
snapshot or deployed origin was changed by the disposable live rehearsal.

Actual scheduled runs require the reviewed workflow on the default branch and
successive scheduled successes. Manual runs cannot stand in for that evidence.
Operator canonical application/publication, including removal of old R2 objects,
must be verified separately. Sprint 7.5 remains In progress, and later interface
gates are not bypassed.


Local Pages preparation after removal also passed: 1,241 securities / 24,015
packs, 766,875,156 bytes including manifest (950 MB limit). Both removed IDs
and directories are absent. [Prune and consistency report](pages-prune-after-removal.txt).
Full Tier-2 source remains intact and excludes both listings; no remote sync
or deployed-origin deletion is claimed. All six GitHub checks passed for runtime
head 7c6b4e3; all six passed for roadmap head 1497d91.


Scoped support-state invalidation regression reproduced and fixed: a failed
query with no changed observations previously left old successful dividend
coverage in stored packs. Changed success/error states now invalidate all
stored years for that listing, including recovery after a failure. Unchanged
states and query timestamps alone do not invalidate packs. Initial failure is
retained; full suite now passes 262 tests with 8 opt-in smoke deselected.
The live fetch run started before this pack-selection-only fix; provider and
fetch behavior are unchanged. Its output was tested through the corrected
scoped selection/build separately, without claiming a new live fetch run.


## Runner-specific follow-up (R7)

The [GitHub canary](https://github.com/ashcx/sg-investing-v1/actions/runs/39094143813) passed every stage; both uploaded artifact digests were verified, and applying its actual update archive reproduced the producer's canonical chain hash. The [full GitHub run](https://github.com/ashcx/sg-investing-v1/actions/runs/39094315718) then failed after 414.375s, peak RSS 2,254.27 MiB and 2,384 guarded calls. The first circuit outcome was GRPN. The original exception was not retained; no exact provider quota or false classification is established. A local isolated GRPN query succeeds. No validated full-run artifact or deployment was produced.

The guard now retains exact exception/call context and rejects arbitrary numeric 429 substring matches. Actual HTTP status, vendor type and explicit rate-limit messages still stop traffic. Full suite: 265 passed, 8 smoke deselected. This diagnostic repair alone does not solve cloud throughput. Next: bounded response reuse across each listing's own price/dividend/action windows, preserving individual windows and unknown-data semantics, then actual full-run verification. The [documented yfinance cache](https://ranaroussi.github.io/yfinance/advanced/caching.html) covers timezones and cookies; it is not evidence that these history calls are reused. No quota, new source or provider-identity rotation is assumed.
