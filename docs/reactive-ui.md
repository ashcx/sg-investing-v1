# Reactive UI — staged auto-loading (Sprint 7.5, Track C)

Status: implemented 2026-09-02. Covers `Todo/sprint-7.5-fx-incremental-reactive.md`
tasks C1–C4. Only `frontend/app.js` changed (plus this document); the frozen
engine layer (`frontend/engine/**`) is untouched, and no index.html/styles.css
edits were needed.

## What changed (function level)

| Function | Change |
| --- | --- |
| `submitAnalysis` / `s7RunAnalysis` | Submit is now a thin wrapper that cancels the panel's pending debounce and force-runs the shared `s7RunAnalysis` closure. The debounced auto-run calls the same closure with `mode: 'auto'` — identical validation, progress states, run-sequence guard and rendering. |
| `submitDca` / `s7RunDca` | Same split for DCA; the previous `dca` engine request id is captured before the run and passed to `s4DcaViaPacks` for supersede + cancel. The adapter path gained the missing run-seq check (a stale adapter envelope can no longer render). |
| `submitPortfolio` / `s7RunPortfolio` | Same split for the portfolio. |
| `s4DcaViaPacks` | Accepts `{ previousEngineId }`; marks the new request the `dca` scope's keep id (`engineClient.supersede`) and politely cancels the predecessor (`engineClient.cancel`). |
| `s6AnalysisViaPacks` | Accepts `{ supersede, previousEngineId }` (analysis panel only — compare passes nothing and is unchanged). On mint: `s7LastAnalyzeId = id`, `supersede('analyze', id)`, cancel predecessor. |
| `s5LocalPortfolio` | Tracks `s5LastPortfolioRequestId`; a newer portfolio run supersedes (as before) and cancels the previous request at the worker. |
| `s7LoadSeries` / `s7ScheduleSeries` / `s7AnalysisDateRange` | **Stage 1**: on any security selection, load that security's series chart for the analysis form's current date range (fallback: trailing two years when the form dates are empty or inverted) — packs + `s6SeriesFromInputs` only, no engine request, no submit. |
| `s7WireReactive` | Wires every reactive trigger (below). Called from `wireEvents`; computes nothing itself. |
| `s7SetForceRefreshLabels` | Relabels the three panel submit buttons to "Force refresh" at init (label only — still an immediate run that cancels pending debounces). |
| `s7CancelAutoRun` / `s7ScheduleAutoRun` | One single-shot timer per panel; every new input replaces it; every manual submit clears it. |
| `renderSeries` | Chart-source label also honours `state.seriesSource` (stage-1 locally loaded chart). |

The run counters and series provenance are exposed read-only as
`window.__sgInvestReactive` for the headless browser tests; nothing in the app
reads it back.

## Stages

1. **Stage 1 — series on selection (C1).** Selecting a security via a catalog
   card, `#security-select` or `#dca-security` schedules a series load
   (250 ms debounce) for the analysis form's current date range — or the
   trailing two years when the dates are empty/inverted. The chart renders
   into the existing `#series-card` (visible from the demo replay's first
   paint) with the source label "Series computed from local data packs". No
   engine request, no form submit, and the analysis metrics on screen are
   untouched until stage 2 replaces them (~750 ms later when the analysis
   auto-run lands). If the manifest classifies the range as `unavailable`, a
   single inline notice is written to `#form-error`; nothing else changes.
2. **Stage 2 — analysis auto-run.** Any `change` of `#security-select`,
   `#start-date`, `#end-date`, the scenario toggles or the scenario preset
   schedules `s7RunAnalysis` after **750 ms**. Validation is identical to the
   manual submit; a failing auto-run only sets the existing inline notice and
   never computes. `unavailable` renders through the existing
   `#artifact-unavailable` panel plus one `#form-error` message — never an
   error per keystroke (triggers are `change` events, and the debounce
   coalesces bursts).
3. **Stage 3 — DCA and portfolio.** DCA auto-runs after **750 ms** on
   `#dca-security`, `#dca-contribution`, `#dca-frequency`, `#dca-start`,
   `#dca-end` and the three DCA scenario toggles. The portfolio auto-runs
   after **1000 ms** on `#portfolio-as-of` changes and delegated
   `#ledger-rows` `change` events — including rows added via "+ Add
   transaction", "Clear ledger" and JSON import. Text/number ledger inputs
   fire `input` per keystroke but `change` only on commit/blur, so active
   typing never schedules a run.

