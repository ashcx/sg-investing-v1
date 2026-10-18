# Data updates runbook

Operator procedures for keeping the canonical store (`data/`, LFS-tracked)
and the browser packs (`frontend/data/packs/`, gitignored, built) current.
The update contract itself is documented in `docs/incremental-updates.md`.

Commands that build scoped packs require a complete pack baseline from the
same reviewed canonical checkout. In a clean checkout, use `--no-build-packs`
and build the full set after validation; see the recovery contract below.

Three update paths exist:

| Path | Command | Duration | Use |
| --- | --- | --- | --- |
| Daily incremental | `scripts/update_incremental.py --since auto` | minutes | Scheduled (CI) and routine manual refresh. |
| Reconciliation sweep | `scripts/update_incremental.py --since <date>` | minutes | Weekly, or after suspected provider restatements. |
| Manual full rebuild | `scripts/refresh_universe.py` → `scripts/update_data.py` → `scripts/build_data_packs.py` | hours (~6 h for the full catalog) | Quarterly deep reconciliation, catalog refreshes, after methodology/pipeline changes. |

## Daily incremental update

After the US close (the scheduled workflow runs `0 22 * * 1-5` UTC):

```bash
python scripts/update_incremental.py --since auto
```

- per security, refetches the last stored price date minus the 45-day
  reconciliation window, sweeps dividends/actions over the same tail, and
  refreshes FX tails for every required pair;
- writes the store through the atomic storage upserts, then rebuilds ONLY
  the touched security/year packs and merges the pack manifest.

Useful flags:

| Flag | Meaning |
| --- | --- |
| `--securities QQQ,6cfd001d-…` | Comma-separated tickers or security_ids; default: whole catalog. |
| `--since YYYY-MM-DD` | Backfill a gap: widens every fetch window back to the date (FX pairs with no history still fetch from the catalog floor). |
| `--dry-run` | Print windows/endpoints/rebuild command; no network, no writes. |
| `--no-build-packs` | Update the store only; rebuild packs later. |
| `--skip-actions` | Skip corporate-action reconciliation (explicitly omits action reconciliation; normally leave it enabled). |
| `--reconciliation-days N` | Override the default 45-day trailing window. |

Preview before you commit to a run:

```bash
python scripts/update_incremental.py --since auto --securities QQQ --dry-run
```

## Weekly reconciliation sweep

Once a week (e.g. Friday after the daily update), widen the windows so
restatements older than the daily tail are caught:

```bash
python scripts/update_incremental.py --since "$(date -d '-10 days' +%F)"
```

- dividend sweeps reach back to `queried_through − max(45d, since span)`;
- gap backfill (`--since`) also fills missing mid-range price/FX dates; new
  FX rates that land inside existing price coverage invalidate the affected
  packs automatically;
- leave corporate actions ON. `--skip-actions` is an explicit diagnostic-only
  omission; such a run is incomplete and cannot produce a publication artifact.

## Manual full rebuild

The incremental path never re-derives history; on a cadence of your choice
(recommended: quarterly), reconcile from scratch:

```bash
python scripts/refresh_universe.py          # catalog refresh
python scripts/update_data.py               # full-catalog refresh (~6 h)
python scripts/build_data_packs.py          # full pack rebuild (resets frontend/data/packs)
python -m pytest -m "not smoke"             # battery before publishing
```

A full rebuild replaces the pack manifest wholesale (no `incremental`
block), which also cleans up any accumulated scoped-merge state.

## Scheduled CI run and applying CI artifacts

`.github/workflows/update-incremental.yml` runs the daily incremental update
(schedule `0 22 * * 1-5` plus manual dispatch) and uploads an artifact
`incremental-update-<run_id>` (retention 1 day) containing:

- `incremental-store-changes.tgz` — every changed canonical store file
  (computed via `git status` over the LFS-tracked `data/` tree);
- `changed-store-files.txt` — the file list, for review;
- `frontend/data/packs/` — the rebuilt packs with merged manifest.

CI never commits. Applying a run is an operator step:

