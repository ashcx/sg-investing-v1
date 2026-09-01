# Sprint 7 — release hardening implementation notes

Status: implemented 2026-09-01. Covers the Sprint 7 tasks (S7.1–S7.8) with
the coordinator-approved tiering. The sprint file's checkboxes are left for
the coordinator to tick (Todo/** out of scope for this task). All Sprint 0–6
exit criteria were verified in the sprint files before starting.

Files changed/created:

| File | Change |
| --- | --- |
| `frontend/app.js` | S7.1: `s5PackLoader` now gets `baseUrl: new URL('.', document.baseURI)` (fixes the S5 subpath bug from docs/sprint-6-notes.md). S7.4: `loadBuildInfo()` + `renderBuildInfo()` — fetches `build-info.json` (404-tolerant), shows the build date next to `#data-date` with the full build/snapshot/run in the tooltip. |
| `frontend/styles.css` | S7.6: Google Fonts `@import` replaced by 10 self-hosted `@font-face` rules (identical family names/weights; latin subset WOFF2 under `frontend/fonts/`; DM Sans + Space Grotesk are variable files served per weight). |
| `frontend/fonts/*.woff2` | New: `dm-mono-latin-400/500`, `dm-sans-latin-400`, `space-grotesk-latin-400` (fetched 2026-09-01 from fonts.gstatic.com, sha256 recorded in the fetch log). |
| `frontend/index.html` | S7.6 only: CSP meta `default-src 'self'; script-src 'self'; worker-src 'self'; connect-src 'self'; font-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'`. |
| `scripts/prune_packs_for_pages.py` | New (S7.1): prunes the pack tree to the published tier (default: all manifest securities EXCEPT `russell2000_current`), rewrites the manifest (recomputed `summary`/`support.counts`, added `tier` note + honest snapshot warning, snapshot/catalog/methodology fields preserved), asserts manifest↔packs consistency in both directions, prints published bytes, `--verify-only --max-total-bytes` is the deploy budget gate. |
| `scripts/check_static_site.py` | New (S7.2): static-site integrity checks (see below). |
| `.github/workflows/deploy-tier1.yml` | New (S7.1): workflow_dispatch + weekly schedule; LFS checkout → pip install `.[dev,market-data]` → `pytest -m "not smoke"` gate → pack build → prune → build-info emission + manifest consistency assertion → 950 MB budget verify → configure/upload (retention-days: 1)/deploy Pages. |
| `.github/workflows/static-checks.yml` | New (S7.2): push/PR, plain checkout, stdlib-only run of the checker. |
| `.github/workflows/data-packs.yml` | `retention-days: 1` on the 1.7 GB `frontend-data-packs` artifact (was eating the 500 MB Actions storage quota). |
| `docs/deployment.md` | New (S7.8): repository/Pages setup, both deploy paths, rollback notes, list of Sprint 7 items needing a push. |
| `docs/sprint-7-notes.md` | This file. |

Untouched by design: `pages.yml` (push path unchanged, trigger branch `main`
verified against the remote default branch via `git ls-remote --symref
origin HEAD`), engine modules, fixtures, tests, Todo/**.

## S7.1 — Tier-1 pruning

Measured against the committed snapshot build (`sha256-2612cdfa…`):

- Excluded universe `russell2000_current`: 1,946 securities, 31,537 packs,
  1,039.1 MB — no security in it belongs to any other universe, so the cut
  is clean.
- Published tier: 1,242 securities, 24,037 packs, 735.1 MB; pruned manifest
  8.5 MB; plus ~3.7 MB of committed frontend assets ≈ **747 MB Pages
  artifact** (budget gate: 950 MB; GitHub Pages guidance: 1 GB).
- The rewritten manifest keeps `data_snapshot_id` / `catalog_version` /
  `catalog_as_of` / `methodology_version` / `generated_at` byte-identical in
  value, recomputes `summary` (securities, pack_count, total_bytes,
  price_rows, pack_bytes min/median/max) and `support.counts`, adds
  `tier: {published: "tier1", excluded_universes, excluded_securities,
  excluded_pack_bytes, note}` and appends a snapshot warning naming the
  excluded universes so the manifest stays honest about what is NOT hosted.
- Consistency assertion is two-way: every manifest-referenced pack exists on
  disk AND every `security=*/year=*.json` on disk is referenced by the
  manifest (no orphans after pruning).
- Browser impact: the app answers support questions from the published
  manifest, so Russell-2000 securities show explicit `unavailable` states
  instead of failing pack fetches (S6.4 behaviour, unchanged).

## S7.2 — static-site checks

`scripts/check_static_site.py` validates over `frontend/`: (a) every
src/href in index.html and every path-like literal in app.js resolves to an
existing file via subpath-safe relative logic (root-absolute asset paths are
rejected; `${...}` template paths are glob-checked, e.g.
`data/series/*/*_*.json`); (b) the pack manifest parses and every referenced
pack exists (skipped on plain checkouts, where `frontend/data/packs/` is
absent); (c) every `frontend/data/**/*.json` outside `packs/` parses;
(d) no root-absolute asset references anywhere (index.html, app.js,
engine modules, styles.css url()), and styles.css keeps fonts self-hosted
(no external `@import`/url). Documented exceptions: `build-info.json`
(deploy-time generated, app tolerates 404) and `sg-invest-*.json`
(`link.download` names, not fetch paths). Literals containing `API_BASE`
are adapter-mode URLs on a separate origin, never site paths.

## S7.4 — build identifier

`deploy-tier1.yml` writes `frontend/build-info.json`
(`{built_at, data_snapshot_id, workflow_run_id}`) from the built manifest
and re-asserts equality plus `built_at >= manifest.generated_at` in a
separate step (fails the release on mismatch). `app.js` fetches it once at
init (same-origin, CSP-clean), tolerates 404 (plain pages.yml deploys) and
renders `· Build <date>` beside the existing `#data-date` chip, with
`Site build … · data snapshot … · workflow run …` as the tooltip. Verified
in-browser against a deploy-shaped tree (chip renders, `#data-date`
fallback intact, zero console errors).

## S7.5 — pins and credential scan

All six workflows pin every third-party action to full major tags, no
floating refs, no major upgrades: `actions/checkout@v4`,
`actions/setup-python@v5`, `actions/upload-artifact@v4`,
`actions/configure-pages@v5`, `actions/upload-pages-artifact@v3`,
`actions/deploy-pages@v4`. Credential scan: no `secrets.*` usage, no tokens
or private keys anywhere; the only privileged permissions are
`pages: write` + `id-token: write` (required by deploy-pages). Pages
artifact contents = `frontend/` only: app assets + pack JSON (public
yahoo_finance-derived prices/dividends/FX with provenance fields); the
upload action excludes `.git`/`.github`. No credentials or private data in
any artifact.

## S7.6 — CSP and self-hosted fonts

Fonts: latin subsets vendored to `frontend/fonts/` (4 unique WOFF2 files,
~89 KB total) with per-weight `@font-face` rules whose family names are
identical to the retired `@import`. Browser-verified:
`document.fonts.check` true for DM Sans / DM Mono 400+500 / Space Grotesk
600, zero requests to fonts.googleapis.com/gstatic.com.

CSP: the coordinator-specified policy is applied as a meta tag. Verified in
Chrome: module worker still spawns (`worker-src 'self'`; engine worker is a
same-origin module worker), fonts load, zero CSP violations, zero console
errors across init + all submits at both widths. Notes:

- `style-src 'unsafe-inline'` is required by the toggle/switch UI styling
  approach (inline `style` attribute usage) and is part of the approved
  policy; everything else is 'self'.
- Adapter mode (development/reference only, meta `sg-invest-api-base` set)
  would need the adapter origin added to `connect-src` in a dev override;
  the static deployment makes no cross-origin calls by construction (S6.2).

## S7.7 — Chrome QA (Playwright, headless Chromium 1440×900 and 390×844)

Desktop: catalog render + filters intact; first paint labelled
`Demo replay · published artifact`; local analysis computes via packs +
worker (QQQ 2024 = S$13,157.34 / +31.57%, matching the committed artifact
envelope); currency switching native ↔ SGD flips values and back;
compare (QQQ, SMH) renders 2 rows; DCA monthly 2024 renders 13 contributions
+ XIRR; portfolio reconstruction renders the QQQ holding with local-source
note; warnings panel renders 9 items with working collapse; mode indicator
transitions verified; engine worker visible via `page.workers()`; **zero
`/api` requests, zero console errors, zero 4xx/5xx** (the only tolerated
item is the by-design `build-info.json` 404 on plain deploys).

Mobile 390px: analysis, DCA and portfolio all compute; document-level
scrollWidth = 390 (no page-level horizontal scroll; `.site-shell` clips).
Section-level overflow found and **reported, not redesigned**:

1. `header` — `.header-meta` chips (`white-space: nowrap`: "Data snapshot"
   + the S6 mode indicator, up to ~285px combined) overflow the 354px
   content box next to the brand (measured 423–528px scroll width
   depending on indicator label). Suggested fix (Sprint 8): allow the meta
   chips to wrap or hide the mode label text on ≤650px.
2. `#portfolio` — ledger table: `.ledger-table-wrap` has
   `overflow-x: auto`, but the grid item (`form.portfolio-form`,
   `min-width: auto`) grows to the 6-column table's min-content (~656px),
   so the wrap never scrolls and the section overflows to 756px with a
   populated ledger. Suggested fix (Sprint 8): `min-width: 0` on the
   layout grid items (portfolio/dca forms).
3. `#home` — `.hero-aside` 4px overflow (rotated `.signal-card`
   `transform: rotate(2deg)`); cosmetic clipping only.

Offline: Playwright disables the HTTP cache by default; the QA harness
re-enables it via CDP (`Network.setCacheDisabled(false)`) because that is
what real browsers do (GitHub Pages serves `Cache-Control: max-age=600`).
With the cache enabled: analysis + DCA prime it; a warm-cache **reload**
re-initialises the site; with the HTTP server **stopped**, a second analysis
(QQQ, S$30,000) recomputes and renders from the cached manifest + packs
(S$39,472.03 = deterministic recompute, distinct from the warm-cache run).
Zero console errors throughout.

A full page reload with the network fully down (no server, no cache) would
require a service worker — out of Sprint 7 scope; the Pages-production
equivalent (warm cache + stopped network) is what is verified above.

## Known tradeoffs / Sprint 8 candidates

1. **Manifest IndexedDB cache never engages in the app.** `ledger-store.js`
   creates `sg-invest-cache` at v2 with only the `ledger` store (init runs
   before any compute), and `pack-loader.js` deliberately opens without a
   version and skips caching when `meta` is absent — so the meta store is
   never created and the manifest is fetched once per session (in-memory)
   and from the HTTP cache after reloads. This is the S6-documented
   degradation; making the cache live needs a coordinated store/version
   change (frozen-layer edit in `pack-loader.js`/`ledger-store.js`).
2. **Offline-first reload** (service worker for full offline reloads) —
   beyond Sprint 7 scope.
3. **Mobile overflow fixes** as listed in S7.7 (three small CSS changes).
4. **Adapter-mode CSP override** for development (`connect-src` adapter
   origin) — static deploys are unaffected.
5. **`index.html` has no favicon** — browsers may log a favicon 404 in some
   environments (not observed in headless QA); adding one means an
   index.html change beyond the S7 CSP-only constraint.
6. `data-packs.yml`'s workflow_run trigger ("Update market data") chains
   into the pack build+prune only when run manually; the Tier-1 deploy is
   intentionally a separate, explicit workflow.

## Verification summary (S7.3)

- `node --check` app.js / ledger-store.js / engine-client.js /
  pack-loader.js / protocol.js / worker.js: OK
- `node frontend/engine/selftest.mjs`: 68/68
- `node frontend/engine/parity/parity.mjs`: 27/27
- `node frontend/engine/property/property.mjs`: PASS (19 properties,
  1,473 cases)
- `node frontend/engine/worker-selftest.mjs`: 86/86
- `node frontend/engine/dca-packs-integration.mjs`: 28/28
- `node frontend/engine/portfolio-packs-integration.mjs`: 14/14
- `.venv/bin/python -m pytest`: 172 passed, 8 skipped
- `.venv/bin/ruff check src scripts`: 30 findings, all pre-existing
  (baseline unchanged; the two new scripts are clean)
- `.venv/bin/python scripts/check_static_site.py`: OK (55,574 referenced
  packs verified against the full local manifest)
- Browser: qa-main (desktop 1440 + mobile 390 + offline) 43/44 checks pass,
  the single failure being the reported mobile-overflow finding; qa-subpath
  (project subpath + build-info display) 15/15. Zero console errors, zero
  `/api` calls, no CSP violations anywhere.
- Local Tier-1 prune run: 747 MB artifact (735.1 MB packs + 8.5 MB
  manifest + 3.7 MB frontend), consistency green, budget green.
