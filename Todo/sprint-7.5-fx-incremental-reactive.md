# Sprint 7.5 — FX to 2000, incremental updates, reactive UI

## Goal

Three usability-closing workstreams: (A) source reliable FX history back to
2000-01-01 so foreign-currency securities stop starting at 2003-12; (B) make
the data store incrementally updatable — any new date or date range, without a
full 6-hour rebuild; (C) staged auto-loading in the UI so charts and results
appear without pressing "Run".

## Entry criteria

- [x] Sprints 0–7 exit criteria are all met (verified 2026-09-01).

## Depends on

Sprint 7. Independent of Sprint 8 — may run before, after, or alongside it
(only minor coordination: both may touch CI workflows).

## Track A — FX history back to 2000

Current state: USD/SGD (Yahoo) starts 2003-12-01, capping the foreign-currency
investing timeline. Required pairs derive from catalog native currencies
(USD, GBP, EUR, JPY, HKD, CNY, …).

- [x] **A0 (decision — updated 2026-09-02):** **MAS is REMOVED as a required
      source** (availability re-checked: API 404 + statistics section still
      on maintenance failover). **ECB is the primary backfill source**;
      reliability cross-checks: frankfurter.app (ECB mirror) + the weekly MAS
      data.gov.sg mirror as an optional tertiary sanity check only. Splice, minimal pull: do NOT re-pull
      the existing 2003+ Yahoo FX; backfill ONLY 2000-01-01 → 2003-11-30 for
      the currency pairs actually needed by securities with pre-2003-12 data
      (derive the pair list from the store; USD dominates). Normalization:
      compute a ratio over the last overlapping month (existing vs MAS rates)
      and scale the MAS window so no level seam enters SGD returns. Record as
      `docs/adr/0002-fx-sources.md`. Data rationale: 1,297 of 3,188 securities
      (40%) predate 2003-12; 0 fully_supported today; 4,936 pre-2004
      security-years already fetched but FX-locked (QQQ/SMH/SOXX/AAPL/MSFT
      first years).
- [x] A1 (resolved by decision 2026-09-02): MAS dropped after re-check (404 +
      maintenance failover confirmed live). Original task was: verify MAS actually covers the missing window for the required
      pairs (api.mas.gov.sg "Exchange Rates — Daily" dataset, or MAS
      statistical-table CSV/XLSX downloads, or a data.gov.sg mirror — register
      for a free API key only if unavoidable and report the requirement). If
      MAS cannot cover a pair/date range, report the exact gap — do NOT
      silently substitute another source. Cross-check every MAS rate against
      ECB (frankfurter.app, no key) and record divergence stats.
- [x] A2: splice with normalization: compute a normalization ratio over the
      overlap boundary (average ratio of new-source vs existing rates over the
      last overlapping month) and scale the backfilled window to it, so no
      level seam enters SGD returns. Document the seam + normalization in pack
      provenance and result warnings for affected ranges.
- [x] A3: implement `scripts/backfill_fx_history.py`: fetch, normalize to the
      existing FX row contract (one unit foreign = X SGD, daily), validate
      against the overlapping 2003+ Yahoo window (record divergence stats in
      the summary), write to `data/fx` Parquet with source provenance.
- [x] A4: rebuild packs; confirm the manifest classifies 2000+ years as
      `fully_supported` for covered currencies; rerun the parity battery
      (FX is input data — the engine is untouched; some parity fixtures pin
      old FX values and must be regenerated deliberately).
- [x] A5: document source, semantics and staleness in `docs/fx-sources.md`
      and surface `fx_source` in pack provenance.

## Track B — incremental updates (no full rebuild)

- [x] B1: design note: incremental update contract. Reuse the existing
      storage layer (upserts keyed by security+trading_date, atomic partition
      replacement, validation gates). Per security, fetch only missing dates
      since its stored `last_date`; fetch a trailing reconciliation window for
      late-arriving dividends/splits; fetch FX tail. Bump `data_snapshot_id`
      as an incremental snapshot (base id + change set).
- [x] B2: implement `scripts/update_incremental.py --since <date|auto>
      [--securities …]`: minutes, not hours; writes an incremental
      `update_summary.json`; rebuilds ONLY touched security/year packs
      (extend `build_data_packs.py` with a `--years` filter).
- [x] B3: tests (synthetic fixtures, no live network): tail fetch, gap
      backfill, late dividend reconciliation, pack rebuild scoping, manifest
      update.
- [x] B4: scheduled workflow `update-incremental.yml` (daily after US close +
      manual dispatch) that optionally chains a Tier-1 redeploy; the full
      rebuild stays as a manual quarterly reconciliation.
