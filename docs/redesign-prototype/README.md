# SG / Invest redesign wireframe

This folder contains a standalone, low-fidelity prototype for the proposed
navigation: **Simulate**, **Compare**, and **Portfolio**, with **Data & methods**
as a utility view. Open index.html directly in a browser. It has no build
step, external dependency, network request, or hosting setup.

The prototype demonstrates the request-first simulator, an explicit handoff
from Simulate to a shared Compare setup, an in-memory transaction dialog,
contextual help, browser hash navigation, and responsive layouts. The security
catalog is illustrative.

[Verification notes and screenshots](QA.md) record the planning review and
prototype checks. They are not production sprint completion evidence.

## Short task script

1. In **Simulate**, choose QQQ, enter an amount and start/end dates, then press
   **Preview result**. Confirm the preview says it is a request preview and that
   financial values and actual dates are not calculated.
2. Change the amount or switch to **Regular contributions**. Confirm the prior
   preview is labeled as a previous request. Enter an optional **Initial lump
   sum (SGD)** (default 0) as well as the recurring contribution; preview and
   confirm both amounts appear separately. Try the compare handoff while in
   regular mode; confirm it explains that Compare supports one-time investing
   and leaves the setup on Simulate. Switch to **One-time**, use **Compare with
   another investment**, and confirm the selected security, amount, dates, and
   dividend/tax assumptions are copied while the second security slot stays
   empty. Choose a second security and preview; actual dates and the common
   window should remain unresolved.
3. In **Portfolio**, add a buy with a security, quantity, date, total cash amount,
   and currency. Edit it, delete it, then choose **Undo last delete**. Try a cash
   deposit and confirm security and quantity fields are hidden.
4. Open **Data & methods**, then use browser Back and Forward. Repeat at 320px,
   390px, 768px, and 1280px widths; check that navigation and controls remain
   reachable and no page-level horizontal scrolling is needed.

## Limitations

- The engine and market data are not connected. Result metrics are explicitly
  marked not calculated, and actual dates and common comparison windows are
  unresolved.
- Catalog entries are illustrative. The prototype does not assert price-history
  coverage or return performance.
- Security selection uses a short native dropdown to keep this wireframe simple.
  Ticker/name/ISIN search, filters, and empty-query recovery are not prototyped;
  they remain explicit Sprint 10 implementation and acceptance requirements.
- Portfolio entries live in memory for the current page only. They are not
  saved, imported, exported, or used to calculate holdings, cash, cost basis,
  or gains.
- Date and amount checks validate local request fields only. They do not verify
  data availability or calculate an investment outcome.
- Compare supports one-time investments only. Regular contribution comparison
  is outside this prototype's scope; the handoff keeps that setup on Simulate.
- This is a flow and interaction wireframe, not a production frontend or a
  complete accessibility assessment.
