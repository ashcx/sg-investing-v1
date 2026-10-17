# SG / Invest — usability audit and redesign proposal

Audit date: 13 October 2026 (Singapore). Local source baseline: `6ab5ac2`.
Live site: <https://ashcx.github.io/sg-investing-v1/>.
Implementation backlog: [Sprint 9](../../Todo/sprint-9-user-experience-redesign.md).

Planning update, 13 October 2026: the original single-sprint proposal is now
split into [Scrum Sprints 9–14](../../Todo/redesign-scrum-plan.md), with individual
files and sequential main-instance execution. That plan supersedes the delivery schedule
below; the audit evidence remains unchanged. A separate
[low-fidelity prototype](../redesign-prototype/index.html) demonstrates the
proposed task flows without connecting to the financial engine.

Subsequent user amendment: regular investing includes an optional initial
lump sum plus DCA. Sprint 11 records the required compatible engine extension;
the earlier engine-unchanged proposal below is superseded only for this feature.

## Recommendation

Rebuild the website's information architecture and presentation around three
tasks: **simulate an investment, compare investments, and reconstruct a
portfolio**. Keep the existing Python and browser engines, decimal arithmetic,
worker protocol, data packs, and result envelopes.

The current site has a recognizable visual identity, but presents a marketing
page, security directory, four calculators, and methodology essay as one long
document. Repeated inputs, invisible state coupling, and inconsistent result
presentation make the user responsible for understanding the implementation.
Several problems affect the meaning of displayed results, not just appearance.
A cosmetic restyle would leave those problems in place.

This is an audit and proposed implementation plan. No application or engine code
was changed, and the redesign has not been implemented or deployed.

## Evidence and test scope

The review combined live Chrome interaction, screenshots, rendered-DOM
measurements, keyboard selection, local source inspection, and existing
deterministic test suites. Viewports inspected included 320×740, 390×844,
768×1024, 1280×900, 1440×1000, and the initial 1305×1118 desktop viewport.
These were desktop browser viewport overrides, not physical-device tests.

Live scenarios included QQQ analysis, ES3.SI price-only analysis, SMH DCA,
QQQ/SMH/SOXX comparison, and a comparison including VALL.SW. Invalid amounts,
inverted dates, unknown securities, empty catalog search, filtering, and DCA
dates outside coverage were exercised. A separate localhost origin was used
for synthetic portfolio edits, preserving the live site's stored ledger.

At the initial desktop viewport, the page measured about 7,014 pixels tall;
analysis began about 1,905 pixels down. At 390 pixels wide, the inspected state
measured about 12,688 pixels tall, with analysis beginning about 3,846 pixels
down. These measurements depend on result state and expanded content; they are
not universal constants. Navigation can jump over this content, but the content
and repeated forms still create a fragmented mental model.

### Existing automated checks rerun

| Check | Result |
| --- | --- |
| Python: `python -m pytest -m 'not smoke'` | 218 passed, 8 deselected |
| Browser-engine self-test | 68 passed, 0 failed |
| Python/browser golden parity | 27/27 passed |
| Property tests | 19 properties, 1,473 cases, 0 failures |
| Worker tests | 90 passed, 0 failed |
| Static-site integrity | Passed; generated pack existence checks skipped because local manifest is absent |

These validate the local calculation and static-asset baseline. They do not
validate the user journeys or certify the live deployment's entire dataset.
Normal live calculation checks initially returned no captured console errors.

### Limits

- Safari, Firefox, physical mobile devices, a screen reader, and actual 200%
  zoom were not tested in this audit.
- Download verification was attempted, but the browser download-event wait
  timed out. Exported file contents and clipboard-link round trips remain
  unverified; this is not evidence that the product's downloads are broken.
- The price-table toggle was verified locally: 253 rows and the expanded state
  appeared for the published QQQ example.
- Local stock-portfolio computation was not treated as a live-site failure:
  the local checkout has no generated pack manifest. A synthetic SGD cash-only
  portfolio successfully returned S$10,000 across zero stock holdings.