- [x] B5: runbook in `docs/data-updates.md`.

## Track C — staged auto-loading (reactive UI)

Request-isolation machinery (supersede, stale guards, cached manifest)
already exists from Sprints 4–6; this sprint wires it to be automatic.

- [x] C1 (stage 1): selecting a security (catalog card or dropdown) auto-loads
      its series chart — no submit required. Series is prices+FX only (cheap).
- [x] C2 (stage 2): the analysis form auto-runs debounced (~750 ms) on any
      change of security/dates/scenario; supersede in-flight runs; button
      becomes "Force refresh"; `unavailable` renders as an inline notice, not
      an error spam.
- [x] C3 (stage 3): same treatment for DCA and portfolio (ledger auto-runs on
      row change, debounced).
- [x] C4: browser tests: debounce fires exactly once per burst; a stale
      response never overwrites a newer one; rapid parameter changes settle on
      the last state; battery stays green.

## Exit criteria

- [x] Track A: manifest shows `fully_supported` back to 2000 for covered
      currencies; source decision recorded (ADR 0002); parity battery green
      with deliberately regenerated fixtures.
- [ ] Track B: a typical daily incremental update completes in minutes with
      scoped pack rebuilds; scheduled workflow green.
- [x] Track C: all three stages browser-verified; no stale results possible.
- [x] Full verification battery green (pytest 172+/8, selftest 68/68, parity,
      property, worker, integration suites, static checks, live-site check).
> **Blocker (2026-09-01) — Track A execution:** MAS is inaccessible —
> `api.mas.gov.sg` does not resolve; `eservices.mas.gov.sg/api` serves a
> maintenance failover page; the entire `www.mas.gov.sg/statistics/*` section
> serves maintenance pages; the data.gov.sg mirror is weekly-only in-window
> (violates the 7-day staleness rule), server-capped at 1,000 rows, ends
> 2003-11-12, and has no HKD/JPY columns. Per the A0 instruction the agent
> STOPPED rather than substitute sources. All infrastructure is complete and
> tested (22 fx tests; cross-check machinery verified — frankfurter covers the
> full window for all 3 required pairs: USD, HKD, JPY). Re-run is one command
> per docs/fx-sources.md once MAS restores access. **Open decision for the
> coordinator/user:** wait for MAS, or pivot the primary to ECB (already
> verified to cover the full window) with MAS as the later cross-check.

## Subsequent scope amendment (15 October 2026)

The Product Owner adopted explicit Calculate/Update for the redesign in
[Sprint 9](sprint-9-user-experience-redesign.md). Financial edits will label
retained results previous until recalculated, replacing automatic financial
recalculation while preserving request identity and preventing stale outputs
from appearing current. Automatic series/data loading may remain. This is
planned Sprint 9 work; the checked Sprint 7.5 tasks and exits describe the
historically shipped baseline and are not evidence of redesign completion.

## Operational recovery amendment — 18 October 2026

Status: **In progress** for Track B operational recovery. Historical completed
implementation tasks remain recorded above; the daily-operation exit is reopened
because current production evidence contradicts it. User requested careful
troubleshooting of daily failure emails, separately from the redesign. No next
redesign sprint is started by this investigation. Main-instance ownership only.

- [x] Inspect scheduled runs and logs, compare against pre-redesign code,
      reproduce fetch-plan behavior offline, and record findings and checks.
- [x] Repair bounded fetching, memory usage, provider retry behavior, workflow
      scheduling/diagnostics, and incomplete-result reporting sequentially.
  - [x] R1: group price calls by exact window in bounded batches; compare only
        incoming security/date rows, preserving restatement and gap detection.
  - [x] R2: bound provider event queries, pace requests, back off retries and
        stop new provider traffic on rate limits; retain missing/empty semantics.
  - [x] R3: make full refresh manual, cap daily runtime, preserve diagnostics
        on failure and prevent incomplete data from being labeled publishable.
  - [x] R4: require a complete pack baseline or an explicit full pack build;
        document artifact application and run full offline regression checks.
- [ ] Verify the canonical application/pack-baseline/publication process and
      retain live canary/full-run resource evidence and successive green daily runs
      before restoring the Track B operational exit.

Investigation result: ten sampled incremental failures and ten full-refresh
cancellations on pre-redesign commit 6ab5ac2. Offline probe confirms a stale
2013 listing widens all 3,168 batch securities to 2013; price change detection
would retain before/after dictionaries covering 13,422,888 rows. Logs explicitly
show Yahoo throttling and runner termination; the termination cause is not
proven. Focused offline suite: 40 passed in 2.36 seconds. No canonical data,
workflow, provider behavior, or deployment changed. Separate self-review checked
that resource-pressure inferences are not presented as confirmed OOM and that
local-store dates are not represented as live deployment freshness.

