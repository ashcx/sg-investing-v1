# Incremental-update recovery — 18 October 2026

Implementation and subsequent self-review performed sequentially in the main
instance. No UI changes, engine formula changes, canonical production refresh,
automatic commit or deployment are included. This work is the user-required
prerequisite to the separate Sprint 12–15 PRs.

## Changes

- Exact-window price groups, bounded batch-capable calls, and incoming-key-only
  comparisons per market/year. Healthy listings cannot inherit a stale peer's
  thirteen-year download. Listing/currency identity is checked before upsert.
- The incremental live Yahoo path uses individual, raised-error price queries
  and explicitly dated event history. All datasets share request pacing,
  transient-only retry/backoff, a rate-limit circuit and request/time budgets.
- Successful empty action queries persist their coverage cursor; missing or
  failed history remains an error. FX rows outside inclusive requested dates
  are filtered at the provider boundary.
- Journaled stages, completed counts, elapsed time and peak process memory;
  nonzero CLI status on incomplete input or pack failures; full-refresh schedule
  removed; bounded/shared-concurrency daily workflow with diagnostic uploads.
- Scoped updater builds refuse a missing, filtered, unsafe or incomplete pack
  baseline. CI defaults to canonical review artifacts; optional packs are a full
  build. Operator application/publication remains an explicit separate step.
- Test runtime constraints plus dependency inventories. The clock-dependent
  pack-byte test now controls its generation-time input, retaining exact byte
  assertions without relying on two builds completing in the same wall second.

## Checks

| Check | Result | Record |
| --- | --- | --- |
| Python normal suite | 248 passed, 8 opt-in smoke deselected | [pytest.txt](pytest.txt) |
| Ruff, changed Python | Passed | [ruff.txt](ruff.txt) |
| Engine | 68/68 | [engine-selftest.txt](engine-selftest.txt) |
| Golden parity | 27/27 | [parity.txt](parity.txt) |
| Initial plus recurring cases | Passed | [initial-lump.txt](initial-lump.txt) |
| Workers | 90/90 | [worker.txt](worker.txt) |
| Properties | 19 / 1,473 cases | [properties.txt](properties.txt) |
| Full pack build | 3,188 securities; 55,574 packs; 13,422,888 price rows | [pack-build.json](pack-build.json) |
| DCA pack integration | 29 checks passed | [dca-packs.txt](dca-packs.txt) |
| Portfolio pack integration | 14/14 | [portfolio-packs.txt](portfolio-packs.txt) |
| Static site with generated packs | Passed | [static-site.txt](static-site.txt) |

The full pack build is 1,855,763,530 bytes. Existing coverage gaps are preserved:
four catalog entries lack prices; the snapshot lacks required CNY/EUR/GBP FX
history. A generated complete pack set is not a claim of complete market data.

A read-only whole-catalog recording probe selected 3,172 listings, made 106
fake batch calls capped at 32, and kept QQQ at 2026-07-13 while M12.SI remained
alone at 2013-01-21. It made zero network calls/canonical writes.

## Live canary

The initial QQQ/ES3.SI/VALL.SW canary failed closed on a Yahoo FX observation
outside requested dates. The corrected adapter was regression-tested; a fresh
copied-snapshot run completed with all three updated, 141 price rows, 67 FX rows,
nine requests, no retries/rate-limit circuit, approximately ten seconds elapsed
and approximately 1.8 GiB peak process memory. No copied data was applied to the
repository. Full current canonical snapshot identity was verified unchanged:
`sha256-8121f966801bd011f59892f8a71cf3d872b6358ad5557aa5032f2ce46e769d67`.

- [Initial incomplete outcome](live-canary-summary.json)
- [Initial diagnostic trace](live-canary-diagnostics.log)
- [Corrected complete outcome](live-canary-fixed-summary.json)
- [Corrected diagnostic trace](live-canary-fixed-diagnostics.log)

The compact summaries omit the thousands of unselected dividend-coverage rows
and the raw change-key list; full responses remain in the disposable canary
folders for inspection. Selected outcomes, errors and telemetry are retained.

## Remaining evidence

The full-universe live run is in progress on another disposable copied snapshot.
Its eventual outcome must be recorded, including failures and unsupported
listings; do not infer success from the small canary or a green unit suite.
Actual scheduled runs require the reviewed workflow on the default branch and
successive scheduled successes. Manual runs cannot stand in for that evidence.
Operator canonical application/publication must be verified separately. Sprint
7.5 therefore remains In progress, and later interface gates are not bypassed.
