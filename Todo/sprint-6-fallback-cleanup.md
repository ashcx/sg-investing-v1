# Sprint 6 — Remove misleading API/static fallbacks

## Goal

One honest computation mode, shown explicitly, with no silent demo
substitutions anywhere in the UI.

## Entry criteria

- [x] Sprint 4 exit criteria are all met: DCA computes fully in-browser.
- [x] Sprint 5 exit criteria are all met: portfolio reconstruction computes
      fully in-browser.

## Depends on

Sprints 4 and 5.

## Tasks

- [x] Add an explicit static/local-compute mode and show it in the UI.
- [x] Replace all runtime `/api` calls with local-engine calls when the API base
      is empty; retain the adapter only as an optional development/reference
      mode.
- [x] Fix comparison fallback behavior: a failed custom comparison must not
      silently render the checked-in QQQ/SMH/SOXX demo artifact.
- [x] Ensure a missing or stale pack produces a clear unavailable state with the
      requested security/date range, never a result from another request.
- [x] Keep native/SGD switching presentation-only and map directly to the
      result contract in both local and adapter modes.

## Exit criteria

- [x] Users can always tell which mode produced the visible results.
- [x] No code path renders a demo artifact in place of a failed request.
- [x] Missing/stale data always yields a clear unavailable state naming the
      requested security and date range.
