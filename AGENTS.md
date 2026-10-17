# AGENTS.md — SG / Invest

Financial analytics engine (Python 3.11+, Polars/Parquet/Pydantic) with a
no-build static frontend (`frontend/`) deployed to GitHub Pages. Read
`README.md` and `product_design_document.md` before making changes.

## Todo system (mandatory)

All roadmap work is tracked in `TODO.md` (the roadmap) and the `Todo/` folder
(one file per sprint: `sprint-0-*.md` … `sprint-14-*.md`, including `sprint-7.5-*`). Any agent asked to
continue, pick up, or check project work MUST use this system:

- **Roadmap**: `TODO.md` holds the sprint table with statuses and the final
  "Done when" acceptance list. Keep the status column current
  (`Not started` / `In progress` / `Complete`).
- **Sprint files**: each `Todo/sprint-N-*.md` has fixed sections:
  Goal → Entry criteria → Depends on → Tasks → Exit criteria (→ Out of
  scope/References where present).
- **Gates**:
  1. Entry criteria must be fully ticked before starting any task of that
     sprint. They are satisfied by the exit criteria of the "Depends on"
     sprints — verify those files, do not assume.
  2. Tick tasks `- [ ]` → `- [x]` directly in the sprint file as they are
     completed.
  3. A sprint is complete only when every exit-criteria item is ticked; then
     update the roadmap status. If blocked, leave status `In progress` and
     record the blocker in the sprint file.
- **Order**: work one sprint and one task at a time in numeric order
  (7 → 7.5 → 8). All work runs sequentially in the main instance; do not
  spawn child agents or delegate implementation, tests, reviews, or documentation.
  Sprint 6 requires 4 and 5; Sprint 7 requires 4, 5, 6.
- **Redesign sequence**: Sprints 9–14 run sequentially after 7, 7.5, and 8.
  `Todo/redesign-scrum-plan.md` defines single-owner work, review, evidence,
  and Scrum events. The main instance owns all files and performs a separate
  self-review after implementation. Human product acceptance remains separate.
- **Sequencing detail**: `Todo/orchestration-plan.md` coordinates task order
  and contract freeze gates. Record each task's results, checks, evidence,
  blockers, and next action in its sprint file before moving to the next task.
  Sprint-file gates always win over the plan.
- **Sprint review and PR**: inspect the actual webpage design at desktop and
  mobile widths after each sprint; retain captures and findings. Open a PR in
  the configured GitHub repository with the sprint plan, changes, checks/results,
  and remaining gaps. Record the PR URL in the sprint log. Check in with the
  user when a material product, scope, or design decision is unclear.
- **Scope changes** are made by editing the sprint file itself, never as
  undocumented drift.

When asked to "continue the todo", "start the next sprint", or similar:
read `TODO.md`, find the eligible sprint, verify its entry criteria against
the depended-on sprint files, then work its Tasks list.

## Engineering conventions

- Python: `ruff` (line length 100), pytest (`python -m pytest`); no live
  network calls in the normal suite (provider/integration/smoke are marked
  and opt-in).
- All financial calculations stay deterministic and decimal-safe; never move
  calculation logic into the browser until the portable-engine sprints
  (Todo sprints 2–3) define how.
- Preserve result-envelope contracts and provenance/warning behavior in every
  change to `src/sg_investing/` or `frontend/`.
