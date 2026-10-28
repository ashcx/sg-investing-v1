# Guided portfolio verification

Run `node tests/browser/sprint-12-server.mjs 4174`, then
`PLAYWRIGHT_MODULE=<installed-playwright-path> node tests/browser/sprint-13.cjs`.
This uses synthetic data and actual browser IndexedDB. No production ledger
is accessed. Run `node frontend/engine/ledger-editor-selftest.mjs` for parser,
field relevance, legacy envelope, fee/ID preservation and write-error checks.

Full results and the sequential interrogate verdict are recorded in
[the Sprint 13 execution log](../../../Todo/sprint-13-portfolio-workflow.md).
The deterministic portfolio contains S$1,000 deposit and a S$100 purchase of
ten shares with S$2.50 fees. Closing price S$13 yields S$130 holdings plus
S$897.50 cash, totaling S$1,027.50. Average cost is S$10.25; unrealised P/L
is S$27.50. The mobile capture shows each metric's label and currency.

Human product acceptance remains open. The next sprint may proceed technically
under the user's 28 October instruction. No live deployment is claimed.