Full evidence, run URLs, limitations, and next sequential repair actions:
[investigation report](../docs/incremental-update-investigation-2026-10-18.md).
No operational fix or successful daily update is claimed by this amendment.


### 18 October 2026 — recovery execution entry

User explicitly chose to resolve this recovery before Sprints 12–15. Verified
original Sprint 7 entry checklist and historical evidence; the reopened operation
exit remains unchecked. Branch `codex/recover-incremental-updates` is isolated
from pending redesign plans on current main 32a25f7. No canonical data or deployed
interface is changed by code tests. Execute R1 → R2 → R3 → R4 sequentially, then
live canary/full-universe evidence and actual scheduled-run verification. Runtime
and financial result-envelope/decimal semantics remain unchanged.
Current action: R1 exact-window batching and bounded change detection.


### R1 complete — bounded price work, 18 October 2026

Grouped exact start windows, capped batches at 32 listings, and included missing-
history listings in isolated window groups rather than the old per-security
full-store scan. Healthy recent tails execute before historical repairs. Before/
after comparisons project only incoming security/date keys, one market/year at
a time; currency/listing identity is checked before canonical upsert. Existing
storage validation/atomicity remains intact.
Checks: incremental suite 22 passed in 2.40s, including four new regressions for
stale-peer batching, nonbatch windows, projected keys, new rows/restatements.
Changed-file Ruff passed. Read-only whole-catalog recording probe: 3,172 listings,
106 calls, maximum 32 per batch; QQQ starts 2026-07-13 while M12.SI remains alone
at 2013-01-21. Zero network calls and canonical writes. Separate self-review
removed the former straggler action fetch to avoid duplicate event retrieval;
events remain in their dedicated reconciliations. No operational recovery claim.
Next sequential action: R2 bounded event queries and request resilience.


### R2 complete — bounded live queries and request containment

Incremental Yahoo mode now uses explicitly dated, actions-enabled history for
dividends/splits (with errors raised and 20-second request timeout), preserving
the ordinary provider path for existing full-refresh callers. Missing history
or omitted event columns are errors, not confirmed zero events. Successful empty
action queries record a durable cursor, preventing repeated inception-to-present
requests; failures never advance it.
A run-scoped provider guard serializes/paces calls, retries transient failures
with exponential delays, bounds total requests/time, and opens a shared circuit
on rate limits. It uses individual listing calls so batch-downloader exception
suppression cannot conceal throttling. Backfill's immediate retries are disabled
for the guarded live provider; deterministic fake-provider behavior is retained.
Checks: 51 focused tests passed in 2.81s (incremental/provider/backfill suites),
including bounded queries, missing-vs-zero events, successful/failed action
cursors, shared circuit, request budget and retry pacing. Separate self-review
checked error states, no fake-provider network, and preservation of dividend
currency/classification and split/bonus semantics. Market-data extra installed
in the existing isolated test environment: yfinance 1.7.0 API inspected locally.
No live data query or canonical production write yet. Next: R3 diagnostics,
scheduling and explicit incomplete-result status.


### R3 complete — observable, bounded, non-publishing refresh workflow

Added a durable stage/resource journal outside canonical data. Final summary
records complete/incomplete and review readiness; provider errors, absent price
observations, event/FX errors, circuit exhaustion and pack errors cannot return
a successful CLI status. Diagnostics survive ordinary process failure through
checkpoint files; hard runner termination may still prevent artifact upload.
Incremental workflow now has a 55-minute limit, shared canonical-update
concurrency, 22:00 UTC daily schedule, manual canary selectors and optional full
pack build. Full refresh is manual with a 330-minute limit. Diagnostics upload
is always attempted; publication artifacts are collected only after complete
summary and full Python verification. Refresh does not auto-commit or deploy.
Checks: 45 focused tests passed in 2.68s; changed-file Ruff passed. Added CLI
incomplete-exit, failed-FX/journal and workflow schedule/diagnostic/concurrency
regressions. Separate self-review kept canary inputs in environment variables
and avoided successful-publication claims from a green fetch alone.
Next sequential action: R4 full-baseline gate, documentation and full battery.


### R4 complete — baseline/publication safety and offline battery

