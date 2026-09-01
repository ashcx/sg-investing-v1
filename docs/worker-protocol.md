# Worker request/response protocol (Sprint 3, S3.3)

Transport-agnostic message protocol for running the calculation engine
(`frontend/engine/`) off the UI thread. The same envelopes are spoken by the
browser module worker (`frontend/engine/worker.js`) and the Node verification
adapter (`frontend/engine/worker.node.mjs`, used by
`frontend/engine/worker-selftest.mjs`).

This is freeze point 3 of `Todo/orchestration-plan.md` (worker protocol +
deterministic request keys, together with `frontend/engine/request-keys.js`).
Sprint 4 task S4.6 (loading states + request isolation) builds directly on
`createRequestTracker()` described below.

Files involved:

| File | Role |
| --- | --- |
| `frontend/engine/protocol.js` | Envelope factories, error mapping, `createRequestTracker`. No Node imports; runs in browser and Node. |
| `frontend/engine/worker.js` | Browser module worker: receives request envelopes, dispatches to the engine, emits progress/results/errors, handles cancellation. Auto-attaches when loaded inside a `WorkerGlobalScope`. |
| `frontend/engine/worker.node.mjs` | Thin Node `worker_threads` adapter around the same worker logic (verification only, never imported by the browser). |
| `frontend/engine/worker-selftest.mjs` | `node frontend/engine/worker-selftest.mjs` — parity, typed errors, cancellation timing, responsiveness and request-key proofs. |

## Envelopes

All envelopes are plain JSON objects (structured-clone safe). `id` is always
the deterministic request id (see below).

### Request (client → worker)

```json
{ "type": "request", "id": "analyze:9f2c…", "scope": "analyze", "payload": { … } }
```

- `scope` ∈ `analyze | dca | portfolio` and selects the engine entry point:
  `analyzeSecurity` / `dcaAnalysis` / `analyzePortfolio`.
- `id` **must** equal `requestKey(scope, payload)`; the worker recomputes it and
  rejects mismatches with a `bad_request` error envelope.
- Payloads mirror the Python request models (snake_case). **All financial
  values MUST be strings** (decimal-safe rule: no `Number` for money, FX,
  quantities). The worker enforces this per scope:

| Scope | Required fields | Optional fields | String-enforced numeric fields |
| --- | --- | --- | --- |
| `analyze` | `security`, `prices`, `fx_rates`, `start_date`, `end_date`, `initial_sgd` | `scenario`, `dividends`, `corporate_actions`, `tax_rules` | `initial_sgd`; row `close`, `rate_to_sgd`, `amount`, `ratio`, `rate` |
| `dca` | `security`, `prices`, `fx_rates`, `start_date`, `end_date`, `contribution_sgd` | `frequency`, `scenario`, `dividends`, `corporate_actions`, `tax_rules` | `contribution_sgd`; same row fields |
| `portfolio` | `transactions`, `securities`, `prices`, `fx_rates`, `as_of` | — | row `quantity`, `cash_amount`, `fees` |

  Unknown top-level fields are rejected (`bad_request`) so typos cannot silently
  change semantics. Row objects are not exhaustively validated; violations the
  engine cares about surface as typed engine errors.

### Progress (worker → client)

```json
{ "type": "progress", "id": "…", "stage": "received" }
{ "type": "progress", "id": "…", "stage": "computing", "done": 0, "total": 1 }
{ "type": "progress", "id": "…", "stage": "complete", "done": 1, "total": 1 }
```

Stages are worker boundaries: `received` (queued) → `computing` → `complete`,
emitted immediately before the result envelope. `done`/`total` are optional
counters. Progress is advisory; clients must not use it for correctness.

### Result (worker → client)

```json
{ "type": "result", "id": "…", "ok": true,  "result": { …engine envelope… } }
{ "type": "result", "id": "…", "ok": false, "error": { "code": "…", "message": "…", "details": { … } } }
```

On `ok: true`, `result` is the engine's result envelope serialized exactly like
the Python `model_dump(mode="json")` shape (Decimals as strings; identical to
calling the engine in-thread and JSON-serializing — proven by the selftest).

Error `code` values (see `ERROR_CODES` in `protocol.js`):

| Code | Source | Meaning |
| --- | --- | --- |
| `cancelled` | `CancellationError` | Request was cancelled (see semantics below). |
| `analysis_data_error` | `AnalysisDataError` | Data-driven failure (missing prices, bad dividend dates, …), Python-parity messages. |
| `engine_value_error` | `EngineValueError` | Invalid calculation input (non-positive amounts, inverted ranges, oversells, …). |
| `bad_request` | protocol validation | Malformed envelope, unknown scope, payload validation problems (details.problems), or id/key mismatch. |
| `internal_error` | anything else | Unexpected failure. `details.name` carries the error class; the stack is included only in debug mode. |

`details` always contains `name` (and `problems` for `bad_request` payload
validation). Stacks never leave the worker unless debug mode is on.

### Cancelled (worker → client)

```json
{ "type": "cancelled", "id": "…" }
```

