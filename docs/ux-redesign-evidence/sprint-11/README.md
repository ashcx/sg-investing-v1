# Sprint 11 — unified investment simulator

[PR #3](https://github.com/ashcx/sg-investing-v1/pull/3), stacked on
[Sprint 10 PR #2](https://github.com/ashcx/sg-investing-v1/pull/2).

Implementation and main-instance technical/design review are complete; human
product acceptance is pending. This increment is stacked on Sprint 10 PR #2.

One security/date/assumption setup now supports one-time and regular investing.
Initial lump sum, recurring amount and frequency remain separate. Initial money
is invested once on the first eligible date, in addition to that period's regular
contribution. Capital/shares and both XIRRs include the initial cash flow; the
recurring contribution count does not. Omitted/zero initial preserves old result
shape and methodology, while nonzero methodology records amount/date/version 1.1.

The paired Python/JS engine change and optional worker/adapter request field are
within the user-authorized DCA scope. No financial combination or XIRR calculation
was added to UI code. The one-time comparison handoff copies exact settings and
keeps edits independent; regular comparison is explicitly unavailable.

## Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Python normal suite | 227 passed, 8 opt-in smoke deselected | [pytest.txt](pytest.txt) |
| Independent hand-calculated cases | 9 Python cases passed | [independent-python.txt](independent-python.txt) |
| New JS/worker cases and full-result Python parity | Six cases plus invalid-input checks passed | [independent-browser-engine.txt](independent-browser-engine.txt) |
| Existing golden parity | 27/27 unchanged | [parity.txt](parity.txt) |
| Engine self-tests | 68 passed | [engine-selftest.txt](engine-selftest.txt) |
| Worker suite | 90 passed | [worker.txt](worker.txt) |
| Properties | 19 properties / 1473 cases, zero failures | [property.txt](property.txt) |
| Simulator browser suite | Passed | [browser.txt](browser.txt) |
| Prior result/export/share regressions | Passed, adapted for intentional shared simulator fields | [result-regressions.txt](result-regressions.txt) |
| Workspace/search regressions | Passed, including 1051 entries and contrast | [workspace-regressions.txt](workspace-regressions.txt) |
| Static paths/JSON | Passed; pack existence skipped because generated packs absent | [static-site.txt](static-site.txt) |
| Ruff on changed Python | Passed | [ruff-changed.txt](ruff-changed.txt) |

Independent expectations and derivations are in
`tests/fixtures/redesign/sprint-11-dca.json`. Canonical Python outputs are a
separate full-result parity reference, not the independent financial oracle.
Examples: fixed price 10 gives 1600 shares and 16000 capital/final value from
10000 initial + twelve 500 contributions; the FX case is independently derived
from dated exchange rates; initial-held shares receive cash/reinvested dividends.
Adapter, direct JS and worker mapping are verified. Original zero-initial fixtures
are unchanged. Financial inputs remain strings/Decimals.

## Design and behavior

Inspected actual Chrome pages at 1440/1280/768/390/320px. Checked one setup and
mode-retained amounts, assumption editor, supported date action, price-only chart
units/ticks/table, initial vs recurring disclosure, previous-result export,
invalid/unsupported requests, comparison copy and separately restored drafts.
Reload starts with empty results. Changes to hidden/inactive requests cannot
make old responses current. Mobile charts scroll within their container; page
bounds checks pass. Screen-reader/physical-device/human usability claims are
reserved for Sprint 14.

- [One-time desktop](one-time-desktop.png)
- [Regular investing desktop](regular-desktop.png)
- [Regular investing mobile](regular-mobile-390.png)
- [Mobile price chart and coverage](price-chart-mobile.png)
- [320px workspace](simulator-320.png)
- [390px workspace](simulator-390.png)

Fixed synthetic data is used throughout; captures do not claim market returns.
No merge, deployment, live-data refresh or full generated-pack integration was
performed. Existing unrelated Ruff findings are documented in Sprint 9; all
changed Python files pass. CI now runs the engine and initial-lump worker checks.

Reproduce with declared Python dev dependencies and the Node scripts named above.
Serve frontend/ on port 4173 and run `tests/browser/sprint-11.cjs` with an installed
Playwright module (or PLAYWRIGHT_MODULE set). The browser harness blocks external
requests and uses an isolated profile; no private ledger data is read.