Scoped updater pack builds now require a complete unfiltered catalog baseline
and existing safe pack paths before provider calls or canonical writes. CI uses
no-build mode by default and only creates full pack sets when requested; the
operator runbook distinguishes canonical review artifacts, failed diagnostics,
complete packs and actual publication. Runtime constraints and dependency
inventory added for repeatability. Structural baseline validation does not
certify an externally restored snapshot's content freshness; restore matching
reviewed canonical data and packs or perform a full build.

Full committed-store pack build: 3,188 securities, 55,574 packs, 13,422,888 price
rows, 1,855,763,530 bytes. Existing support gaps remain explicit: 4 catalog
securities lack prices; CNY/EUR/GBP FX history is absent in this snapshot.
Battery: Python 245 passed, 8 smoke deselected in 6.72s; engine 68/68; parity
27/27; worker 90/90; properties 19 / 1,473 cases; initial-lump cases passed; DCA
packs 29 checks passed; portfolio packs 14/14; static-site passed with full packs;
changed-file Ruff passed. Reports: `docs/incremental-recovery-2026-10-18/`.
A repeated suite initially exposed the preexisting wall-clock-dependent pack
byte-comparison test; it now controls the generation-time input, preserving
its full-byte assertion while removing second-boundary flakiness. No runtime
pack generation-time semantics changed.

Separate self-review checked fail-closed provider/pack status, safe artifact
collection (including new checkpoint files), no automatic commits/deployment,
no UI/engine changes, and no ignored baseline failures. Added missing-FX and
skipped-action incomplete flags plus a post-pacing deadline check.
Next: small live canary on a disposable copied snapshot; no canonical production
data or public site changes. Operational gate remains open.


### Live canary and final self-review follow-up

Initial canary correctly exited incomplete after ingestion rejected a Yahoo FX
observation dated 2026-10-18 outside requested end 2026-10-17. Bounded provider
normalization now filters FX dates inclusively; a new regression covers both
boundaries. Fresh copied-snapshot rerun passed: QQQ/ES3.SI/VALL.SW all updated,
141 price rows and 67 FX rows, nine provider calls, zero retries/circuit errors.
Approximately ten seconds elapsed, peak process RSS approximately 1.8 GiB, from
existing year-partition storage validation. Original canonical snapshot hash is
verified unchanged. Initial failure and corrected result are both retained.
Further self-review restricted retries to transient failures and added completed
counts to long-running price/event journals. Final Python battery: 248 passed,
8 opt-in smoke deselected in 6.60s; changed-file Ruff passed. Prior browser-engine
and generated-pack checks remain valid: neither engine nor committed snapshot
changed. Next: full-universe live run on another disposable copied snapshot.


Recovery draft PR published: https://github.com/ashcx/sg-investing-v1/pull/5
Branch `codex/recover-incremental-updates`, initial head e217145. Local full-
universe run remains active on its disposable copy; no success or restored
schedule is claimed. Separate Sprint 12–15 PRs remain pending the required
prerequisite and human review gates.


PR #5 initial head e217145: all six GitHub checks passed. Subsequent self-review
also added always-attempted diagnostic retention and an explicit incomplete-
artifact guard to the manual full-refresh workflow; its prior script can report
failed listings while returning zero. Focused incremental/workflow tests: 30
passed in 2.28s. No runtime code changed after the final 248-test battery.
Full-universe local verification remains active on the disposable copy.


### Full-universe evidence follow-up — explicit unavailable windows

The live rehearsal exposed explicit Yahoo no-history responses for a small
set of listings. This is not proof of delisting. Recovery reporting now
separates typed provider no-history windows from broken requests. Existing
observations remain intact; dividend coverage remains failed/unknown and action
query checkpoints do not advance. Handled runs with these gaps are marked
`ready_for_review_with_unavailable` with per-dataset reasons. Missing FX,
malformed data, timeouts, rate limits, untyped errors and runs with zero updated
listings remain incomplete. No publication happens automatically.
This clarifies R3's incomplete-result policy within this sprint; financial result
envelopes, coverage classifications and engine calculations are unchanged.
Regression checks cover mixed supported/unavailable listings, untyped errors,
all-unavailable prices, mandatory FX and retry/circuit behavior. Full-baseline
proof also checks catalog/schema/methodology identity and every priced year,
including priced-but-uncatalogued securities. Final full run evidence remains
pending; the earlier live run uses the prior stricter failure classification
and its actual outcome will be retained separately.


### Full rehearsal finished; final candidate and roadblock

