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
- [ ] Repair bounded fetching, memory usage, provider retry behavior, workflow
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