- There was no new independent audit of financial methodology or source-data
  correctness, nor a full network-failure/performance benchmark.
- The historic sprint exit checklists were reviewed. Their checked state does
  not override the regressions reproduced here, particularly the claim that
  stale results are impossible. New regression work is tracked in Sprint 9.

## Findings

P1 means fix before treating the redesigned interface as ready for release.
P2 means substantial friction or inconsistency to resolve during the redesign.
“Observed” means reproduced in the browser; source-only findings are identified.

| ID | Priority | Finding and evidence | Required change |
| --- | --- | --- | --- |
| F01 | P1 | **Initial inputs and result describe different requests.** Fresh form: 1 Jan–13 Oct 2026. Visible QQQ example: 2 Jan 2024–2 Jan 2025, S$13,157.34. An example badge is present, but the result sits beside the active form. Observed; [screenshot](01-default-input-result-mismatch.jpg). | Start with an honest empty state, or load an example's exact inputs and compute that request. |
| F02 | P1 | **Changing initial capital does not update the result.** After an ES3 run, changing S$10,000 to S$20,000 and leaving the field kept S$10,000 in the result, without a stale indication. Source confirms `#initial-amount` is absent from reactive listeners. Observed; [screenshot](09-cross-panel-and-stale-amount.jpg). | Use one explicit calculation contract and mark every edited request as pending update. |
| F03 | P1 | **DCA can overwrite another tool's chart.** Run ES3 analysis, then choose SMH in DCA. Analysis keeps the ES3 title and metrics while its chart changes to a USD series with 164 closes; ES3's own chart had 167 closes. `s7WireReactive` sends the DCA selection into the analysis chart loader. Observed and source-confirmed. | Each result owns its security, period, chart, currency view, and request identity. |
| F04 | P1 | **Comparison promises equal periods that are not equal.** With the same requested 2026 dates, QQQ returned +16.58% in SGD for 2 Jan–27 Aug. VALL returned +0.67%; a separate analysis confirmed 20–27 Aug. The comparison says all rows use the same date range and gives VALL an OK status. Observed; [screenshot](13-mismatched-comparison-periods.jpg). | Default to a disclosed common usable window; otherwise show each actual period and an explicit unequal-period warning. |
| F05 | P1 | **Light-form labels are nearly unreadable.** Compare, DCA, and Portfolio use label color `#c4cfda` on `#fffefa`, approximately 1.57:1 contrast, at 11px. Dark-theme rules leak into light panels. Observed and measured; [mobile comparison](06-mobile-comparison.jpg). | Use semantic surface/text tokens, scoped form styles, and readable label sizes. |
| F06 | P1 | **Mobile comparison removes the meaning of its numbers.** At 390px the column headers disappear. QQQ shows +17.80%, +16.58%, and S$11,658.16 without local labels identifying native return, SGD return, or ending value. Observed; [screenshot](06-mobile-comparison.jpg). | Mobile cards must repeat the label, unit, and period for every metric. |
| F07 | P1 | **FX caption is backwards and hard-coded to USD.** Values such as 1.3193→1.3655 represent SGD per USD, while the caption says “USD per SGD conversion lens.” The same USD caption remains on an SGD security's 1.0000→1.0000 result. Observed; `index.html:174`. | Write “1 USD = S$1.3193 at purchase; S$1.3655 at valuation,” using the actual native currency. Hide irrelevant FX duplication for SGD. |
| F08 | P1 | **Failed or invalid requests leave successful-looking old outputs.** A 2027 SMH DCA request reports unavailable coverage, while the previous S$4,896.55, eight contributions, +72.52% XIRR, and “no warnings” output remains. Invalid analysis amount also keeps the old result. Observed; [DCA error](07-dca-error-stale-result.jpg). | A previous result may remain only when prominently identified by its original inputs and labeled as previous. |
| F09 | P1 | **Requested dates exceed available history with weak explanation.** The default end date was 13 Oct; QQQ resolved to 27 Aug. Its four visible warnings concerned dividends, not the missing recent weeks. Header snapshot date was 31 Aug. Observed. | Distinguish snapshot date, latest usable security/FX date, requested dates, and actual dates. Give stale/truncated coverage a prominent notice. |
| F10 | P1 | **Chart invites misleading interpretation.** Raw USD and SGD price levels share one unlabeled scale, without date ticks, numeric ticks, or a useful chart title. Currency conversion mechanically separates the lines; it does not make their vertical gap a return attribution. Observed and source-confirmed in `renderSeries`. | Show one clearly labeled price currency at a time, with axes and an accessible table; any indexed comparison must explicitly say price performance. |
| F11 | P1 | **Portfolio entry lacks basic editing and guidance.** There is no per-row delete control. Adding a row silently inserts a BUY, a 2024 date, quantity 1, and cash 1,000. Cash-deposit entry still exposes security and quantity. Inputs have no associated labels/ARIA names for transaction type, date, quantity, cash, or currency. Observed in isolated testing and source-confirmed in `ledgerRowTemplate`. | Use a transaction form with relevant fields, stable row IDs, edit/delete/undo, and explicit labels. |
| F12 | P2 | **The page presents features before a task.** Six navigation destinations, repeated security pickers, and separate large sections require users to discover how the pieces connect. One-time analysis and DCA repeat the same setup concepts. Observed. | Put task selection first; combine the two investment patterns in one simulator. |
| F13 | P2 | **Scenario selection is represented twice.** A preset selector and three always-visible switches express the same choice. DCA has only switches; Compare has presets with slightly different names. Observed. | One concise assumptions summary, with an expandable custom editor shared across tools. |
| F14 | P2 | **Discovery is oversized and lacks recovery.** Six filters are always visible. Internal names such as “Sp500 Current” and “Sgx Active” appear as product labels. Empty searches offer no reset action. The catalog count extends to x≈1609 at a 1440px viewport and is clipped. Observed; [screenshot](12-catalog-clipped-count.jpg). Source also caps “Show more” at 1,000 while retaining the button when more matches exist. | Use compact search results, progressive filters, friendly names, visible reset, and bounded pagination without a dead-end button. |
| F15 | P2 | **Warnings are hard to interpret and act on.** Analysis collapses a warning count; DCA prints long concatenated sentences; comparison offers only WARNING/OK chips with no direct warning inspection. Observed. | A consistent coverage summary near the result, grouped details below, and a recovery action when one exists. |
| F16 | P2 | **Terminology requires decoding.** “Force refresh,” “replay,” “same lens,” “dividend bridge,” CCY, WAC, and XIRR mix implementation language, branding, and finance terminology. Observed. | Use Calculate, Update results, Compare investments, Dividend details, Currency, and Average cost, with inline definitions where needed. |
| F17 | P2 | **Visual hierarchy and styling vary by tool.** Analysis is dark with a large dashboard; Compare/DCA/Portfolio use light forms that retain dark inputs and faint labels. The comparison ticker input also looks like an unstyled browser input. Secondary text remains very small despite earlier size overrides. Observed. | One component system for fields, labels, cards, statuses, currency controls, spacing, and type. |
| F18 | P2 | **“View coverage & provenance” leads to general methodology.** The destination has conceptual cards, not actionable security coverage or source details. Observed. | Provide a real Data & methods view with security-specific coverage and retained provenance. |
| F19 | P2 | **Security identity can lag behind typed search.** Typing an unknown ticker clears the selection internally but leaves the previous security's exchange, domicile, and other metadata visible. Observed. | Clear or explicitly suspend selected-security details while the picker contains an uncommitted query. |

