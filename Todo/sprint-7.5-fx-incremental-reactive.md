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

- [ ] **A0 (planning checkpoint — user sign-off required before coding):**
      present the source comparison and record the decision as
      `docs/adr/0002-fx-sources.md`. **User direction (2026-09-01): splice,
      minimal pull** — do NOT re-pull the existing 2003+ Yahoo FX; backfill
      ONLY the missing window (2000-01-01 → 2003-11-30, ~10 currency pairs).
      Data rationale: 1,297 of 3,188 securities (40%) predate 2003-12 (1,178
      start at the 2000-01 horizon); 0 are fully_supported today; 4,936
      pre-2004 security-years are already fetched but FX-locked — including
      QQQ/SMH/SOXX/AAPL/MSFT first years. Source choice remains open:
      **ECB reference rates (primary candidate)** vs **MAS** (SGD-authoritative)
      vs others listed below.
- [ ] A1: verify candidate sources for daily rates over 2000-01-01 →
      2003-11-30: **MAS** (Monetary Authority of Singapore — official SGD
      reference rates, the SGD-authoritative source), **ECB reference rates**
      (daily since 1999, publishes SGD and majors vs EUR; USD/SGD derivable as
      EUR/SGD ÷ EUR/USD; clean free API via frankfurter.app), Stooq (free CSV,
      licence unclear), FRED H.10 (verify whether SGD is covered), Dukascopy
      (tick data, heavier). Rate each on: coverage of the missing window,
      currencies, licence, stability, and "reference rate vs market close"
      semantics.
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
- [ ] A5: document source, semantics and staleness in `docs/fx-sources.md`
      and surface `fx_source` in pack provenance.

## Track B — incremental updates (no full rebuild)

- [ ] B1: design note: incremental update contract. Reuse the existing
      storage layer (upserts keyed by security+trading_date, atomic partition
      replacement, validation gates). Per security, fetch only missing dates
      since its stored `last_date`; fetch a trailing reconciliation window for
      late-arriving dividends/splits; fetch FX tail. Bump `data_snapshot_id`
      as an incremental snapshot (base id + change set).
- [ ] B2: implement `scripts/update_incremental.py --since <date|auto>
      [--securities …]`: minutes, not hours; writes an incremental
      `update_summary.json`; rebuilds ONLY touched security/year packs
      (extend `build_data_packs.py` with a `--years` filter).
- [ ] B3: tests (synthetic fixtures, no live network): tail fetch, gap
      backfill, late dividend reconciliation, pack rebuild scoping, manifest
      update.
- [ ] B4: scheduled workflow `update-incremental.yml` (daily after US close +
      manual dispatch) that optionally chains a Tier-1 redeploy; the full
      rebuild stays as a manual quarterly reconciliation.
- [ ] B5: runbook in `docs/data-updates.md`.

## Track C — staged auto-loading (reactive UI)

Request-isolation machinery (supersede, stale guards, cached manifest)
already exists from Sprints 4–6; this sprint wires it to be automatic.

- [ ] C1 (stage 1): selecting a security (catalog card or dropdown) auto-loads
      its series chart — no submit required. Series is prices+FX only (cheap).
- [ ] C2 (stage 2): the analysis form auto-runs debounced (~750 ms) on any
      change of security/dates/scenario; supersede in-flight runs; button
      becomes "Force refresh"; `unavailable` renders as an inline notice, not
      an error spam.
- [ ] C3 (stage 3): same treatment for DCA and portfolio (ledger auto-runs on
      row change, debounced).
- [ ] C4: browser tests: debounce fires exactly once per burst; a stale
      response never overwrites a newer one; rapid parameter changes settle on
      the last state; battery stays green.

## Exit criteria

- [ ] Track A: manifest shows `fully_supported` back to 2000 for covered
      currencies; source decision recorded (ADR 0002); parity battery green
      with deliberately regenerated fixtures.
- [ ] Track B: a typical daily incremental update completes in minutes with
      scoped pack rebuilds; scheduled workflow green.
- [ ] Track C: all three stages browser-verified; no stale results possible.
- [ ] Full verification battery green (pytest 172+/8, selftest 68/68, parity,
      property, worker, integration suites, static checks, live-site check).