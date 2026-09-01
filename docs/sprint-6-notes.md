# Sprint 6 — fallback cleanup implementation notes

Status: implemented 2026-09-01 (S6.1–S6.5 plus the coordinator-approved
frozen-layer reconciliation). Covers `Todo/sprint-6-fallback-cleanup.md`.
The sprint file itself was NOT edited (out-of-scope per this task's hard
constraints), so its checkboxes are left for the coordinator to tick.

Files changed:

| File | Change |
| --- | --- |
| `frontend/app.js` | Local analysis/compare paths, mode indicator, fallback removal, run guards |
| `frontend/engine/protocol.js` | Additive: `createRequestTracker().nextId(scope, payload)` |
| `frontend/engine/pack-loader.js` | Additive: optional IndexedDB manifest cache (`meta` store) |
| `frontend/engine/worker-selftest.mjs` | Additive: 9 nextId checks (77 → 86, all green) |
| `docs/sprint-6-notes.md` | This file |

## S6.2 — zero runtime `/api` traffic when the API base is empty

- `apiGet()` now hard-throws when `API_BASE` is empty, so a static
  deployment can never emit a runtime `/api` request even if a future call
  site forgets the `if (API_BASE)` gate. The relative-path fetch
  (`fetch('api…')`) is gone entirely.
- `init()` resolves catalog, status and the first-paint series from the
  published static artifacts (`data/catalog.json`,
  `data/data-status.json`, `data/series/<id>/<start>_<end>.json`); the
  `/api/catalog`, `/api/status` and `/api/series` probes run only in
  adapter mode.
- `submitAnalysis` computes through the local engine:
  `packs.findSecurity` → `packs.supportFor` (same gate as S4/S5) →
  `packs.loadSecurityInputs` → `engineClient.analyze` (scope `analyze`,
  all financial values as strings, scenario booleans mapped to
  `dividends_enabled` / `withholding_tax_enabled` / `reinvest_dividends`).
  The result is wrapped in the adapter envelope shape
  (`data_snapshot_id` from the packs, `catalog_version` from the manifest,
  `methodology_version`, `request`) so `renderResult`, `analysisLink`,
  download and compare rendering work unchanged.
- Series: `s6SeriesFromInputs` mirrors `scripts/frontend_server.py`
  `/series` semantics from the packs already loaded for the analysis —
  window-filtered daily closes sorted by date, `native_close` plus
  same-day `sgd_close` using the previous-trading-day FX rule
  (`rateForDate`, parity of Python `_rate_for_date`), Decimal arithmetic
  via the vendored library. Presentation-only: a failure to build the
  chart yields `null` (chart hidden) and never blocks the result.
- `submitCompare` resolves each ticker against the manifest with the
  adapter's semantics (exactly one security per ticker or an explicit
  error), then runs per-ticker local analyses and hands
  `{ results: [envelope…] }` to the existing `renderCompare`.
- `submitPortfolio` in static mode goes straight to `s5LocalPortfolio`;
  the relative POST probe to `api/portfolio` (which produced the 404/501
  noise) is removed. Adapter mode still POSTs `${API_BASE}/api/portfolio`
  first and falls back to the local engine.

Adapter mode (meta tag set) keeps adapter-first with local fallback for
analysis, DCA, portfolio and compare; the adapter is now the
development/reference mode only. Verified in the browser against
`scripts/frontend_server.py`: init probes `/api/catalog`, `/api/status`,
`/api/series`; analysis renders with `Adapter · <origin>`; after an
injected adapter outage the local engine takes over and the indicator
switches to `Local compute (adapter unavailable)`.

## S6.3 — no silent demo-artifact substitution

Removed on failure: `submitAnalysis`'s exact-QQQ-demo replay fallback, the
`submitCompare` → `state.compareArtifact` fallback, and the relative
portfolio probe's "render whatever local can salvage" ambiguity (errors
now always surface in `#portfolio-error`). The init-time committed replay
(data/analyses/qqq-2024.json + its series artifact) still provides the
first paint, but it is explicitly labelled in the mode indicator
(`Demo replay · published artifact`) and in the result footer
(`Published demo replay · methodology …`), and is never reachable from a
failed request. The dead init preloads (`data/dca/qqq-2024-monthly.json`,
`data/comparisons/qqq-smh-soxx-2024.json`, `data/portfolios/demo-qqq.json`)
were removed; those artifacts are no longer fetched at all.