Full rehearsal: 3,172 selected, 3,138 updated, 214,653 prices fetched;
26m42s elapsed, peak RSS 2,183.34 MiB; 9,515 requests, zero retries/rate-limit
circuit. It correctly exited incomplete under its initial stricter absence
policy (32 price errors, two unusable-price warnings, 34 dividend errors,
32 action errors; FX succeeded). Retained actual outcome is not rewritten.
Final candidate 621e37a: all six GitHub checks passed; Python 256 passed,
8 smoke deselected; Ruff passed. Live QQQ/WBD/ATAI/40F.SI canary correctly
remained incomplete. WBD and ATAI each return a zero-open price row; these
malformed observations are rejected. QQQ/40F.SI canary passed as
`ready_for_review_with_unavailable`, preserving explicit coverage failures.
Evidence: `docs/incremental-recovery-2026-10-18/README.md`.
User decision requested under AGENTS.md material-scope rule: explicitly quarantine
WBD/ATAI with retained history and visible warnings, or preserve the global
failure until their source is repaired. No exclusion implemented yet. Next:
apply the user's decision, verify the final full run, and retain actual scheduled
and publication evidence after reviewed merge. Interface gates remain closed.

### 18 October 2026 — authorized removal of WBD and ATAI

Product Owner explicitly requests removing both listings entirely, superseding
the quarantine proposal. Scope amendment: remove their catalog memberships,
canonical price/dividend/action rows, active backfill/coverage records and
published catalog/packs. Persist their listing IDs as exclusions so later
universe refreshes cannot silently restore them. Historical audit records and
Git history remain evidence; no replacement prices or alias substitutions.
- [x] R5: implement persistent exclusions and a reproducible removal migration;
      verify unrelated rows remain identical and both listings cannot reappear.
- [x] R6: rebuild publishable artifacts and rerun the full live recovery rehearsal
      without these two listings; retain results before operational acceptance.
Research is now explicitly selected in the proposal carousel. Sprint 14 remains
subject to its earlier sprint gates and integrated implementation review.


R5 complete: config/catalog exclusions stop source merges restoring either ID;
pack generation also rejects excluded IDs from an old restored price store.
Removal migration deleted 6,622 observations across 22 US year partitions and
removed three membership rows, leaving 3,170 catalog securities / 3,257 memberships.
Every rewritten partition was read back and compared against the exact filtered
original Arrow table, preserving all peer values and schemas. Active state,
coverage and public catalog were regenerated; no historical audit evidence was
erased. Normal suite: 259 passed, 8 smoke deselected; focused removal/universe/
pack suite: 21 passed; changed-file Ruff passed. Separate self-review confirmed
explicit scope authorization, no alias/replacement prices and no calculation
changes. R6 full pack rebuild is active; live rehearsal follows it.

R6 artifact verification: full rebuilt set 3,186 securities / 55,546 packs /
13,416,266 prices; both IDs absent from canonical/public catalog, manifest and
pack directories. DCA 29 checks, portfolio 14/14, static site (55,546 paths)
passed. Browser search at 1440px and 390px: WBD/ATAI absent, QQQ discoverable,
zero page errors; captures visually inspected and retained. Existing presentation
is baseline evidence, not Sprint 14 implementation. Added scoped-merge regression
so even an old pack manifest cannot retain a removed entry or directory.
Final verification command uses explicit PYTHONPATH=src for subprocesses; the
shared test environment's editable installation points to the original checkout.
An initial subprocess-path failure is retained; the final full suite passes
260 tests with 8 smoke deselected, including all five committed Yahoo regressions.
Changed-file Ruff passes. Full live rehearsal session is active on disposable
`/private/tmp/sg-recovery-full-after-removal`; no production publication claimed.


R6 publication preparation: copied the full pack set to an isolated Pages
candidate, pruned the Russell 2000 tier and reran manifest/disk consistency.
PASS: 1,241 securities / 24,015 packs; 766,875,156 bytes including manifest,
within the 950 MB budget. Neither removed ID or pack directory remains in
Tier 1; full Tier 2 absence was already verified. Report retained in
`docs/incremental-recovery-2026-10-18/pages-prune-after-removal.txt`.
This is local publication preparation, not a deployed-origin check. All six
GitHub checks passed for runtime/removal head 7c6b4e3, and all six passed for
roadmap head 1497d91. Existing live rehearsal remains active; do not restart it.