### Reproduction references for implementation

The source locations below are at baseline `6ab5ac2`:

- `frontend/app.js:343`: `selectSecurity` mirrors Analysis into DCA.
- `frontend/app.js:490`: raw mixed-currency `renderSeries`.
- `frontend/app.js:606`: analysis validation leaves prior output visible.
- `frontend/app.js:665`: comparison renders no actual periods and checks
  snapshot/methodology consistency without checking resolved date equality.
- `frontend/app.js:845`: DCA errors update form text without replacing output.
- `frontend/app.js:885`: ledger row template, missing row actions and labels.
- `frontend/app.js:1030`: initialization renders the example before applying
  unrelated current-date defaults.
- `frontend/app.js:1446`: defaults derive from today's date, not usable coverage.
- `frontend/app.js:1474` and `:1530`: DCA selection updates the analysis chart.
- `frontend/app.js:1518`: initial-amount change listener is missing.
- `frontend/styles.css:94`, `:129`, `:178`: global dark-form rules, light panel
  background, and hidden mobile comparison headers respectively.

## Proposed product structure

### Three destinations, with a small help/data utility

| Destination | User's question | Main interaction |
| --- | --- | --- |
| Investment simulator | What would my investment have become? | Choose a security, one-time or regular investing, amount, and dates. |
| Compare investments | How would these alternatives have performed under the same assumptions? | Add 2–6 securities to one shared setup and inspect results over a disclosed common window. |
| My portfolio | What do my recorded transactions add up to? | Add/import transactions, inspect holdings and cash, choose a valuation date. |
| Data & methods (utility) | Can I trust and interpret this result? | Read coverage, dates, sources, assumptions, and limitations in context. |

