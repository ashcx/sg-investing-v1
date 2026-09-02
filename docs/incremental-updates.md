# Incremental data updates (Sprint 7.5, Track B)

Status: design note and contract for `scripts/update_incremental.py` and the
scoped-merge mode of `scripts/build_data_packs.py`. Operator procedures live
in `docs/data-updates.md`; the pack/manifest schema itself is frozen in
`docs/data-pack-schema.md`.

Goal: refresh the canonical store for ANY new date or date range in minutes,
without the ~6-hour full-catalog rebuild (`scripts/update_data.py`), and
republish only the affected browser packs.

## Fetch contract

One run = one pass over the selected securities. For every selected security:

| Dataset | Window start | Window end |
| --- | --- | --- |
| Prices | `max(catalog history_start, last stored price date − reconciliation window)`; an explicit `--since` older than that widens the window back (gap backfill). No stored prices → full fetch from the floor ("straggler" path). | `end_date` (default: today, UTC) |
| Dividends | Provider sweep start from the dividend coverage report: `queried_through − max(reconciliation window, --since span)`; no prior coverage → catalog floor. Accumulating/non-distributing securities are skipped. | `end_date` |
| Corporate actions | `max(catalog history_start, last stored action − reconciliation window)`; no stored actions → catalog floor. Yahoo's `.actions` is an unbounded per-ticker fetch, so this step can be skipped with `--skip-actions`. | `end_date` |
| FX | `max(catalog history_start, last stored rate − reconciliation window)` per required pair (native currency ≠ SGD, derived from the selection). A pair with no stored history is fetched from the floor regardless of `--since` — packs need FX at every price date. | `end_date` |

The default trailing reconciliation window is **45 days**
(`RECONCILIATION_DAYS_DEFAULT`) so late-arriving dividends, restated events
and corporate actions inside that tail are re-reconciled on every run.

All writes go through the existing storage layer
(`sg_investing.data.storage.ParquetStore`): upserts keyed by security +
trading/event date, partition replacement only after validation of both the
incoming rows and the merged partition, atomic file writes. Provider
normalization is reused from the full-refresh path (`update_security_prices`,
`update_fx_rates`, `backfill_dividends`) — the incremental script never
duplicates provider logic.

## Change detection and change keys

Before and after the fetch/upsert phase, the run projects the affected store
partitions and compares value signatures:

- prices: `(security_id, date) → (open, high, low, close, volume)`;
- dividends/corporate actions: stable event signatures that deliberately
  exclude `retrieved_at`, so a reconciliation refetch returning identical
  economics registers no change;
- FX: `(base_currency, rate_date) → rate`.

Every new or restated row yields a change key:

- `price:<security_id>:<date>`
- `dividends:<security_id>:<ex-date>:<amount>:<currency>:<source_id>`
- `corporate_actions:<security_id>:<effective-date>:<type>:<ratio>`
- `fx:new:<date>:<currency>` / `fx:restated:<date>:<currency>:<rate>`
- `security:<security_id>:backfilled:<rows>` (straggler full-history fetch)

The change set is capped at 10,000 keys (sorted, then truncated) so a
misused full-history run still produces a bounded summary and digest.

## Scoped pack rebuild and manifest merge

The touched `(security_id, year)` pairs are derived from the change keys,
plus:

- straggler full-history fetches (every partition year they wrote);
- FX restatements and FX gap-fills (`fx:new` rates dated on or before a
  security's stored last price date) mapped through each pack's FX window
  (`[first price date − 10 calendar days, last price date]`, mirroring
  `FX_LOOKBACK_CALENDAR_DAYS` in the packs module).

With `--build-packs` (default) the run invokes
`python scripts/build_data_packs.py --security <id> … --years <YYYY,…>` for
exactly those pairs. The scoped builder:

1. rebuilds only the matching security/year pack files;
2. MERGES `manifest.json`: touched entries are recomputed from the rebuilt
   packs, entries of untouched securities are preserved (their pack files
   are not touched, byte-for-byte), and `summary`/`support` counts are
   recomputed over the union;
3. keeps the previous manifest's top-level `scope` (the merged manifest
   still answers for that universe) and records the rebuild scope plus the
   base `data_snapshot_id` in a new `incremental` block
   (`mode: "merge"`, `replaced_packs`, `updated_entries`, `scope`).

Without scoping flags `build_data_packs.py` behaves exactly as before: a
full rebuild that resets the output directory and replaces the manifest (no
`incremental` block). A full rebuild after any merge therefore also cleans
up stale scoped state.