## Debounce semantics

- One timer per panel (`s7Reactive.timers`): series 250 ms, analysis 750 ms,
  DCA 750 ms, portfolio 1000 ms. A new input clears the pending timer and
  starts a new one (leading edge never fires; only the quiet period runs).
- Manual submits ("Force refresh") clear their panel's pending timer and run
  immediately, so a click right after typing produces exactly one run.
- Only `change` events trigger (selects, date pickers, checkboxes, blur/Enter
  commits) — never `input`, so typing in ledger fields is free.
- The runs counters (`window.__sgInvestReactive.runs`) exist for the browser
  tests: each burst settles on exactly one run per panel.

## Supersede semantics

Layers, outermost first (identical to the manual-submit paths — the reactive
UI simply fires them automatically):

1. **Panel run sequence** (`s6Runs.analysis`, `s4State.runSeq`,
   `s6Runs.portfolio`): each run bumps its panel's sequence; a response whose
   sequence is no longer current renders nothing and resets no shared UI
   state. This is the render gate — it alone makes stale overwrites
   impossible.
2. **Tracker stale guard** (`engineClient.supersede(scope, newId)`): the new
   request is the scope's keep id; every other active request in the scope is
   marked `superseded`, so late envelopes for them are recorded stale by
   `protocol.createRequestTracker`.
3. **Worker cancellation** (`engineClient.cancel(previousId)`): the panel's
   own previous request is cancelled at the worker (queued requests are
   dropped; completed computations are discarded at delivery), so a
   superseded computation stops wasting work. Ids are compared first — an
   identical payload re-mints the same deterministic id
   (`tracker.nextId` dedupe) and is never "cancelled" against itself.

Cross-panel safety: the analysis panel only supersedes/cancels ids it minted
itself (`s7LastAnalyzeId`); compare's sequential per-ticker analyze requests
are never cancelled by the reactive panel, and a superseded tracker record
never gates browser delivery (the run-sequence guard remains the render gate).
Per-scope single-flight: at most one relevant in-flight request per panel;
older ones are superseded/cancelled, not queued.

## Composition with the S4/S6 guards

The reactive path adds **no** new isolation machinery — it reuses the existing
request-isolation stack end to end:

- worker request-id verification (`id === requestKey(scope, payload)`),
- the tracker stale guard (`observe` → `superseded`/`cancelled` records),
- the S4 DCA guards (`s4State.requestId` check, `s4State.runSeq`),
- the S6 run-sequence guards (`s6Runs.analysis` / `s6Runs.portfolio`).

Auto-runs enter through the same submit closures as manual runs, so button
busy state, progress stages (`s6SetButtonProgress`, `s4SetDcaProgress`), the
`#s4-dca-progress` status line, unavailable panels and the compute-mode
indicator all behave exactly as documented in `docs/dca-static.md` and
`docs/sprint-6-notes.md`.

## No auto-run loops

A run re-renders the UI but never re-fires a trigger: render code only sets
`textContent` / `innerHTML` / `classList` / `.value` / `.checked`
programmatically, none of which dispatch events, and the currency switches it
binds are click handlers. The browser suite verifies counters are stable
after settling (analysis, DCA, portfolio each checked).

## Test hooks

`window.__sgInvestReactive` exposes `{ timers, runs: {series, analysis, dca,
portfolio}, seriesSecurityId }` — read-only introspection for
`browser-test-c.py` (debounce-once-per-burst, supersede, series provenance).
`seriesSecurityId` is set only when the stage-1 loader has actually rendered a
chart, so test (c) can prove the chart appeared before any analysis ran.

## Verification

- `node --check frontend/app.js`: OK.
- Headless browser, static mode (`/tmp/opencode/browser-test-c.py`, plain
  `http.server`): 22/22 — series-on-select with zero analysis runs, chart
  source label, debounce exactly-once per burst (analysis/DCA), no auto-run
  loops, A→B settles on B with exactly two runs, unavailable inline notice
  (no spam) and recovery, DCA golden S$13,777.06 / 12 contributions via the
  auto-run, ledger typing schedules nothing / blur auto-runs once, force
  refresh immediate + debounce-cancelled, "Force refresh" label, zero `/api`
  requests, zero console errors (the optional `build-info.json` 404 is
  documented-expected and excluded, per docs/sprint-7-notes.md S7.4).
- Full battery (selftest, parity, property, worker, pack integrations, pytest,
  ruff): see the sprint report; all green.