Make the simulator the default landing view. A short introductory sentence and
optional “Try an example” are enough; remove the large promotional hero and
decorative currency card from the working interface. Keep the SG / Invest
identity, warm background, dark text, and restrained lime accent.

Explore becomes a reusable **security search and browse panel**, available when
choosing a security. It is not a mandatory separate stage. Methodology becomes
contextual help plus the Data & methods destination, not an essay appended to
every calculator. Each main destination is a route/view, with active navigation,
working browser Back, reloadable URLs, and a skip-to-content link.

### Simulator journey

1. Search for a security by ticker, name, or ISIN. Results show exchange,
   currency, identity, usable history, and coverage status before selection.
2. Choose **One-time investment** or **Regular investing**. Retain the security,
   date range, and assumptions when switching modes, but keep the two amount
   fields distinct: initial capital versus contribution per period.
3. Enter the amount and dates. For regular investing, choose frequency. Offer
   YTD, 1 year, 5 years, and Max only when the available history supports them;
   label the actual coverage end explicitly.
4. Show a compact assumptions summary: for example, “Dividends reinvested after
   applicable withholding.” Expand **Adjust assumptions** for independent
   dividend/tax/reinvestment controls. Explain irrelevant controls for
   accumulating funds and disable dividend-dependent options when appropriate.
   Preserve uncertainty for securities whose distribution policy is unknown.
5. Press **Calculate**. After editing a completed setup, show **Update results**
   and a pending-changes indicator. Currency display and detail expansion are
   immediate presentation controls; financial input edits require calculation.
6. Read final value, money invested, and gain/loss first. Show total return and
   CAGR for one-time investing; contributions and money-weighted XIRR for
   regular investing. Put dividends, FX, and provenance in secondary details.
7. Use **Compare with another investment** to create a comparison with an
   explicit copy of the selected setup. Do not silently bind separate screens
   to one global mutable selection.

Choosing explicit calculation is a proposed scope change from Sprint 7.5's
automatic runs. It removes the current mixture of automatic computation and
“Force refresh,” and avoids background jobs while a user is still constructing
a request. Keep worker cancellation and response-identity protection.

### Result hierarchy and state contract

Order the result as: **answer → actual period/coverage → key metrics → chart →
dividend and FX details → assumptions and provenance → exports**.

Every visible result and chart must belong to the same immutable request and
security identity. Manage draft inputs separately from the last completed
request. Define explicit states: empty, editing, loading, ready, previous result
with pending changes, invalid, incomplete coverage, unavailable, and failed.

