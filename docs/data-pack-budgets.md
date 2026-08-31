# Data-pack budgets, caching and asset self-hosting — Sprint 1

Status: Recorded 2026-08-31 against a real build (see "Measured baseline").
Freeze point: the IndexedDB convention in "Browser caching" is binding for
Sprint 5's ledger store (orchestration plan: never parallelize S1.7/S5.6 on
conflicting conventions).

## Measured baseline (full-universe build, 2026-08-31)

Build: `python scripts/build_data_packs.py` against the committed canonical
store (`data_snapshot_id sha256-2612cdfa…`, catalog as of 2026-08-30).
Runtime on this workstation: 10 min 31 s for the full universe.

| Measure | Value |
| --- | --- |
| Securities in manifest | 3,188 (3,172 catalog + 16 priced-but-uncatalogued) |
| Packs written (`security=<id>/year=<YYYY>.json`) | 55,574 |
| Price rows packaged | 13,422,888 |
| Pack payload, min / median / max | 1,609 / 35,155 / 40,492 bytes |
| Packs total (raw) | 1,774,128,729 bytes (1.65 GiB) |
| Manifest (raw) | 18,877,386 bytes (18.0 MiB) |
| Manifest (gzip -9, what Pages serves) | 1,012,546 bytes (0.97 MiB) |
| Example pack, QQQ year 2024 (252 rows): raw / gzip | 37,315 / 9,464 bytes |
| Whole pack set (raw) | 1,793,006,115 bytes (1.67 GiB) incl. manifest |

Typical pack = one security-year ≈ 250 daily bars ≈ 35 KiB raw ≈ 9–10 KiB
over the wire with gzip (GitHub Pages compresses JSON transparently).

## Budgets (enforced by review until a CI size check exists in S7.2)

| Budget | Target | Measured headroom |
| --- | --- | --- |
| Single security-year pack | ≤ 64 KiB raw, ≤ 20 KiB gzip | max measured 40.5 KiB raw / ~10 KiB gzip |
| Manifest | ≤ 25 MiB raw, ≤ 4 MiB gzip | 18.0 MiB raw / 0.97 MiB gzip |
| Cold start: manifest fetch | ≤ 1.5 s on a 10 Mbps link | 0.97 MiB gzip ≈ 0.8 s |
| Cold start: one pack fetch | ≤ 150 ms on 10 Mbps after manifest | ~9.5 KiB gzip ≈ 10 ms |
| Warm start (cached): pack resolve + parse | ≤ 50 ms per pack from IndexedDB | no network; parse only |
| Full-universe pack set | never committed to git; artifact/CDN only | 1.67 GiB exceeds the GitHub Pages 1 GiB site guidance |

Load-time numbers are byte-derived (measured sizes at reference bandwidths);
they are budgets, not browser measurements — Chrome QA timing belongs to
Sprint 7.7.

Deployment consequence: at 1.67 GiB the full-universe pack set must not be
committed to the repository or pushed wholesale to GitHub Pages (1 GiB site
guideline). Sprint 1 publishes packs as a workflow artifact
(`.github/workflows/data-packs.yml`); hosting a subset (e.g. the catalog's
representative securities) or an external object store is a Sprint 6/7
decision. `frontend/data/packs/` is generated output only.

## Lazy-loading plan

1. The browser fetches `packs/manifest.json` once per session and caches it
   in IndexedDB (see below).
2. Support questions (`is security X / date range Y supported?`) are answered
   from the manifest alone — no pack fetch, no calculation.
3. A calculation range resolves to the pack paths it intersects (the manifest
   stores each year's `pack` path); only those files are fetched, ideally in
   parallel with a small concurrency limit (≤ 6).
4. Each fetched pack is validated (`schema_version`, `data_snapshot_id`
   matching the manifest) before use; a mismatching or missing pack means
   the security/range falls back to `unavailable` with a refresh prompt.
5. Cross-year ranges that need FX rates older than a pack's FX window read
   the previous year's pack for that security (windows overlap by 10 days).

## Browser caching (IndexedDB) — convention shared with Sprint 5

To satisfy the "never parallelize S1.7/S5.6" rule, the database naming and
versioning convention is fixed here:

- **Database name:** `sg-invest-cache`. Version: unsigned integer starting
  at `1`, only ever increased.
- **Object stores:**
  - `packs` — keyPath: none; key: the pack's relative path (e.g.
    `security=6cfd001d-…/year=2024.json`); value:
    `{data_snapshot_id, fetched_at, last_used_at, payload}`.
  - `meta` — out-of-line string keys (`"manifest"` holds the cached
    manifest payload plus its `data_snapshot_id`).
  - Sprint 5 adds a `ledger` object store through `onupgradeneeded` when the
    database version is bumped (2 and upward). Migrations are additive
    only: never delete or recreate another feature's store.
- **Invalidation:** a cached pack is valid iff its stored
  `data_snapshot_id` equals the current manifest's `data_snapshot_id`; on
  mismatch the entry is deleted and refetched. A new manifest snapshot
  therefore flushes stale packs lazily, per entry.
- **Eviction:** on `QuotaExceededError`, evict least-recently-used `packs`
  entries (`last_used_at`) until the write succeeds; `meta` and `ledger`
  entries are never evicted by pack cache pressure.
- **Access rules:** all reads/writes go through one shared module
  (Sprint 5's store layer); packs are immutable per snapshot, so cache hits
  never need revalidation beyond the snapshot id comparison.

## External fonts/assets (Sprint 1 task 8 decision)

Audit result:

- `frontend/styles.css:1` —
  `@import url('https://fonts.googleapis.com/css2?family=DM+Mono…&family=DM+Sans…&family=Space+Grotesk…')`.
  This is the only external asset reference in the frontend; it pulls three
  font families (DM Mono, DM Sans, Space Grotesk) from Google Fonts at
  runtime.
- `frontend/index.html` — no external references (local `app.js`,
  `styles.css`, vendored `frontend/vendor/decimal.mjs`).
- `frontend/engine/` — no runtime network requests.

**Decision: self-host.** The three families must be vendored as WOFF2 files
under `frontend/fonts/` with a local `@font-face` block replacing the
`@import`, so the site renders identically when third-party requests are
blocked (offline/CSP/restricted networks). Implementation belongs to the
frontend owner (styles.css is outside Sprint 1's scope); until then the
stylesheet retains exactly one third-party dependency, which Sprint 7's CSP
and request review (S7.6) must re-verify. No new external references may be
introduced anywhere else.
