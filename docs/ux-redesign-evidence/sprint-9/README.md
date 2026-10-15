# Sprint 9 review evidence — 15 October 2026

Implementation and technical self-review are complete. Human product acceptance
is pending; Sprint 9 remains In progress and Sprint 10 has not started.

The increment repairs result ownership before the later navigation and visual
redesign. Each tool has explicit Calculate/Update, current/pending/previous/error
states, and a completed request summary. Analysis charts and exports belong to
that completed request. DCA selection and currency no longer mutate analysis.
FX captions use the actual native currency, redundant SGD FX is hidden, and
coverage separates requested/resolved dates, published price/FX dates, snapshot
metadata, and grouped original warnings. An unprovided date is labeled Not
published rather than inferred. The page starts with an honest empty result.

## Checks

| Check | Result | Evidence |
| --- | --- | --- |
| Python, excluding opt-in smoke | 218 passed, 8 deselected | [pytest.txt](pytest.txt) |
| Browser engine self-tests | 68 passed | [engine-selftest.txt](engine-selftest.txt) |
| Python/browser golden parity | 27/27 | [parity.txt](parity.txt) |
| Properties | 19 properties, 1,473 cases, zero failures | [property.txt](property.txt) |
| Worker suite | 90 passed | [worker.txt](worker.txt) |
| Deterministic real Chrome UI suite | Passed | [browser.txt](browser.txt) |
| Static paths and JSON | Passed; generated packs absent, existence check skipped | [static-site.txt](static-site.txt) |
| Module syntax and whitespace | Passed | `node --input-type=module --check < frontend/app.js`; `git diff --check` |
| Ruff baseline | 13 existing findings in unchanged Python files | [ruff.txt](ruff.txt) |
| Engine/source scope | No changes in `src/sg_investing/` or `frontend/engine/` | Git diff inspection |

Browser cases cover F01/F02/F03/F07/F08/F09/F15: fresh load, synthetic ES3
analysis → SMH DCA selection/calculation/currency, amount edit without auto-run,
invalid amount, unavailable analysis/DCA dates, edits during in-flight work,
previous JSON/share identity, foreign/SGD captions, coverage and warnings,
comparison and portfolio current/pending/invalid states, and no page exceptions.

Browser inputs are fixed in `tests/fixtures/redesign/sprint-9.json`, derived
from existing golden fixtures with synthetic ES3/SMH labels. They are UI
regressions, not claims about those securities' market returns. The tests use
real pack loading and the actual calculation worker, intercept fixture data
locally, and abort external requests. An isolated browser profile avoids using
private ledgers or the user's browser session. Full generated-pack integration
and production deployment are not claimed by this sprint.

To reproduce: serve `frontend/` locally on port 4173; provide an installed
Playwright module with `PLAYWRIGHT_MODULE` if it is not on the normal Node path,
then run `node tests/browser/sprint-9.cjs`. `SG_TEST_URL` and `CHROME_PATH` can
select another local server or Chrome executable. On Linux, install Playwright's
Chromium or set `CHROME_PATH`. Run Python with the declared `.[dev]` dependencies.

## Design inspection and self-review

Inspected the real page in headless Chrome at 1440px, 390px, and 320px. Fixed
coverage copy inheriting headline typography, mobile form width, and a warning
badge overflowing the result header. Automated bounds checks verify the analysis
output fits both mobile widths. The existing whole-site navigation, lighter form
labels, comparison mobile labeling, and chart interpretation are assigned to
Sprints 10–12 and are not claimed resolved here.

- [Empty desktop](empty-desktop.png)
- [ES3 result retained after SMH DCA](isolated-es3-smh-desktop.png)
- [Previous amount](previous-amount-desktop.png)
- [Invalid amount](invalid-amount-desktop.png)
- [Unavailable dates](unsupported-analysis-desktop.png)
- [SGD coverage](coverage-sgd-desktop.png)
- [Foreign-currency coverage](coverage-usd-desktop.png)
- [Previous result at 390px](previous-mobile-390.png)
- [Foreign result at 320px](coverage-usd-mobile-320.png)
- [Foreign result at 390px](coverage-usd-mobile-390.png)

Self-review confirmed edit invalidation precedes validation; older progress,
success, and error paths cannot commit after a new draft; DCA coverage survives
currency rerender; and share links retain requested dates and original amount.
User acceptance has not been inferred from tests or this self-review.