Note: `--years` filters by calendar year across all `--security` values, so
an unrelated year of a touched security may also be recomputed when the
touched years span a union. That is harmless (content is recomputed from the
same store) and only ever over-rebuilds, never under-rebuilds.

## Snapshot identity and the incremental chain

- `compute_data_snapshot_id(data/)` — full content hash of the store; this
  is what pack manifests carry (computed at build time).
- The update summary additionally tracks a **chain hash** computed over the
  same scheme but excluding the root-level `update_summary.json`. Every run
  rewrites that file with fresh timestamps after hashing, so including it
  would make the continuation check between runs impossible.
- `incremental_snapshot_id = sha256(base_id + "\\0" + each sorted change key
  + "\\x1f")`, reported as `incr-<32 hex>`. An empty change set is a no-op
  that keeps the base id.
- Chain continuation: a run starts from the previous run's incremental id
  only when the previous summary was itself an incremental run **and** its
  store hash matches the current chain hash exactly. After a full rebuild or
  any external store change the chain restarts from the content hash.

## Idempotency

Re-running an already-applied update refetches the same tail, registers an
empty change set and therefore: keeps the incremental snapshot id, rebuilds
no packs, and writes only `data/update_summary.json` (plus the dividend
coverage snapshot files, which carry fresh timestamps). Re-runs are safe by
construction; a no-change run still produces a complete summary with
`change_set.count == 0`.

Note that `record_coverage_snapshot` refreshes
`data/dividends/coverage_history.json` on every run, so the *full* store
hash (and any pack manifest built afterwards) changes even when no market
data changed. The chain hash excludes the summary file; the coverage history
is part of the store and is treated as data.

## Dry run

`--dry-run` prints exactly what a real run WOULD do without any network call
or write: per-security fetch windows (start/end, years, provider endpoint),
FX tails, the estimated scoped pack-rebuild command and the list of store
paths that would be written. It only reads the local store, so it is safe to
run anywhere and is deterministic for a given store state.

## `data/update_summary.json` (incremental mode)

| Field | Meaning |
| --- | --- |
| `mode` | `"incremental"` (dry runs report `"dry-run"` and are not persisted). |
| `since`, `end_date`, `reconciliation_days` | Run parameters. |
| `securities_selected_count`, `full_history_fetch_securities` | Selection size; tickers that needed a full fetch. |
| `base_data_snapshot_id` | Chain base: previous incremental id, or the store content hash when the chain restarted. |
| `data_snapshot_id` | Chain hash of the store after the run (excludes `update_summary.json`, see above). |
| `incremental_snapshot_id` | `incr-…` head of the chain after this run. |
| `store_content_hash_unchanged` | True when the canonical datasets are byte-identical to the previous run. |
| `change_set` | `{count, truncated, keys}` — capped at 10,000 keys. |
| `changed_securities`, `changed_years` | `(security_id, year)` pack partitions touched by this run. |
| `price_rows_fetched`, `price_dates_new`, `price_dates_restated` | Price outcome. |
| `dividend_events_new_or_restated`, `dividend_events_restated` | Dividend outcome. |
| `corporate_actions_new_or_restated`, `corporate_action_errors` | Corporate-action outcome. |
| `fx_rows_new_or_restated`, `fx_rows_restated`, `fx_fetch_errors` | FX outcome. |
| `updated` / `warnings` / `failed`, `results[]` | Per-security status (`partitions_written` per row). |
| `dividends`, `dividend_coverage_warnings`, `dividend_updates` | Dividend coverage report snapshot and per-ticker sweep results. |
| `packs` | Command and JSON summary of the scoped pack build (`merge.replaced_packs`, `merge.updated_entries`), or `null` when nothing was rebuilt. |

## Known limitations

- The scoped pack builder composes private helpers from
  `sg_investing.data.packs` (`_manifest_entry`, `_fx_coverage`,
  `_manifest_warnings`, `_write_json`) because the module exposes no
  scoped-build primitive and `src/` is frozen for this sprint. Pack content
  and manifest schema stay byte-identical to full builds; if a scoped
  primitive is later added upstream, this composition should be replaced.
- Dividend restatement detection relies on stable provider event identity.
  Yahoo-derived `source_id`s embed the amount, so a restated Yahoo dividend
  counts as "new" (different event id) rather than "restated"; both cases
  are captured by `dividend_events_new_or_restated` and produce the same
  change keys and pack touches.
- Corporate-action reconciliation is unbounded per ticker on the provider
  side (yfinance `.actions`); scheduled runs may use `--skip-actions` and
  reconcile actions in the weekly sweep instead (see `docs/data-updates.md`).