If a previous result remains after a failure, label it “Previous result — your
new request could not be calculated,” show its input summary, and prevent its
share/export actions from implying that it represents the current form.
Announce completion and errors without moving focus during ordinary editing.
An explicit Calculate action may move focus to the result heading.

Show requested and resolved dates separately when they differ materially.
“Previous trading day” is not a sufficient explanation for a result ending
several weeks early. Default to the latest usable security/FX coverage and
display the snapshot date as provenance rather than a universal freshness claim.

### Comparison journey

Carry a simulator setup into Compare, then add a second security. A direct visit
starts with two empty slots and one shared setup, not three arbitrary defaults.
Before calculation, show each security's usable history and the proposed common
window. If the requested window cannot be served equally, offer “Use common
available dates” or explicitly separate/exclude the unsupported entry.

The primary results compare SGD final value and return; native returns are
secondary. Every row/card includes its actual start/end dates and inspectable
coverage notes. Partial failures should identify the failed security and retain
usable alternatives with an honest comparison status. Never claim all inputs,
periods, or snapshots are equal unless equality was checked.

Mobile uses labeled cards, not a desktop row with its header removed. Initially
retain the existing one-time comparison capability; multi-security DCA
comparison is a separate future feature, not part of this redesign.

### Portfolio journey

Keep portfolio work separate from hypothetical simulation. A new user sees an
empty state with **Add transaction** and **Import ledger**, not an unexplained
pre-populated BUY. Existing saved transactions must restore without loss.

Add transaction opens a labeled form: type, date, and only the relevant fields.
Buy/sell exposes security, quantity, transaction cash amount, and currency.
Explain that cash is the transaction total, not a unit price. Cash deposits and
withdrawals omit security/quantity; dividends use their relevant cash/security
fields. Show a readable transaction list with Edit, Delete, and Undo, plus
visible save status. Keep the current engine's transaction semantics.

Use human labels such as Buy, Sell, Dividend, Cash deposit, Cash withdrawal,
Currency, and Average cost. Ledger management actions belong in a separate
menu; clearing a ledger needs a concrete recovery/confirmation design. Import
needs validation and a preview before replacing existing data. The valuation
date defaults to a disclosed usable date. On mobile, transaction entry is a
form/card, not a horizontally scrolling spreadsheet.

Do not add portfolio return, allocation, risk, or wealth-through-time claims
that the existing result contract cannot support. Preserve holdings, cash,
weighted-average cost, and realized/unrealized P&L reporting.

## Visual and interaction system

| Element | Proposed rule |
| --- | --- |
| Layout | Persistent compact navigation; one task per view; 1,200px approximate content maximum; form and result columns only when they fit comfortably. |
| Mobile | One column, compact setup summary, clear Edit inputs action, reachable result; collapse navigation before it becomes crowded. |
| Typography | Body/input text about 16px, labels 14px, secondary metadata at least 12px; numbers align consistently with tabular figures. |
| Color | One light workspace theme initially; scoped dark surfaces only where deliberately designed. Lime indicates primary action, not data trust or positive performance by itself. |
| Controls | Consistent labeled fields and currency selectors; approximately 44–48px primary touch targets as a product design target, not a claimed WCAG minimum. |
| Focus | Visible focus on search, amounts, switches, menus, tables, and result links; retain reduced-motion support. |
| Charts | Explicit title, dates, value-axis units, readable ticks, and table alternative. Native/SGD single-price-series toggle. Optional base-100 price comparison must be labeled as price performance. |
| Feedback | One primary action per setup; persistent pending/loading/error states; concise summaries with expandable details. |
| Copy | Plain task names and concrete financial terms; explain advanced metrics next to where they appear. |

Do not fabricate a daily investment-value or reinvested-total-return curve from
the current daily price artifact. A price chart is a price chart. If another
series is needed later, it must come from an engine-supported contract.

