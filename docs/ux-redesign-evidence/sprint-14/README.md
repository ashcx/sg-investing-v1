# Release candidate verification, 28 October 2026

The integrated local candidate passes the technical checks below. It has not
been deployed or merged. Sprint 14 remains In progress until five real
participant sessions and final Product Owner acceptance are recorded. Sprint 13
product acceptance also remains open; its technical gates and PR are complete.
The user explicitly authorized continued technical work between sprint PRs.

## Reproduce the checks

Run the offline suites from the repository root:

```sh
python -m pytest -m "not smoke"
node frontend/engine/selftest.mjs
node frontend/engine/parity/parity.mjs
node frontend/engine/property/property.mjs
node frontend/engine/worker-selftest.mjs
node frontend/engine/ledger-editor-selftest.mjs
node frontend/engine/compare-window-selftest.mjs
node frontend/engine/compare-result-selftest.mjs
node frontend/engine/compare-ui-selftest.mjs
node frontend/engine/compare-pipeline-selftest.mjs
PYTHONPATH=src python scripts/build_data_packs.py --security 6cfd001d-07dc-44d9-aff8-d6c99b0ee80b --years 2024,2025
node frontend/engine/dca-packs-integration.mjs
node frontend/engine/portfolio-packs-integration.mjs
python scripts/check_static_site.py
```

Python passes 291 tests, with 8 opt-in smoke tests deselected. Browser-engine
selftests pass 83/83; parity 29/29; worker checks 90/90; property checks 19
properties across 1,473 cases. Ledger and comparison suites pass. Pack
integration passes DCA 29/29 and portfolio 14/14. The scoped build uses real
canonical QQQ data for both required years, not a full-catalog rebuild. An
initial 2024-only build gave portfolio 12/14 due to missing 2025; the build
scope was corrected without changing assertions. Static-site, module syntax,
focused Ruff and whitespace checks pass.

Serve frontend on port 4173 and the synthetic review server on port 4174.
Set PLAYWRIGHT_MODULE to the installed Playwright package. Run:

```sh
node tests/browser/sprint-12.cjs
node tests/browser/sprint-13.cjs
node tests/browser/sprint-14.cjs
node tests/browser/native-zoom.cjs
node tests/browser/startup.cjs
```

The updated Sprint 11 browser script also passes on the integrated candidate.
Its comparison selector excludes Sprint 12's intentional empty slot, and its
output directory is configurable to preserve historical evidence.

## Inspect the actual candidate

The release browser probe independently checks QQQ final SGD value
13123.365925115971 against the Python golden, exported warning arrays, snapshot
and methodology, share-link round trips, original financial values after
edits, keyboard skip links, reduced motion, accessible control names and
320/390/768/1280/1440px layouts. Label contrast minima are 9.65:1 in Simulator
and 15.84:1 in the other destinations. It checks 200% CSS zoom separately from
the native browser zoom script. Native Chrome settings select 200%, and the
probe verifies DPR >= 1.9 and no horizontal page overflow in all four views.
Captures include generated-data output, published Tier-2 output and native zoom.

The candidate uses real generated QQQ packs and read-only published GRPN/R2
JSON. R2 JSON is proxied through the test route using the production Pages
Origin and a test response CORS header; this is labeled test transport, not
proof of localhost being an allowed production origin. Financial calculations
still run in the candidate Web Worker. A separate read-only published Pages
manifest check is baseline evidence only, not candidate deployment evidence.
No calculation API requests or browser exceptions were recorded. A cold-context
missing-pack request fails explicitly and succeeds after the network is restored.

## Interrogate the exit conditions

Main-instance sequential review only, as required by project instructions.
No independent or multi-model review is claimed. The named principles Prove It
Works and Sequence Work into Verifiable Units led to actual browser/IndexedDB/
pack probes and tested, ordered sprint PRs rather than checklist-only closure.

Three verified integration findings were repaired and their probes rerun:

- While typing a transaction, the status stayed Saved. The browser assertion
  expected /Unsaved/ and printed Saved in this browser. Input now immediately
  marks the draft unsaved; leaving the field saves valid data, including when
  the user types and reverts to the original value. Stored data remains intact.
- GRPN unconfirmed dividend detail showed Data quality OK. The published-data
  assertion expected /Review warnings/ and printed Data quality OK. Unknown
  dividend coverage is now included in quality warnings when dividends are
  enabled, excluding known accumulating/non-distributing policies. The probe
  passes and GRPN monetary values remain unchanged.

Dropped probe assumptions: the existing envelope uses snapshot/methodology,
not a provenance object; retained-output text legitimately changes its download
label to previous request; a pre-transaction valuation may legitimately show an
empty portfolio; and a 2024-only pack build cannot satisfy 2025 fixtures. These
were test/setup expectations, not verified application defects.

A held data-status response also reproduced blocked workspace initialization:
startup.cjs printed false != true. Route initialization now precedes optional
metadata loading, and the same probe passes while the response remains held.
Earlier intermittent startup timeouts are retained as observations, not falsely
attributed to a confirmed cause; four fresh-context instrumented starts also
completed normally. The held-response dependency is independently proven fixed.

No remaining verified technical finding against tested exits. Audit-map.md
maps F01–F19 to evidence. This is not a declaration of universal accessibility
or release acceptance. Five actual unfamiliar participants have not run the
protocol. The usability checker exits 2 with NOT VERIFIED on the blank template,
and its threshold tests pass on explicitly synthetic test records.

## Complete the human gates

Review the portfolio increment in PR #11 and record explicit Product Owner
acceptance. Use usability/protocol.md and observations-template.json for the
five real sessions. The required targets are at least 4/5 unaided completions
per task, median first-valid-result time below 60 seconds, and correct
identification of currency, amount, actual period and current/previous state.
Run scripts/evaluate_usability.py on actual anonymized observations. Keep the
release gate open on missing or failed outcomes. Product Owner then reviews
all evidence and accepts the release candidate. No sessions or acceptance may
be fabricated or inferred from the automated checks.