Local operator application rehearsal PASS: created the changed-store archive
from the recovery branch against origin/main, applied it to an unchanged
baseline copy, and obtained exactly the validated data snapshot
`sha256-04cb723d8f46447a0749e02f522034aa5b068ea61842aa1ef27eaef8a5ecdfb1`.
Full pack baseline verification then passed (catalog/schema/methodology,
canonical security/year coverage and existing safe paths). Archive 159,965,722
bytes; checksum and exact file list retained in
`docs/incremental-recovery-2026-10-18/operator-application-check.json`.
This verifies the local application procedure for the reviewed removal data;
it is not scheduled-run evidence or a remote-publication claim. Final live
rehearsal is still active; its outcome and actual operational gates remain open.

R6 self-review follow-up: scoped rebuild selection currently follows observation
changes, so a changed dividend provider failure with no changed observations may
leave old successful coverage metadata in stored year packs. Verify with a
fixed fixture, then repair coverage-state invalidation within R6. This preserves
the existing warning contract; it adds no financial feature or interface scope.
The live no-build fetch rehearsal remains active and unchanged. Its later pack
verification must include the coverage-state invalidation check.


R6 coverage-state regression PASS after reproducing failure: pure provider
failure/recovery now refreshes all stored year packs even with no observation
changes. Stable states do not trigger metadata-only rebuilds. Unique-ID scans
stay Arrow-projected and deduplicated before conversion to Python. Full suite:
262 passed, 8 smoke deselected in 7.18s; changed-file Ruff passes. Scheduled
pre-fetch regressions now include coverage-invalidation and listing-removal
cases. The active no-build fetch began before this pack-selection-only repair;
its provider/fetch path is unchanged. The corrected selection and scoped build
will be verified against its final output separately. Do not call this a second
live fetch run or erase earlier evidence.

Final live fetch after removal PASS: complete=true,
`ready_for_review_with_unavailable`, 3,170 selected / 3,138 updated / 32 explicit
unavailable price windows / zero failed updates. 214,653 prices fetched;
26m47s elapsed; peak RSS 2,241.19 MiB; 9,509 requests, zero retries or rate-limit
circuit; no FX errors. Unavailable event windows remain explicit (34 dividend,
32 action), with failed/unknown coverage. Compact outcome, full progress trace
and diagnostics retained as `live-full-after-removal-*` evidence.
All six GitHub checks passed for coverage-fix runtime head f05023d.

The corrected scoped pack build is now active separately on that same
post-fetch disposable store (process session 79612; harness
`/private/tmp/sg-live-scoped-verification.py`). It adds coverage-state touches to
the original no-build run's observation touches, verifies unchanged pack bytes,
checks current failure metadata across all affected years, and then runs real
DCA/portfolio pack integrations. Baseline gate is verified against the original
pre-update store before rebuilding and against the updated store afterwards;
an initially misplaced post-fetch/pre-build check correctly detected newly
added canonical years and is documented in `live-scoped-harness-baseline-note.txt`.
No product baseline check was weakened. Do not restart the active pack build.
R6 and the operational exit remain unchecked pending final pack results and
actual reviewed scheduled/publication evidence. No UI sprint has started.


R6 local technical verification COMPLETE: corrected scoped rebuild passed on the
actual fetched store. It rebuilt 55,161 packs across 3,167 touched listings,
verified updated coverage metadata in 85 year packs across 39 changed coverage
states, and preserved all 387 untouched packs byte-for-byte. Rebuilt manifest:
3,186 securities / 55,548 packs / 13,525,569 price rows; two catalog listings
remain without prices. Both removed IDs remain absent. Complete post-update
baseline and full manifest/disk consistency checks pass. Pack build 168.842s;
separate live fetch 1,607.129s. Real DCA 29/29 and portfolio 14/14 checks pass
against these rebuilt live packs. The initial integration harness omitted the
unchanged Decimal vendor asset; the missing-module result is retained, the
asset copied, and integrations rerun successfully. No engine code changed.
Evidence: `live-scoped-pack-verification.json`, `dca-live-scoped-packs.txt`,
`portfolio-live-scoped-packs.txt`, `live-scoped-consistency.txt` under the recovery
evidence directory. Live rehearsal and subsequent corrected scoped build are
separate phases; neither is represented as an actual scheduled run.

All recovery implementation/locally executable tasks are complete. Overall
Sprint 7.5 stays In progress: reviewed merge, actual successive scheduled runs,
and remote Pages/R2 publication verification are still required. No later sprint
entry gate has been ticked, and no human acceptance is invented. Recovery PR #5
is ready for Product Owner review; its merge triggers the existing deployment
workflow and subsequent R2 synchronization.

