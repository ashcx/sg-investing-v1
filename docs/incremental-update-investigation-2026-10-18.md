# Daily update failure investigation — 18 October 2026

Investigation only: no provider calls, canonical-data changes, workflow changes,
reruns, or deployment. GitHub metadata/logs were read remotely; local checks
used the existing store and fake providers. Dates below are UTC unless marked.

## What the run history establishes

The latest 80 repository runs include ten failed scheduled incremental runs
from 6–16 October and ten cancelled scheduled `Update market data` runs in
the same period. All twenty ran main commit
`6ab5ac2ab7fd3a87aaee96b85f59c8312f0181ee`, before the Sprint 9–11 changes.
The two updater workflows, incremental script, and Yahoo adapter have no
changes between that commit and the current checkout. This is not caused by
the redesign changes.

| Run | Evidence |
| --- | --- |
| [38823584870](https://github.com/ashcx/sg-investing-v1/actions/runs/38823584870) | Job 116725695447: 1,042 failed price downloads at 2026-10-15 23:37:22, including `YFRateLimitError('Too Many Requests. Rate limited. Try after a while.')`; runner shutdown signal at 2026-10-16 00:02:02, exit 143. Summary, collection, upload skipped. |
| [38654732151](https://github.com/ashcx/sg-investing-v1/actions/runs/38654732151) | Job 116161680222: 1,290 failed downloads at 2026-10-14 23:39:47, widespread rate limits; runner shutdown at 23:44:28. Summary, collection, upload skipped. |
| [37399995033](https://github.com/ashcx/sg-investing-v1/actions/runs/37399995033) | Job 112064804749: runner shutdown during updater on 6 October, before any completed summary. |
| [38935169303](https://github.com/ashcx/sg-investing-v1/actions/runs/38935169303) | Full refresh job 117088730853: updater starts 16 October 16:51:56; cancelled 22:52:05, approximately six hours later; tests/upload skipped. |
| [38979792218](https://github.com/ashcx/sg-investing-v1/actions/runs/38979792218) | Latest incremental job failed during update. Job-log download returns BlobNotFound; do not infer its detailed cause from earlier logs. |

GitHub reports no artifacts for runs 38823584870 and 38654732151. The exit-143
annotation confirms termination, not a Python traceback. The logs do not prove
why the runner was shut down. Memory pressure, infrastructure termination, and
other cancellation causes cannot be distinguished from this evidence. Likewise,
the six-hour full-refresh pattern is consistent with the normal job timeout,
but its fetched log says only that the operation was cancelled.

## Confirmed implementation and operational faults

1. **The price batch loses per-security fetch windows.**
   `scripts/update_incremental.py::_fetch_price_rows` takes the minimum start
   across every non-straggler security, then calls `get_prices_batch` once for
   all securities. Only after download does it filter each security's rows.
   A read-only plan of this checkout selects 3,172 securities: 3,168 batch
   securities and four without prices. M12.SI ends on 2013-03-07, so the
   batch start becomes **2013-01-21 for all 3,168 securities**. QQQ's intended
   start is 2026-07-13. An offline recording provider confirmed the actual
   batch arguments, without contacting Yahoo. A small reconciliation request
   therefore becomes a thirteen-year, whole-catalog download. A single
   `yfinance.download` invocation still makes requests for individual tickers.

2. **Change detection materializes the whole price history twice.**
   `run_incremental_update` chooses scan years using the earliest plan,
   including missing-history securities starting in 2000. `_scan_price_values`
   materializes all market rows in Python dictionaries, retaining the before
   dictionary while building the after dictionary. Local Parquet metadata
   counts **13,422,888 rows over 73 partitions** in that range. This is a
   substantial memory/time risk independent of Yahoo latency. It is a plausible
   contributor to runner failure, not proven OOM evidence.

3. **Other requests also defeat the bounded-tail intent.**
   `YahooFinanceProvider.get_dividends` accesses `ticker.dividends` and
   `get_corporate_actions` accesses `ticker.actions`, then filters dates
   locally. These use full-history accessors. Each call constructs a fresh
   ticker, so the steps do not share its history cache. Dividend backfill uses
   four workers and up to three immediate attempts per failing security,
   without delay/backoff. Corporate actions run for the entire selection.
   There is no shared request budget or rate-limit circuit breaker. Provider
   rate limiting is explicitly observed; the precise contribution of each
   stage to the remote termination is unknown.

4. **The legacy refresh remains scheduled daily.**
   `update-data.yml` runs at 12:30 UTC weekdays and the incremental job at
   21:00 UTC weekdays. This conflicts with the runbook's manual/quarterly
   reconciliation policy. The legacy path visits catalog membership entries
   serially and reads/rewrites shared market/year partitions per security.
   The full-refresh job in the table consumed six hours. Some sampled full
   and incremental runs overlap; they use separate runners, and shared Yahoo
   throttling between them is not established.

5. **Failures discard diagnostics; successful refreshes still need an operator.**
   Summary and artifact steps use the default success-only condition; the
   summary is written only at the end of the updater. A terminated run loses
   its uncommitted work and never reaches artifact collection. Even a green
   run deliberately does not commit or deploy: an operator must apply its
   one-day artifact. Every fresh runner therefore starts from committed data,
   not the preceding runner's progress. Most local stored histories end on
   27–28 August; that is checkout evidence, not a verification of live-site
   freshness. Making the workflow green alone will not provide automatic
   daily publication.

## Additional release gaps found

- `main()` returns zero even when the summary contains provider or pack-build
  errors. A future green badge could conceal an incomplete refresh.
- A clean CI checkout has no generated pack baseline. A scoped pack build
  without a previous manifest yields a filtered manifest, as the current
  tests explicitly permit. A partial pack artifact must not be represented
  as a complete merged deployment without restoring and checking its baseline.
- Dependencies have open lower bounds. Sampled runs installed different
  Polars/PyArrow versions. No observed failure establishes dependency drift
  as the cause; locking tested versions would improve reproducibility.
- Node action deprecation warnings are present, but checkout and installation
  succeeded. Those warnings are not the observed updater failure.
- The cron is 21:00 UTC weekdays, or 05:00 Singapore time Tuesday–Saturday.
  During US daylight saving time it is one hour after the US close; during
  standard time it is at the close. Data availability needs a publication
  buffer, rather than assuming that time always means data is final.

## Validation performed

- Whole-catalog `--dry-run`: successful, no network or writes. The tool uses
  host UTC (17 October at inspection), so its default end date differs from
  the user-facing Singapore investigation date. The offline batch probe
  explicitly used 18 October; the problematic start/count are unchanged.
- Recording-provider probe: 3,168 securities, actual shared start 2013-01-21,
  QQQ intended start 2026-07-13; no provider calls.
- Parquet metadata count only: 13,422,888 candidate rows; no attempt to
  reproduce a potentially memory-exhausting full production update.
- `python -m pytest tests/test_incremental_update.py tests/test_ingestion.py
  tests/test_storage_ingestion_completeness.py -o addopts='' -q`:
  **40 passed in 2.36 seconds** using `/tmp/sg-invest-s9-venv/bin/python`.
  These synthetic tests do not validate production scale, throttling, or
  runner memory. Existing incremental tests mostly use the per-security fake
  provider path and miss the shared-window batch fault.

## Sequential repair and acceptance plan

1. Make full reconciliation manual; keep one scheduled daily path. Add bounded
   runtime, stage logging, resource measurements, and always-attempted diagnostic
   uploads clearly separated from publishable validated data.
2. Group price requests by appropriate per-security date windows and bounded
   chunks; isolate stale/unavailable listings so they cannot widen healthy
   peers' requests. Compare only relevant partition/security/date projections,
   one bounded unit at a time. Add stale-peer and scale regressions.
3. Use bounded history queries for events, preserve missing-versus-confirmed-zero
   semantics, and add pacing, delayed bounded retries and a rate-limit circuit
   breaker. Preserve all corporate-action and dividend reconciliation coverage.
4. Define an explicit incomplete/failure policy for provider and pack failures;
   verify it with offline failures. Restore a compatible full pack baseline
   before scoped merges, or rebuild full packs in the publication stage.
5. Verify a small live canary, then a full-universe run with resource telemetry
   and retained diagnostics. Confirm the canonical update application and
   publication process separately, then require successive successful scheduled
   runs. No claim of restored daily operation until that evidence exists.

The immediate demonstrated defect is the unbounded shared fetch window, with
confirmed provider rate limiting and substantial avoidable memory pressure.
Changing the notification settings or merely increasing the timeout would not
repair these faults. Runner shutdown attribution remains open pending telemetry.
