# Sprint 1 — Static data-pack publishing

## Goal

Generate versioned, partitioned, lazy-loadable browser data packs for every
supported security, with manifests, budgets and a publishing workflow.

## Entry criteria

- [x] Sprint 0 exit criteria are all met: static/no-API target confirmed,
      calculation architecture recorded, specs updated.

## Depends on

Sprint 0 (architecture decision).

## Tasks

- [x] Define versioned browser data-pack schemas for daily native prices, FX,
      dividend events, security metadata, coverage and provenance.
- [x] Generate packs for every supported security, not only the current
      representative QQQ analysis/DCA/comparison/portfolio/series artifacts.
- [x] Publish packs in security/year partitions so the browser loads only the
      securities and date ranges a user requests.
- [x] Include `data_snapshot_id`, catalog version, methodology version, source,
      coverage dates and data-quality warnings in every pack/manifest.
- [x] Add a manifest that tells the client whether a security/date range is
      fully supported, incomplete or unavailable before calculation begins.
- [x] Update the data-refresh workflow to build and publish the frontend data
      artifact after a validated snapshot. Do not require committing canonical
      Parquet files to the public repository.
- [x] Add payload-size, cache and load-time budgets. Use lazy loading and
      IndexedDB/browser caching for previously loaded packs.
- [x] Decide whether external fonts/assets should be self-hosted so the site
      remains deterministic when third-party requests are unavailable.

## Exit criteria

- [ ] A workflow run produces packs for all supported securities from a
      validated snapshot without committing canonical Parquet to the repo.

> **Blocker (2026-08-31):** workflow `.github/workflows/data-packs.yml` is
> authored and YAML-validated; the equivalent build was executed locally for
> real (55,574 packs, 3,188 manifest entries, 1.79 GB). The CI run itself
> cannot be verified without pushing to GitHub — tick this after the first
> successful Actions run.
- [x] A client can ask "is security X / date range Y supported?" from the
      manifest before any calculation runs.
- [x] Pack sizes and load behavior meet the recorded budgets.

## Out of scope

- Browser-side calculation (Sprint 2+).
- DCA/portfolio feature work (Sprints 4–5).