Additional runner-specific operational preparation: actual GitHub branch canary
PASSED, run https://github.com/ashcx/sg-investing-v1/actions/runs/39094143813
(manual workflow_dispatch, head 2120273). Ubuntu/Python 3.11 constrained install,
pre-fetch regressions, QQQ/40F.SI live refresh, 262-test post-fetch validation,
changed-store archive collection and both artifact uploads all succeeded.
Downloaded artifacts verified against GitHub SHA-256 digests; applying the actual
uploaded update archive to a disposable baseline reproduced the producer's
canonical chain hash exactly. Updater 20.972s / peak RSS 1,792.65 MiB;
seven provider calls, zero retries/circuit. Retained token-free summaries,
dependency inventory and application proof under `github-canary-*` evidence.

The full-catalog workflow is now active on the same PR branch/runner platform:
https://github.com/ashcx/sg-investing-v1/actions/runs/39094315718
(run id 39094315718; event workflow_dispatch; exact source head 2120273;
no packs/artifacts are published automatically). This checks the original full-
job failure environment rather than substituting a small canary. Inspect that
specific run/jobs until terminal; do not restart it on an observation timeout.
Neither manual run counts toward actual successive scheduled successes.
Merge/publication and future human-review progression decisions remain pending.

### R7 — runner-specific request pressure, reopened 18 October 2026

Actual full GitHub runner test FAILED safely after 2,384 guarded calls in
414.375s, peak RSS 2,254.27 MiB. Guard classified the GRPN price call as a rate
limit; remaining network traffic stopped, validation/publication were skipped,
and diagnostics uploaded successfully. The original exception was not retained,
so do not claim a documented Yahoo quota or infer OOM. Direct isolated GRPN
query on the local network succeeds. Canary success does not prove full-run
recovery. PR #5 returned to draft; merge approval is on hold pending repair.

- [x] R7: preserve exact circuit cause, eliminate false numeric rate-limit
      matches, reduce redundant per-listing history requests with bounded reuse,
      and reverify the complete workflow on GitHub's runner. Reuse must keep each
      dataset's requested date window, unknown/empty semantics and event currency,
      bound memory, and retain circuit/time/request limits. Do not replace the
      full-catalog check with a canary or count manual runs as scheduled success.

Implementation direction: a single actions-enabled history for each listing's
own required union window can serve its separately filtered price, dividend and
split queries. Retain only compact event columns/index, with a strict cache
budget and no cross-listing window widening. Cache hits must not consume a
provider request or delay. A slower minimum interval applies to actual uncached
calls; existing 40-minute provider / 55-minute workflow limits remain unless
verified evidence requires an explicitly documented amendment. Full-refresh
provider behavior and financial calculation contracts remain unchanged.


R7 diagnostic substep complete: exact exception type/message/symbol/request index are retained, with URL credential values redacted. Numeric values or IDs containing 429 cannot open the circuit; real HTTP status/vendor type/explicit rate-limit responses still stop traffic. Full suite 265 passed / 8 smoke deselected; guard suite nine cases; Ruff passed. No new full run has been started before the request-reuse repair.

Next implementation: compute each live listing's required union of existing price, dividend-coverage and action-checkpoint windows. Query once with actions, then filter each dataset to its original individual window. Cache only deep-copied event columns/index and any explicit event currency, under a 512 MiB cap, releasing entries after actions. Cache only typed absence, never transient errors; an unobserved window is not confirmed zero events. Cache hits consume neither provider traffic count nor pacing delay. Use a conservative 0.3s minimum for uncached calls without increasing existing deadlines. Preserve default full-refresh callers and fake-provider contracts. Add deterministic date-window equivalence, empty/missing/malformed/cache-budget tests, then branch canary and full GitHub checks. R7 remains open and all work is sequential in the main instance.


R7 implementation/self-review complete locally; hosted verification pending. Added one actions-enabled history per listing's own required union window, preserving separate price/dividend/action filters and existing checkpoint logic. Full-refresh callers retain their prior path. Cached event columns/index/currency are deep copied under a 512 MiB cap and released after actions. Cache budget exhaustion opens the circuit; typed absence is cached, transient errors are not; unobserved windows remain unavailable, not zero. Default uncached pacing is 0.3s, cache hits have no provider-count/pacing cost. Existing 40-minute/55-minute bounds remain unchanged.

Checks: 277 passed / 8 smoke deselected in 7.16s; Ruff passed. Deterministic cases cover independent-window equivalence, cold/warm planning, dry-run purity, missing columns, zero versus unobserved windows, historical events with no recent prices, negative reuse, transient retry, memory budget, fallback windows and listing isolation. Live four-listing canary passed in 9.487s: five uncached calls including FX / eight cache hits / no retries/circuit, event payload peak 364,488 bytes and final zero. Twelve live model comparisons equal independent queries except creation timestamps. Evidence under `shared-history-live-*`.