```bash
# 1. Download the artifact from the workflow run and unpack it.
unzip incremental-update-<run_id>.zip -d update-artifact && cd update-artifact

# 2. Review what changed.
cat changed-store-files.txt
python -c "import json; s = json.load(open('frontend/data/packs/manifest.json')); \
  print(s['data_snapshot_id'], s['incremental'])"   # packs artifact only

# 3. Apply over a clean checkout (LFS-smudged working tree).
tar xzf incremental-store-changes.tgz -C /path/to/checkout
cp -r frontend/data/packs/. /path/to/checkout/frontend/data/packs/

# 4. Verify locally, then commit the store changes (LFS tracks data/**).
cd /path/to/checkout
python -m pytest -m "not smoke"
git status -- data                      # should match changed-store-files.txt
git add data && git commit -m "Incremental data update <run_id>"
git push
```

Pushing updated store files triggers the normal pack/deploy pipeline
(`data-packs.yml`); the packs in the artifact can be used immediately for a
Pages deployment if you do not want to wait for a rebuild. Committing from
CI itself is deliberately out of scope: an operator reviews the change set
(`git status`/`git diff --stat`) before it lands, and `update_incremental.py
--commit` is documented only as a future option, not implemented.

## Reading `data/update_summary.json`

Every update writes `data/update_summary.json`. For incremental runs the
key health signals are:

- `failed` / per-security `results[].error` — provider failures; failed
  securities keep their previous store contents (atomic upserts), and the
  next run's window still covers them;
- `fx_fetch_errors`, `corporate_action_errors` — per-pair/per-security
  provider errors recorded without aborting the run;
- `store_content_hash_unchanged` — true when nothing changed;
- `incremental_snapshot_id` — head of the incremental chain; equal to the
  previous run's id when no data changed;
- `change_set.truncated` — set when the run hit the 10,000-key cap (a sign
  the incremental tool was used for something full-rebuild-shaped);
- `packs.merge.replaced_packs` / `updated_entries` — what the scoped pack
  rebuild replaced.

If `failed` or the error maps stay non-empty across runs, or a gap persists
that `--since` does not close, fall back to the manual full rebuild.


## Recovery workflow and artifact contract — 18 October 2026

This section supersedes earlier assumptions that a fresh CI checkout already
has a full pack baseline or that an update success means automatic publication.

- One daily incremental schedule remains: 22:00 UTC weekdays, 06:00 Singapore
  Tuesday–Saturday, buffered after the US close in both DST seasons. Full
  reconciliation is manual. Both workflows share a non-cancelling concurrency
  group. Incremental jobs have a 55-minute cap; full jobs have 330 minutes.
- The incremental workflow runs without packs by default. Manual dispatch may
  select comma-separated tickers for a canary and request a **full** pack build
  after the canonical update. No partial manifest is uploaded as a full set.
- On a complete update plus passing normal Python suite, the review artifact
  contains changed canonical files (including untracked checkpoints), their list
  and summary; complete packs are included only if explicitly built. Canonical-
  only artifacts retain seven days; large full-pack artifacts retain one day to
  limit Actions storage use. No update auto-commits or deploys.
- A separate diagnostics artifact is always attempted, including stage/RSS
  checkpoints, stdout/stderr, process resource output and dependency versions.
  An incomplete run must not create a validated-update artifact. Inspect its
  diagnostics and rerun after correcting the cause; do not apply partial files
  just because they are present in a failed runner workspace.
- Review/apply canonical changes in a clean checkout first. If no full pack set
  is included, run `python scripts/build_data_packs.py` after applying them.
  Never copy a selected/filtered manifest over a complete publication. Run the
  normal suite and pack integrations before committing the canonical update.
- Tested updater dependencies are constrained by `config/update-constraints.txt`;
  workflows also retain the exact dependency inventory for each run.

A canary, one manual green run, and synthetic tests are not proof of restored
daily operations. Retain a full-universe run's resource evidence, confirm
artifact application/publication independently, and require successive actual
scheduled successes before checking the Sprint 7.5 operational exit.
