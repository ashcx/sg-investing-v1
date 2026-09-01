# Sprint 7 — Release hardening & GitHub Pages launch

## Goal

Ship a hardened, verifiable GitHub Pages deployment.

## Entry criteria

- [x] Sprint 4 exit criteria are all met: DCA computes fully in-browser.
- [x] Sprint 5 exit criteria are all met: portfolio reconstruction computes
      fully in-browser.
- [x] Sprint 6 exit criteria are all met: single honest computation mode, no
      silent fallbacks.

## Depends on

Sprints 4, 5, 6.

## Tasks

- [x] Keep `.github/workflows/pages.yml` as the deployment path and verify it on
      the repository's actual default branch (the current workflow assumes
      `main`).
- [x] Add CI checks for static asset paths under a repository project subpath,
      missing data packs, malformed JSON and broken internal links.
- [x] Run the full Python suite, browser-engine parity suite and static-site
      smoke tests before publishing.
- [x] Add a generated build identifier and visible snapshot date to the site;
      fail the build if required artifacts are stale or inconsistent.
- [x] Pin third-party action/library versions and confirm no credentials or
      private market data are included in the Pages artifact.
- [x] Set a Content Security Policy and review external requests, downloads and
      client-side storage behavior.
- [x] Repeat Chrome QA at desktop and mobile widths for catalog, analysis,
      currency switching, DCA, portfolio, comparison, warnings and offline
      reload behavior.
- [x] Document repository setup: create the Git repository, push the default
      branch, enable Pages with GitHub Actions, and confirm the deployed URL.

## Exit criteria

- [x] CI gates pass: Python suite, parity suite, static-site smoke tests.

> **Resolved (2026-09-01):** pushed as dbdc3b6..; static-checks green on push,
> backend tests green, deploy-tier1 built + pruned + deployed successfully.
> Live verification on https://ashcx.github.io/sg-investing-v1/: DCA renders
> the exact Python golden (S$13,777.06 · 12 contributions · XIRR +28.53%) in
> LOCAL COMPUTE mode with zero /api calls and zero console errors.
>
> **Follow-up fix (same day):** the two deploy paths conflicted in production —
> a push-triggered plain `pages.yml` deploy (frontend only, no packs) superseded
> the Tier-1 deployment and wiped all packs from the live site (manifest 404).
> Consolidated to a single deployment workflow: `pages.yml` removed and
> `deploy-tier1.yml` now triggers on push + dispatch + schedule, always
> deploying frontend + packs behind the pytest gate. See docs/deployment.md.
> locally — both new workflows (`static-checks.yml`, `deploy-tier1.yml`) are
> authored, the full battery is green, subpath + CSP + mobile QA pass in real
> Chromium. Items 1 and 4 need a git push so the Actions runs can execute
- [x] Build fails on stale/inconsistent artifacts; paths work under a project
      subpath.
- [x] Desktop + mobile Chrome QA passed for all listed surfaces.
- [x] Pages enabled and deployed URL confirmed.