Terminal confirmation that the request will never produce a result.

### Cancel (client → worker)

```json
{ "type": "cancel", "id": "…" }
```

## Request ids and request keys

- `id = requestKey(scope, payload)` (`frontend/engine/request-keys.js`, frozen):
  `<scope>:<fnv1a64-hex>` over the canonical (recursively key-sorted) JSON of
  the payload.
- Pure and deterministic: same content in any key order → same id; different
  payloads → different ids; different scopes → different namespaces.
- Consequences by design:
  - Re-submitting an identical payload yields the same id. The worker ignores a
    duplicate while the identical request is still in flight; the client
    tracker dedupes/handles the rest (see below).
  - Identical payloads can be served/deduplicated by id; a cache layer in
    Sprint 4+ can key on `id` directly.
- The worker verifies `id === requestKey(scope, payload)` and answers with
  `bad_request` otherwise, so clients cannot desynchronize from the key
  contract.

## Cancellation semantics

The engine entry points are synchronous, so cancellation is layered:

1. **Cooperative (queued / between stages).** On `{type:'cancel', id}` the
   worker records the id. A queued request that has not started computing is
   aborted immediately and answered with `{type:'cancelled', id}` — it never
   reaches `computing`. The worker also re-checks the cancel flag after the
   engine call returns and **discards the result**, answering `cancelled`
   instead, so a result envelope can never follow a cancel. The window between
   "received" and "computing" is configurable via `createEngineHost({ yieldMs })`
   (default `0`; the browser auto-attach uses the default). A cancel that is
   processed before the compute task starts always wins.
2. **Forced (in-flight kill).** While the synchronous engine call runs, the
   worker cannot process messages. To abort a long computation immediately the
   client terminates the worker
   (`worker.terminate()` in the browser, `worker.terminate()` on a
   `worker_threads` Worker in Node) and maps the terminated worker's in-flight
   ids to `code: 'cancelled'` locally in the tracker. The selftest proves this
   path aborts in ~150ms against a computation that takes ~4s.
3. **Tracker guard.** `createRequestTracker` marks locally cancelled ids as
   terminal. Any late `result`/`progress` envelope for such an id (e.g. from a
   race, a duplicate, or a restarted worker) is reported as **stale** via the
   `onStale` callback and never delivered to the application. This is the
   behaviour Sprint 4 task S4.6 relies on for request isolation.

`createRequestTracker({ onStale })` API:

- `track(requestOrId, scope?)` → record; starts `pending`. Re-tracking an
  **active** id returns the existing record (dedupe); re-tracking after a
  terminal state starts a fresh attempt.
- `markRunning(id)`, `markCancelled(id)` (local cancel, returns whether it
  transitioned), `supersedeScope(scope, keepId?)` (S4.6 request isolation:
  supersedes every other active request of the scope).
- `observe(envelope)` → `{ delivered, stale, reason?, record }` for every
  inbound envelope; updates record state and fires `onStale` for stale ones.
- `stateOf(id)`, `getRecord(id)`, `activeInScope(scope)`, `size`.
- Record states: `pending → running → succeeded | failed | cancelled |
  superseded` (terminal states never change, except that a
  `code:'cancelled'` error envelope on a cancelled id is accepted as an
  idempotent confirmation).

## Browser integration point (Sprint 4)

```js
const worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
worker.addEventListener('message', (event) => tracker.observe(event.data));
worker.postMessage(createRequest('dca', payload)); // id = requestKey('dca', payload)
```

- `new URL('./worker.js', import.meta.url)` resolves **relative to the importing
  module**, so it works unchanged under a GitHub Pages project subpath
  (`https://<org>.github.io/<repo>/…`); never use absolute `/engine/worker.js`
  paths. All worker-internal imports (`./index.js`, `./protocol.js`,
  `./request-keys.js`, `../vendor/decimal.mjs`) are relative for the same
  reason.
- `{ type: 'module' }` is required — `worker.js` is an ES module.
- Debug mode: append a query param —
  `new URL('./worker.js?debug=1', import.meta.url)` — to include stacks in
  error envelopes during development. Keep production URLs param-free.
- Client-side bookkeeping: create one `createRequestTracker()` per worker,
  `track()` every request, route every inbound envelope through `observe()`,
  and use `supersedeScope`/`markCancelled` for UI-level request isolation
  (S4.6). On worker termination, treat every non-terminal tracked id as
  `cancelled` (`markCancelled`).
- Recommended cancel flow: post `{type:'cancel', id}` first; if the request must
  abort immediately and the worker is busy computing, terminate the worker and
  respawn it (ids and the tracker make the replacement seamless).

## Node verification

```
node frontend/engine/worker-selftest.mjs
```

Runs the same `worker.js` logic inside `node:worker_threads` via
`worker.node.mjs` and proves: parity of worker vs in-thread envelopes (fixture +
large 40y/20y synthetic ranges), typed error mapping, id integrity, cooperative
and forced cancellation (with timing), parent-thread responsiveness during
computation, and request-key identity rules.
