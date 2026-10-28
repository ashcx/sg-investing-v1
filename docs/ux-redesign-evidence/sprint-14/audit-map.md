# Reconcile the October usability audit

This maps F01–F19 from `docs/ux-audit-2026-10-13/README.md` to the integrated
candidate. Automated and self-review evidence is separate from human usability.

| Finding | Current resolution and evidence |
| --- | --- |
| F01 mismatched initial request | Empty startup and completed-request ownership. Sprint 11 browser reload assertions and Sprint 14 real-pack export/share checks. |
| F02 initial amount edits | Previous-result notice on edits. Sprint 11 initial-amount/export checks and Sprint 14 retained result assertions. |
| F03 cross-tool chart overwrite | One shared simulator setup with per-mode results and independent comparison. Sprint 11 browser handoff/mode checks. |
| F04 unequal comparison periods | Explicit shared-date proposal and actual-period verification. Comparison window/result/controller/pipeline suites and Sprint 12 browser. |
| F05 faint labels | Scoped light-panel styles. Sprint 10 measured contrast and fresh browser viewport checks; Sprint 14 control-name checks. |
| F06 unlabeled mobile values | Comparison cards repeat metric/currency/period. Actual renderer assertions in compare-ui-selftest and Sprint 12 mobile capture. |
| F07 reversed FX caption | Currency-aware SGD-per-native explanations from Sprint 9. Existing Sprint 9 evidence; release browser validates real foreign-security output. |
| F08 stale successful outputs | Previous-request identity survives invalid edits and failed replacements. Sprint 11, Sprint 12 and Sprint 13 browser tests. |
| F09 weak coverage disclosure | Requested/actual dates and published coverage are separate. Sprint 10 coverage checks, Sprint 11 supported-date/error checks and Sprint 13 unavailable valuation. |
| F10 misleading price chart | One price currency, axes and table, with explicit price-not-wealth caption. Sprint 11 assertions and inspected mobile capture. |
| F11 unsafe ledger entry | Empty state, local restore/status, relevant labeled fields, stable row IDs, preview import, undo and recovery. Sprint 13 browser/store checks and captures. |
| F12 feature-first layout | Four task destinations and unified simulator. Sprint 10 routes and Sprint 11 modes. |
| F13 duplicate scenarios | Shared simulator assumptions and comparison snapshot. Sprint 11 state/handoff evidence. |
| F14 oversized discovery | Progressive filters, reset, full pagination and keyboard search. Fresh Sprint 10 browser passes 1,051 entries. |
| F15 warning interpretation | Comparison warnings are inspectable and result envelopes retain warning/provenance. The GRPN published-data probe reproduced unconfirmed dividend detail with an OK badge. The local result now adds that coverage warning to quality metadata when dividends are enabled; the browser regression requires Review warnings. Financial values are unchanged. |
| F16 jargon | Calculate/Update, Average cost, transaction-total explanation and price-history captions. Sprint 12 accepted copy cleanup and Sprint 13 captures. |
| F17 inconsistent styling | Shared workspace rules, scoped fields and mobile cards. Sprint 10 and release viewport evidence. |
| F18 general-only provenance link | Security-specific methods/coverage. Sprint 10 browser contextual methods check. |
| F19 stale security identity | Typed uncommitted selection clears metadata. Sprint 10 browser assertion. |

No absence of evidence is treated as a pass. Native Chrome 200% zoom is directly verified by native-zoom.cjs and recorded
in native-zoom.json. Final product review and real participant sessions remain
separate from the passing checks.
