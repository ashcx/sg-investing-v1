# Deployment — GitHub Pages

Sprint 7 (S7.1/S7.8) deployment guide for the static site. The frontend is a
no-build static app; static mode makes zero `/api` calls and computes entirely
in the browser from published data packs.

## Repository setup (one-time)

1. Create the GitHub repository and push the default branch `main` (the
   Pages trigger in `.github/workflows/deploy-tier1.yml` assumes `main`; the
   remote default branch is verified as `main` via `git ls-remote --symref
   origin HEAD`). Large canonical data under `data/` is Git LFS
   (`git lfs install` before the first push).
2. In **Settings → Pages → Build and deployment → Source**, select
   **GitHub Actions** (not "Deploy from a branch"). The deploy workflow
   declares `permissions: pages: write, id-token: write` and deploys through
   `actions/deploy-pages`, so no branch-based Pages configuration is needed.
3. Confirm the first successful run of "Deploy Tier-1 site to GitHub Pages"
   (push or manual `workflow_dispatch`); the deployed URL appears in the
   workflow's `environment: github-pages` and in Settings → Pages.

## Single deploy path — every push, dispatch, or weekly schedule

> **Changed 2026-09-01:** the repository previously had two deploy paths
> (`pages.yml` fast frontend-only deploys on push; `deploy-tier1.yml` with
> packs on dispatch). This conflicted in production: a plain push deploy
> replaced the Tier-1 deployment and wiped all data packs from the live site
> (whole-site deployment semantics — later deploy wins). `pages.yml` was
> removed; `deploy-tier1.yml` is now the **only** deployment workflow.

`.github/workflows/deploy-tier1.yml` triggers on every push to `main`, on
manual `workflow_dispatch`, and on a weekly schedule, and publishes the
complete interactive site:

1. Checkout with `lfs: true` (the committed, validated canonical snapshot).
2. `pip install ".[dev,market-data]"`, then the full Python suite gate
   (`pytest -m "not smoke"`).
3. `python scripts/build_data_packs.py` — builds all security-year packs.
4. `python scripts/prune_packs_for_pages.py` — prunes `frontend/data/packs/`
   to the **Tier-1** publication: every manifest security EXCEPT universe
   `russell2000_current` (~1.0 GB excluded), rewriting `manifest.json` to the
   pruned subset (snapshot identity, methodology, catalog fields preserved; a
   `tier` note records the excluded universes) and asserting
   manifest↔packs consistency in both directions.
5. Emits `frontend/build-info.json`
   (`{built_at, data_snapshot_id, workflow_run_id}`) and asserts it matches
   the manifest snapshot (`built_at` must not predate the manifest's
   `generated_at`); the site displays the build date next to the data
   snapshot chip. A plain pages.yml deploy has no such file and the app
   tolerates its 404.
6. Verifies the artifact budget: `prune_packs_for_pages.py --verify-only`
   re-asserts consistency and fails the release above **950 MB** (measured
   Tier-1 size: **~747 MB** = 735.1 MB packs + 8.5 MB manifest + ~3.7 MB
   frontend assets).
7. `actions/configure-pages` + `actions/upload-pages-artifact`
   (`retention-days: 1` to protect the 500 MB Actions storage quota) +
   `actions/deploy-pages`.

Triggers: `workflow_dispatch` (manual) and a weekly schedule
(Monday 03:30 UTC — mostly a pipeline re-verification; remove the `schedule`
block if unwanted). Both deploy paths share the `pages` concurrency group, so
a Tier-1 run and a push run never deploy simultaneously.

`frontend/data/packs/` is generated output only and is never committed
(`.gitignore`); the full 3,188-security universe (~1.77 GB) is published
exclusively as the `frontend-data-packs` workflow artifact from
`.github/workflows/data-packs.yml` (also 1-day retention). Tier-2 hosting for
the excluded Russell-2000 universe is the Sprint 8 decision
(`Todo/sprint-8-pack-origin.md`).

## CI

- `.github/workflows/static-checks.yml` (push + PR):
  `python scripts/check_static_site.py` — asset/script/href paths resolve
  (subpath-safe), pack manifest + `frontend/data` JSON parse, no
  root-absolute references that would break the Pages project subpath,
  fonts remain self-hosted.
- `.github/workflows/test.yml` runs the Python suite on push/PR; the Tier-1
  deploy re-runs it as a hard publish gate.

## Rollback

- **Pages redeploy of a known-good build:** in **Actions → Deploy frontend
  to GitHub Pages** (or "Deploy Tier-1 site"), use **Re-run all jobs** on the
  last good run, or `workflow_dispatch` the workflow on a previous commit via
  "Run workflow" → branch/tag. `actions/deploy-pages` replaces the current
  Pages deployment atomically; the last successful deployment stays live
  until a new one succeeds.
- **Frontend-only hotfix:** push a fix to `main`; the push-triggered
  pages.yml deploys in ~1 minute (without packs). Use this to pull a broken
  Tier-1 change back to the last-known frontend if needed.
- **Data-pack regression:** the pack build starts from the committed LFS
  snapshot, so rolling back the data store is `git revert` + re-run the
  Tier-1 workflow. A browser cache can hold at most a stale 24 h manifest
  entry (IndexedDB) and cached packs validated by `data_snapshot_id`; a
  republish with a corrected snapshot flushes caches lazily.
- Workflow files themselves: `git revert` the workflow commit; no Pages
  state to clean up (deployments only change on successful runs).

## Sprint 7 items that require a git push to fully verify

Prepared locally, pending push (no commits made by the Sprint 7 agent):

1. **pages.yml + deploy-tier1.yml behaviour in CI** (S7.1): the workflows'
   real execution — LFS checkout, `pytest -m "not smoke"` gate, pack build,
   prune, Pages artifact upload/deploy, artifact budget failure path — only
   runs on GitHub. Everything except the actual Actions run was verified
   locally (scripts run green; workflow YAML parses; prune run measured).
2. **static-checks.yml on a fresh GitHub checkout** (S7.2): the checker runs
   green locally on the real tree; the workflow's own run (plain checkout,
   packs absent) needs one push.
3. **`retention-days: 1` on data-packs.yml + upload-pages-artifact** (S7.1):
   visible only as live artifact expiry in the Actions UI after a run.
4. **Pages enablement + deployed URL confirmation** (S7.8): Settings →
   Pages → Source "GitHub Actions" and the final URL check require the
   repository to exist with the pushed workflows.
5. **Schedule trigger** for deploy-tier1 (weekly) fires only once pushed.
6. **Build-info end-to-end in production** (S7.4): verified locally against
   a deploy-shaped artifact (build-info.json + pruned packs + rewritten
   manifest); the production `frontend/build-info.json` appears only after
   the first Tier-1 run on GitHub.
