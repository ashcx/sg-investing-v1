# Sprint 7 — Release hardening & GitHub Pages launch

## Goal

Ship a hardened, verifiable GitHub Pages deployment.

## Entry criteria

- [ ] Sprint 4 exit criteria are all met: DCA computes fully in-browser.
- [ ] Sprint 5 exit criteria are all met: portfolio reconstruction computes
      fully in-browser.
- [ ] Sprint 6 exit criteria are all met: single honest computation mode, no
      silent fallbacks.

## Depends on

Sprints 4, 5, 6.

## Tasks

- [ ] Keep `.github/workflows/pages.yml` as the deployment path and verify it on
      the repository's actual default branch (the current workflow assumes
      `main`).
- [ ] Add CI checks for static asset paths under a repository project subpath,
      missing data packs, malformed JSON and broken internal links.
- [ ] Run the full Python suite, browser-engine parity suite and static-site
      smoke tests before publishing.
- [ ] Add a generated build identifier and visible snapshot date to the site;
      fail the build if required artifacts are stale or inconsistent.
- [ ] Pin third-party action/library versions and confirm no credentials or
      private market data are included in the Pages artifact.
- [ ] Set a Content Security Policy and review external requests, downloads and
      client-side storage behavior.
- [ ] Repeat Chrome QA at desktop and mobile widths for catalog, analysis,
      currency switching, DCA, portfolio, comparison, warnings and offline
      reload behavior.
- [ ] Document repository setup: create the Git repository, push the default
      branch, enable Pages with GitHub Actions, and confirm the deployed URL.

## Exit criteria

- [ ] CI gates pass: Python suite, parity suite, static-site smoke tests.
- [ ] Build fails on stale/inconsistent artifacts; paths work under a project
      subpath.
- [ ] Desktop + mobile Chrome QA passed for all listed surfaces.
- [ ] Pages enabled and deployed URL confirmed.