Normal text should meet at least 4.5:1 contrast; large text has a different
threshold. See [W3C contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
Validate narrow layouts and zoom using [W3C reflow guidance](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html).
Assess smaller controls and spacing against [W3C target-size guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html),
including its exceptions. This audit is not a full accessibility conformance assessment.

## Delivery order and effort

These are planning estimates for one experienced implementer, not a delivery
commitment. The authoritative task checklist and exit gates live in Sprint 9.

| Phase | Work | Estimate | Exit evidence |
| --- | --- | --- | --- |
| 1. Protect result meaning | Request/response ownership, stale states, equal-period checks, date/FX captions, contrast fixes; add focused browser regressions. | 2–3 days | F01–F10 cannot silently misrepresent a request. |
| 2. Freeze the flows | Desktop/mobile wireframes for the three destinations; agree state transitions, component tokens, copy, and old-link behavior. | 1–2 days | Every input and action has one clear role; design addresses all audit findings. |
| 3. Build the workspace | Routes, active/sticky navigation, reusable search/browse, coverage preview, accessible forms and status components. | 2–3 days | Core navigation/search works at all target widths; old links still open meaningful views. |
| 4. Replace analysis and DCA UI | One simulator, explicit Calculate/Update, progressive assumptions, consistent results, price chart and tables. | 2–4 days | One-time and regular-investing journeys pass without cross-panel mutations. |
| 5. Replace comparison UI | Explicit setup handoff, common-window handling, labeled mobile cards, inspectable warnings and partial failures. | 1–2 days | QQQ/VALL unequal-history regression passes. |
| 6. Replace portfolio UI | Guided transaction entry, edit/delete/undo, save status, import preview, restore/export compatibility. | 2–4 days | Existing ledgers survive; new users can enter and correct transactions on mobile. |
| 7. Release validation | Browser journeys, visual/keyboard/zoom checks, deterministic suites, live pack integration, and task-based usability sessions. | 2–3 days | Sprint 9 exit checklist and recorded deployed smoke checks pass. |

Total: approximately **12–21 working days**, depending on implementation and
review iteration. Keep one owner of the frontend integration at a time. Avoid
shipping half-migrated tools with incompatible state conventions.

## How to tell whether the redesign worked

Run short task sessions with five people unfamiliar with the current site.
This is proposed research, not completed research. Ask each person to:

1. Calculate a specified QQQ one-time investment and state its actual dates.
2. Switch to a specified monthly contribution scenario and explain its result.
3. Compare QQQ with VALL and identify why their usable histories differ.
4. Add and correct a sample portfolio transaction, then explain where it is saved.

Proposed targets: at least four of five complete each core task without coaching;
median time to first valid result under one minute; all participants can identify
currency, invested amount, actual period, and whether the visible result matches
their current inputs. Record completion, mistakes, and time directly before
deciding whether the targets were met. No production analytics service is
required to conduct this evaluation.

Release also requires zero reproduced P1 defects, no unlabeled mobile financial
values, no loss of existing ledgers, readable controls at 320px and zoom, and
unchanged engine parity. Passing backend tests alone is insufficient.

## Screenshot index

- [01: fresh form/example mismatch](01-default-input-result-mismatch.jpg)
- [02: desktop calculated analysis](02-analysis-desktop.jpg)
- [03: invalid amount with previous result](03-invalid-input-stale-result.jpg)
- [04: mobile hero and promotional card](04-mobile-home.jpg)
- [05: mobile navigation](05-mobile-menu.jpg)
- [06: faint form labels and unlabeled mobile comparison](06-mobile-comparison.jpg)
- [07: unsupported DCA dates and form error](07-dca-error-stale-result.jpg)
- [08: isolated synthetic portfolio editor](08-portfolio-desktop.jpg)
- [09: edited capital and unrelated chart in analysis](09-cross-panel-and-stale-amount.jpg)
- [10: 320px header/first-paint layout](10-mobile-320-header.jpg)
- [11: tablet header/first-paint layout](11-tablet-header.jpg)
- [12: clipped desktop catalog count](12-catalog-clipped-count.jpg)
- [13: comparison that claims identical periods](13-mismatched-comparison-periods.jpg)
