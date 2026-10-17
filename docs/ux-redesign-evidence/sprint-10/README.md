# Sprint 10 — workspace and discovery

[PR #2](https://github.com/ashcx/sg-investing-v1/pull/2), stacked on Sprint 9.

Technical work and main-instance design inspection complete; human acceptance
remains pending. The user authorized building Sprints 10 and 11 sequentially,
with final product review after both as recorded in the Scrum plan.

- Four destinations with one active workspace, legacy routes, reload,
  Back/Forward, route-preserving skip link and keyboard/mobile navigation.
- Reusable search by ticker/name/ISIN, selection clearing, no stale identity on
  uncommitted text, coverage previews, progressive filters and reachable pagination.
- Semantic styles, readable light/dark forms, friendly terminology and contextual
  Data & methods. Unknown coverage/source metadata is explicitly labeled.
- Share links use available latest packs; exports retain produced snapshot metadata.

Checks: [routes](routes.txt), [full browser suite](browser.txt), [Sprint 9 regression
suite](result-regressions.txt), [static-site checks](static-site.txt). Module syntax
and whitespace checks pass. The unchanged engines retain Sprint 9's verified
baseline; Sprint 11 will rerun financial checks for its DCA extension.

The deterministic catalog has 1,051 entries to verify pagination beyond 1,000.
Search by known ISIN, unknown text, clear/reset, keyboard selection, and metadata
isolation pass. Form-label contrast measures 15.84:1. Reduced-motion preference
is exercised. The actual page was inspected at 1440/1280/768/390/320px with no
page-level horizontal overflow in the checked simulator workspace.

Design captures: [desktop](workspace-desktop.png), [320px](workspace-320.png),
[390px](workspace-390.png), [768px](workspace-768.png), [contextual methods](methods-desktop.png).
The screenshots use explicitly synthetic data. No market-return, deployment,
real-user usability, or broad cross-browser claim is made.

Run `tests/browser/sprint-10.cjs` against frontend/ served on port 4173 with an
installed Playwright module (or PLAYWRIGHT_MODULE set to it). Source tests and
fixed Sprint 9 pack inputs are in the repository. All external browser requests
are blocked by the deterministic test harness.
