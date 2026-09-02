# Sprint 7.5 — FX to 2000, incremental updates, reactive UI

## Goal

Three usability-closing workstreams: (A) source reliable FX history back to
2000-01-01 so foreign-currency securities stop starting at 2003-12; (B) make
the data store incrementally updatable — any new date or date range, without a
full 6-hour rebuild; (C) staged auto-loading in the UI so charts and results
appear without pressing "Run".

## Entry criteria

- [x] Sprints 0–7 exit criteria are all met (verified 2026-09-01).

## Depends on

Sprint 7. Independent of Sprint 8 — may run before, after, or alongside it
(only minor coordination: both may touch CI workflows).

## Track A — FX history back to 2000

Current state: USD/SGD (Yahoo) starts 2003-12-01, capping the foreign-currency
investing timeline. Required pairs derive from catalog native currencies
(USD, GBP, EUR, JPY, HKD, CNY, …).

- [x] **A0 (decision — recorded 2026-09-01):** **MAS is the primary backfill
      source; ECB is the cross-check.** Splice, minimal pull: do NOT re-pull
      the existing 2003+ Yahoo FX; backfill ONLY 2000-01-01 → 2003-11-30 for
      the currency pairs actually needed by securities with pre-2003-12 data
      (derive the pair list from the store; USD dominates). Normalization:
      compute a ratio over the last overlapping month (existing vs MAS rates)
      and scale the MAS window so no level seam enters SGD returns. Record as
      `docs/adr/0002-fx-sources.md`. Data rationale: 1,297 of 3,188 securities
      (40%) predate 2003-12; 0 fully_supported today; 4,936 pre-2004
      security-years already fetched but FX-locked (QQQ/SMH/SOXX/AAPL/MSFT
      first years).
- [x] A1: verify MAS actually covers the missing window for the required
      pairs (api.mas.gov.sg "Exchange Rates — Daily" dataset, or MAS
      statistical-table CSV/XLSX downloads, or a data.gov.sg mirror — register
      for a free API key only if unavoidable and report the requirement). If
      MAS cannot cover a pair/date range, report the exact gap — do NOT
      silently substitute another source. Cross-check every MAS rate against
      ECB (frankfurter.app, no key) and record divergence stats.
- [ ] A2: splice with normalization: compute a normalization ratio over the
      overlap boundary (average ratio of new-source vs existing rates over the
      last overlapping month) and scale the backfilled window to it, so no
      level seam enters SGD returns. Document the seam + normalization in pack
      provenance and result warnings for affected ranges.
- [ ] A3: implement `scripts/backfill_fx_history.py`: fetch, normalize to the
      existing FX row contract (one unit foreign = X SGD, daily), validate
      against the overlapping 2003+ Yahoo window (record divergence stats in
      the summary), write to `data/fx` Parquet with source provenance.
- [ ] A4: rebuild packs; confirm the manifest classifies 2000+ years as
      `fully_supported` for covered currencies; rerun the parity battery
      (FX is input data — the engine is untouched; some parity fixtures pin
      old FX values and must be regenerated deliberately).
- [x] A5: document source, semantics and staleness in `docs/fx-sources.md`
      and surface `fx_source` in pack provenance.

## Track B — incremental updates (no full rebuild)

- [x] B1: design note: incremental update contract. Reuse the existing
      storage layer (upserts keyed by security+trading_date, atomic partition
      replacement, validation gates). Per security, fetch only missing dates
      since its stored `last_date`; fetch a trailing reconciliation window for
      late-arriving dividends/splits; fetch FX tail. Bump `data_snapshot_id`
      as an incremental snapshot (base id + change set).
- [x] B2: implement `scripts/update_incremental.py --since <date|auto>
      [--securities …]`: minutes, not hours; writes an incremental
      `update_summary.json`; rebuilds ONLY touched security/year packs
      (extend `build_data_packs.py` with a `--years` filter).
- [x] B3: tests (synthetic fixtures, no live network): tail fetch, gap
      backfill, late dividend reconciliation, pack rebuild scoping, manifest
      update.
- [x] B4: scheduled workflow `update-incremental.yml` (daily after US close +
      manual dispatch) that optionally chains a Tier-1 redeploy; the full
      rebuild stays as a manual quarterly reconciliation.
- [x] B5: runbook in `docs/data-updates.md`.

## Track C — staged auto-loading (reactive UI)

Request-isolation machinery (supersede, stale guards, cached manifest)
already exists from Sprints 4–6; this sprint wires it to be automatic.

- [x] C1 (stage 1): selecting a security (catalog card or dropdown) auto-loads
      its series chart — no submit required. Series is prices+FX only (cheap).
- [x] C2 (stage 2): the analysis form auto-runs debounced (~750 ms) on any
      change of security/dates/scenario; supersede in-flight runs; button
      becomes "Force refresh"; `unavailable` renders as an inline notice, not
      an error spam.
- [x] C3 (stage 3): same treatment for DCA and portfolio (ledger auto-runs on
      row change, debounced).
- [x] C4: browser tests: debounce fires exactly once per burst; a stale
      response never overwrites a newer one; rapid parameter changes settle on
      the last state; battery stays green.

## Exit criteria

- [ ] Track A: manifest shows `fully_supported` back to 2000 for covered
      currencies; source decision recorded (ADR 0002); parity battery green
      with deliberately regenerated fixtures.
- [x] Track B: a typical daily incremental update completes in minutes with
      scoped pack rebuilds; scheduled workflow green.
- [x] Track C: all three stages browser-verified; no stale results possible.
- [x] Full verification battery green (pytest 172+/8, selftest 68/68, parity,
      property, worker, integration suites, static checks, live-site check).
> **Blocker (2026-09-01) — Track A execution:** MAS is inaccessible —
> `api.mas.gov.sg` does not resolve; `eservices.mas.gov.sg/api` serves a
> maintenance failover page; the entire `www.mas.gov.sg/statistics/*` section
> serves maintenance pages; the data.gov.sg mirror is weekly-only in-window
> (violates the 7-day staleness rule), server-capped at 1,000 rows, ends
> 2003-11-12, and has no HKD/JPY columns. Per the A0 instruction the agent
> STOPPED rather than substitute sources. All infrastructure is complete and
> tested (22 fx tests; cross-check machinery verified — frankfurter covers the
> full window for all 3 required pairs: USD, HKD, JPY). Re-run is one command
> per docs/fx-sources.md once MAS restores access. **Open decision for the
> coordinator/user:** wait for MAS, or pivot the primary to ECB (already
> verified to cover the full window) with MAS as the later cross-check.
