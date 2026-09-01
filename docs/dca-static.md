# DCA in full static mode — Sprint 4

Status: implemented 2026-09-01. Covers `Todo/sprint-4-dca-static.md` tasks
S4.1–S4.6. `frontend/app.js` changed only inside its DCA region
(`renderDca`, `submitDca`, the `#dca-form` wiring) plus S4-prefixed helpers
appended at the file bottom; all other features are untouched.

## What changed

- **`submitDca` no longer depends on `/api/dca`.** When no API base is
  configured (`meta[name="sg-invest-api-base"]` empty — the GitHub Pages
  default), the request is served entirely in the browser: data packs +
  `pack-loader` + the engine worker.
- **The silent demo-artifact fallback is gone.** Previously a failed `/api/dca`
  request for one specific QQQ form combination silently re-rendered the
  stored demo replay (`state.dcaArtifact`), i.e. a *different request's*
  result. A failure now always surfaces as an explicit error message in
  `#dca-error`; a result is only ever rendered for the request that produced
  it.
- **Adapter mode still works.** When an API base is configured, the adapter
  (`apiGet('/dca', …)`) is tried first; if it fails, `submitDca` falls back to
  the local engine and notes the fallback (`"<adapter error> — falling back to
  the local engine."`) above the form while the local result computes.
- **Loading/progress states (S4.6).** While packs load and the worker
  computes, the submit button shows indeterminate progress text and the
  results panel shows a `role="status"` line (`#s4-dca-progress`, using the
  existing `detail-note` class; the panel is `aria-live="polite"`). Stages:
  "Resolving published data packs…" → "Loading <TICKER> data packs for
  <year>–<year>…" → "Computing DCA replay in the browser…" → worker progress
  envelopes (`received` → `computing`) mapped to queue/compute labels.
- **Request isolation (S4.6).** Each submit tracks its engine request id in
  `s4State.requestId` and calls `engineClient.supersede('dca', id)`, which
  marks every other active `dca` request superseded in the request tracker. A
  resolved/rejected response whose id no longer equals the current one renders
  nothing and shows no error (defense in depth — the tracker already reports
  such envelopes stale). A run-sequence guard stops a superseded run from
  resetting the shared button/progress state of the newer run.
- **Support-gate notice (S4.4).** Engine warnings (`data_quality.warnings`)
  render as before; when the loader classifies the range as `incomplete`, an
  inline `consistency-warning` notice also states the security, the support
  status, the per-year reasons and any pack-level warnings.
- **Frequency fix.** Engine envelopes carry no `request` block, so the kicker
  used to fall back to "Monthly" for every local result; `renderDca` now falls
  back to the submitted `s4State.request.frequency`, so monthly / quarterly /
  yearly are labelled correctly.

## Data flow (static mode)

```
#dca-form
  → submitDca: request {security_id, contribution_sgd, frequency,
    start_date, end_date, dividends, withholding, reinvest}   (SGD amount as string)
  → s4DcaViaPacks (app.js):
      packs.findSecurity({securityId})      manifest.json (fetched once, cached in-module)
      packs.supportFor(entry, start, end)   manifest-only classification
      packs.loadSecurityInputs(entry, …)    per-year pack JSONs → {security, prices,
                                            fx_rates, dividends, corporate_actions,
                                            tax_rules, warnings, support}
      engineClient.dca(payload)             worker scope `dca`; payload mirrors the
                                            /api/dca params (financial values as strings)
  → worker.js → dcaAnalysis (Decimal engine) → Python-shaped envelope
  → renderDca(envelope, {support, packWarnings}) → #dca-results
```

The worker payload is the frozen protocol shape for scope `dca` (`security`,
`prices`, `fx_rates`, `start_date`, `end_date`, `contribution_sgd` +
`frequency`/`scenario`/rows). Form booleans map to
`scenario.dividends_enabled` / `withholding_tax_enabled` /
`reinvest_dividends`. The id is `requestKey('dca', payload)` per
`docs/worker-protocol.md`, so identical requests dedupe by id.

### Wiring note (frozen files untouched)

`createRequestTracker()` has no `nextId()`, but `engine-client.js` mints ids
with `tracker.nextId(scope, payload)`. The client therefore runs only when the
caller injects a compatible tracker; `app.js` creates the client with
`createEngineClient({ tracker: s4Tracker })`, where `s4Tracker` wraps the
frozen tracker, adds `nextId` backed by `requestId(scope, payload)`, and
`track()`s every id so the stale-request guard actually sees the requests. No
frozen module (`pack-loader.js`, `engine-client.js`, `protocol.js`) is
modified.

## Support-gate behavior

`packs.supportFor(entry, startDate, endDate)` classifies from the manifest
alone (no pack fetches):

| Status | Behavior |
| --- | --- |
| `fully_supported` | compute locally; engine warnings still render. |
| `incomplete` | compute locally (the packs contain the rows that exist); render result + inline notice naming status, per-year reasons and pack warnings. |
| `unavailable` (range outside covered years / unknown security) | no engine call, no result rendered — `#dca-error` names the security, the requested range and the reason ("requested range outside covered years X–Y"). A prior result stays on screen; it is never replaced by another request's data. |

Engine-level failures (no trading dates in range, non-positive amount,
protocol violations, worker errors) surface through the same error element
with the engine's typed message (`analysis_data_error`, `engine_value_error`,
`bad_request`, …).

## Adapter mode (unchanged behavior)

With `sg-invest-api-base` set, `submitDca` posts the same params it always did
(`security_id`, `contribution_sgd`, `frequency`, `start_date`, `end_date`,
`dividends`, `withholding`, `reinvest`, `request_key`) to `/api/dca`. On
success the API envelope renders as before. On failure the local path runs
with identical inputs, so both modes are request-equivalent by construction.

## Parity and verification

- `scripts/generate_parity_fixtures.py` gained seven additive DCA fixtures:
  `dca-sgd-security-monthly` (no FX), `dca-accumulating-fund-monthly`
  (dividend rows present but ignored by policy), `dca-zero-dividend-monthly`,
  `dca-invalid-date-range` and `dca-invalid-amount` (error envelopes), plus
  real-data `dca-qqq-2024-quarterly` / `dca-qqq-2024-yearly` goldens.
  Regeneration is byte-identical for the 20 pre-existing fixtures.
- `frontend/engine/parity/parity.mjs`: 27/27.
- `frontend/engine/dca-packs-integration.mjs`: fs-backed fetcher →
  `createPackLoader` → `dcaAnalysis` (no worker, no engineClient) for QQQ
  monthly/quarterly/yearly 2024; exact-string equality on
  `total_contributed_sgd` and `contribution_dates`, `xirr` fields within
  1e-9 — 28/28 checks green.