## S6.1 — mode display

`#mode-indicator`, a `security-tag` chip appended by JS into the existing
`.header-meta` (no index.html/styles.css edits), always shows the producer
of the most recent visible result:

- `Local compute` — API base empty;
- `Adapter · <origin>` — API base set;
- `Local compute (adapter unavailable)` — adapter attempted and failed;
- `Demo replay · published artifact` — the init-time committed replay is
  on screen (this fourth state is how S6.3's "demo replay must be clearly
  part of the mode display" is satisfied).

Per-request provenance is reinforced at the result itself: the analysis
footer reads `Computed locally in your browser` / `Adapter result` /
`Published demo replay`, and the chart source reads
`Series computed from local data packs` in local mode. DCA and portfolio
panels keep their S4/S5 local-source notes; the indicator updates on every
completed compute (analysis, compare, DCA, portfolio).

## S6.4 — unavailable states and request isolation

- Every local compute path gates on `packs.supportFor` first:
  `unavailable` (unknown security, ticker with zero/multiple manifest
  matches, or range outside covered years) renders an explicit message
  naming the security and the requested range — analysis/compare via the
  `#artifact-unavailable` panel + `#form-error` / `#compare-error`,
  portfolio via the S5 unavailable card, DCA via `#dca-error` (S4
  behaviour unchanged). `incomplete` computes and surfaces the coverage
  reason plus pack warnings (analysis merges them into the rendered
  `data_quality.warnings` copy and forces the `WARNING` badge; DCA keeps
  the S4 inline notice).
- Run isolation: each submit bumps a per-panel run sequence
  (`s6Runs.analysis/compare/portfolio`, same pattern as S4's DCA
  `runSeq`). A late/stale/superseded response can only ever be observed by
  the submit closure that started it, and only renders if its sequence is
  still current — a result from a different request can never replace the
  visible one. The engine worker independently verifies
  `id === requestKey(scope, payload)` and the tracker reports stale
  envelopes, so the layers are: worker id check → tracker stale guard →
  panel run sequence.

## S6.5 — native/SGD switching

`displayValues` and `renderDca` map the result contract's parallel
`*_foreign_currency` / `*_sgd` fields in both modes; the local engine
envelope carries exactly those fields (Decimal-string parity with the
Python `model_dump(mode="json")` shape), so switching remains
presentation-only. Browser-verified for locally computed analysis
(USD 9,635.83 / +27.13% ↔ S$13,157.34 / +31.57%, matching the committed
artifact envelope) and locally computed DCA (XIRR +24.36% native ↔
+28.53% SGD). No gap found; the only fix needed was the series producer
label noted above.

## Frozen-layer reconciliation (coordinator-approved)

- `protocol.js` `createRequestTracker` gained `nextId(scope, payload)` —
  implemented via the frozen `requestKey` from `./request-keys.js` — which
  mints the deterministic id and `track()`s it in one step. Purely
  additive: all existing exports and tracker behaviour are unchanged.
- `app.js` no longer injects the S4/S5 tracker bridges
  (`s4Tracker` / `s5CompatibleTracker` are removed); both engine clients
  use their own default tracker from `createEngineClient()`.
- `worker-selftest.mjs` gained an additive section
  ("S6: native tracker nextId") with 9 checks: key identity with
  `requestKey`, pending tracking, delivery through the stale guard,
  id dedupe for identical payloads, different payload/scope namespaces,
  and `supersedeScope` interplay. 77 pre-existing checks stay green
  (86/86 total).
- `pack-loader.js` gained optional IndexedDB caching of the manifest per
  `docs/data-pack-budgets.md`: database `sg-invest-cache`, out-of-line key
  `"manifest"` in the `meta` store (the `packs` store is created alongside
  when this module first creates the database, per the documented v1
  schema; pack fetches themselves are unchanged and remain validated
  against the loaded manifest's `data_snapshot_id`). Design decisions:
  - Strictly best-effort — any IndexedDB problem (unavailable, blocked,
    quota, missing `meta` store because the ledger store created the
    database first) silently degrades to a plain fetch.
  - This module never bumps the shared database version (the ledger store
    owns version 2 migrations), so it opens without an explicit version
    and skips caching when `meta` does not exist.
  - Freshness: a cached manifest is trusted for 24 h
    (`DEFAULT_MANIFEST_CACHE_TTL_MS`, overridable via
    `options.ttlMs` / `options.manifestCache` for tests). The tradeoff
    (a data update can take up to 24 h to be seen on a warm cache) is
    bounded and honest: every computed result still carries its
    `data_snapshot_id` provenance, and a stale manifest only delays new
    coverage — it cannot mix snapshots, because packs are validated
    against the loaded manifest exactly as before. S7 may want to
    revalidate against a cheap sidecar signal instead.

## Verification

- `node --check` on app.js / protocol.js / engine-client.js / pack-loader.js: OK
- `node frontend/engine/selftest.mjs`: 68/68
- `node frontend/engine/parity/parity.mjs`: 27/27
- `node frontend/engine/property/property.mjs`: PASS
- `node frontend/engine/worker-selftest.mjs`: 86/86 (77 + 9 additive)
- `node frontend/engine/dca-packs-integration.mjs`: 28/28
- `node frontend/engine/portfolio-packs-integration.mjs`: 14/14
- `.venv/bin/python -m pytest`: 172 passed, 8 skipped
- `.venv/bin/ruff check src scripts`: 30 pre-existing findings, unchanged
- Headless browser (static mode, plain `http.server`): demo replay
  labelled at first paint; DCA golden S$13,777.06 / 12 contributions /
  +28.53% (native +24.36%); portfolio table (qty 10, WAC 400); QQQ 2024
  analysis locally computed equals the committed artifact envelope
  (S$13,157.34 / +31.57%; USD 9,635.83 / +27.13%) with a 253-point local
  series; QQQ+SMH compare renders exactly 2 rows (no SOXX demo leak);
  mode indicator transitions verified; **zero** `/api/` requests and zero
  console errors across init + all submits.
- Headless browser (adapter mode via scripts/frontend_server.py): adapter
  init probes, `Adapter · <origin>` rendering, injected outage → local
  fallback with `Local compute (adapter unavailable)`, zero console errors.
- Headless browser (negative paths): out-of-range analysis names QQQ +
  1990-01-02 → 1991-12-31; unknown compare ticker names NOPE + range and
  renders nothing; no demo substitution on any failure; zero `/api/`
  requests; zero console errors.

## Notes for S7

- Subpath QA: `packs` loader is created with
  `baseUrl: new URL('.', document.baseURI)` (subpath-safe), but the S5
  portfolio loader (`s5PackLoader = createPackLoader()`) has an empty base
  URL, which makes its manifest/pack URLs root-absolute
  (`/data/packs/…`) and will break under a GitHub Pages project subpath.
  One-line fix candidate for S7 (give it the same baseUrl) — left alone
  here because S5 behaviour is frozen for this sprint's scope.
- CSP: with the API base empty the app makes no cross-origin calls except
  the Google Fonts `@import` in styles.css (the only remaining external
  reference, flagged in docs/data-pack-budgets.md for self-hosting).
  A `connect-src 'self'`-style policy plus `font-src` for the vendored
  fonts would cover the static deployment; adapter mode needs the adapter
  origin added to `connect-src`. The engine worker is a module worker from
  the same origin (`worker-src 'self'` / `script-src 'self'`).
- The mode indicator inherits `.header-meta`'s `text-transform: uppercase`
  — labels render in caps; the raw text is as specified.
- `nextId` re-minting an identical payload while the same request is still
  in flight dedupes via `track()`; engine-client's pending map keys on id,
  so truly concurrent identical analyze payloads (not reachable from the
  UI because submit buttons disable while busy) would fold into one
  pending entry.
- Manifest cache TTL (24 h) and the S5 loader baseUrl above are the two
  deliberate tradeoffs to revisit in S7.