Separate self-review checked that request grouping never widens a peer's window, financial values/source IDs/event currency/split classification are unchanged, price columns cannot be retained by pandas cache blocks, all cache misses still pass circuit/deadline/request budgets, and no full-refresh or engine contract changed. Next: publish the candidate, run a non-publishing branch canary, inspect artifact/call counts, then re-run the whole catalog on GitHub. R7 remains unchecked until that evidence succeeds; no merge or sprint-gate waiver is claimed.


R7 hosted canary PASS on exact candidate 75ffcf9:
https://github.com/ashcx/sg-investing-v1/actions/runs/39096967279
All stages passed, including the 277-test suite and artifact uploads. Downloaded
diagnostics verified against GitHub SHA-256 digest: five uncached calls,
eight cached responses, zero retries/circuit, event cache peak 364,488 bytes
and final zero; updater 29.558s / peak RSS 1,804.19 MiB. This is the QQQ/GRPN/
ES3.SI/40F.SI canary, not a full-catalog or scheduled-success claim. All six
standard CI checks also pass on 75ffcf9.

Full-catalog hosted verification is now active on that same exact candidate:
https://github.com/ashcx/sg-investing-v1/actions/runs/39097179279
Run id 39097179279, workflow_dispatch, 3,170 listings, no pack publication.
Poll this specific run/jobs until terminal; do not restart on an observation
timeout. Inspect diagnostics/validated artifacts and the exact cause if it
fails. No other live full run remains active. PR #5 remains draft; R7 stays
unchecked until full hosted proof is obtained. Merge approval and human-review
progression decisions remain pending/on hold; no later sprint has started.


### R7 complete — full GitHub workflow and uploaded-snapshot verification

Actual full-catalog GitHub run PASSED on exact runtime head 75ffcf9:
https://github.com/ashcx/sg-investing-v1/actions/runs/39097179279
This is workflow_dispatch, not a scheduled success. All 3,170 listings were
selected: 3,137 updated, 33 explicit unavailable-price warnings, zero failed
updates and zero FX errors. There were 34 unavailable dividend windows and 33
unavailable action windows; old observations and unknown coverage remain honest.
SO7.SI was unavailable on the hosted runner although it returned data locally;
no delisting or replacement values are inferred. Updater 1,621.891s (27m02s),
peak RSS 2,754.5 MiB; 3,176 uncached calls / 6,333 cached responses, no retries
or rate-limit circuit. Event cache peak 320,586,048 bytes, below its 536,870,912-
byte cap, and final zero. Hosted post-fetch suite: 277 passed / 8 deselected.

Both downloaded artifact ZIPs match GitHub SHA-256 digests. Applied the actual
uploaded archive to a fresh disposable canonical baseline; its resulting chain
hash exactly matches the producer: sha256-b1e58fd77ef1bb84e2de649fc480f155b29d9765e73e89fed8b6e4d6740bd452.
A separate scoped build on that exact uploaded snapshot passed in 160.452s:
3,167 touched listings, 77 coverage year-pack records checked across 39 changed
coverage states, and all 387 untouched packs byte-identical. Complete-baseline
and manifest/disk equality checks pass: 3,186 manifest securities / 55,548 packs /
13,525,534 price rows. WBD/ATAI remain absent. DCA 29/29 and portfolio 14/14 pass
against these rebuilt packs. An initial disposable setup assumed an optional
frontend/package.json existed; it does not, and copying only existing assets
completed setup. No product code or test assertions were changed for this check.

Evidence: `shared-history-github-full-{verification,application,scoped-packs,pack-consistency}.json`,
progress/resource trace, exact dependency inventory, job excerpt, and integration
reports under `docs/incremental-recovery-2026-10-18/`. Separate self-review confirms
manual hosted verification is not labeled cron evidence, the optional hosted
full-pack step was skipped as requested, and the subsequent local scoped build
is reported as a separate operation. Earlier failed runs stay retained.

R7 and the repair implementation task are complete. PR #5 can return to ready
for review, but no merge/publication approval or human acceptance is inferred.
Overall Sprint 7.5 remains In progress: reviewed merge, successive actual
scheduled successes, and remote Pages/R2 publication verification remain open.
No live update snapshot was applied to the source repository or published.
Sprints 12–15 remain Not started under their entry/review gates. Roadmap PR #6
is planning only and remains stacked on recovery; after PR #5 merges, retarget
#6 to main before considering its merge. Await the pending Product Owner
merge/deployment and between-sprint acceptance decisions before dependent work.
