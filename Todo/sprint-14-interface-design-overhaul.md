# Sprint 14 — Interface design overhaul

## Goal

Give SG / Invest a professional, deliberate visual identity for Singapore
investors reviewing historical investment outcomes. Overhaul the palette,
typography, spacing, component styling, information hierarchy, and interface
copy while preserving the useful high-level structure: Simulator, Compare
investments, My portfolio, and Data & methods. Desktop and mobile must feel
like the same product, with layouts suited to their widths.

User brief, 18 October 2026: the current design feels generic and AI-generated;
the palette and excessive textual UI are rejected. Remove redundant eyebrow
text and decorative explanations. Preserve task structure, not current styling.
Use the frontend-design skill to analyse the actual interface, propose concrete
improvements, implement the selected direction, and critique the result.

Status: **Not started**. This file records the requested planning amendment;
it does not authorize skipping earlier sprint gates or claim a completed review.

## Entry criteria

- [ ] Every Sprint 13 exit criterion is checked, including human review,
      ledger compatibility, transaction controls, mobile readability, evidence,
      and the sprint PR. Verify the actual file and depended-on exits.
- [ ] The integrated Sprints 10–13 candidate and its retained desktop/mobile
      evidence are available; distinguish it from any older deployed baseline.
- [ ] Read README.md, product_design_document.md, AGENTS.md, the redesign Scrum
      and coordination plans, and the frontend-design SKILL.md before work.

## Depends on

Sprint 13 only. Work runs sequentially in the main instance. Sprint 15 retains
the amended validation/design-review work and starts only after this
sprint's exit criteria are satisfied. Earlier open gates remain in force.

## Tasks

Timebox commitment: **S14-US01 + S14-US02 (6 SP)**. **S14-US03 (3 SP) is
stretch**, still required for exit. Re-estimate the four-workspace overhaul at
planning; if it exceeds capacity, record a recovery timebox within this sprint
rather than dropping views or bypassing verification. Complete and record each
task, checks, evidence, and separate self-review before advancing.

- [ ] **S14-US01 — Review the interface and propose a distinctive direction**
      (P1, 3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Given** the integrated website and the user's visual brief, **when** its
    actual desktop/mobile screens are reviewed, **then** concrete problems and
    a justified design direction are presented before production styling changes.
  - Tasks:
    - [ ] Apply `/Users/macbook/.codex/skills/frontend-design/SKILL.md`; inspect
          all four workspaces in empty, populated, loading, edited/previous,
          error and partial/unavailable states where applicable. Retain baseline
          captures at 320, 390, 768, 1280 and 1440px using non-private fixtures.
    - [ ] Inventory visual inconsistencies and text that does not help a user
          act or understand a result. Classify copy as remove, shorten, retain,
          or move into contextual details. Include redundant eyebrows, repeated
          headings, slogans, excessive metadata strings and repeated warnings.
    - [ ] Propose two concise visual directions with real SG / Invest content
          and comparable desktop/mobile mockups. Each includes 4–6 named hex
          colors with semantic roles, deliberate typefaces/roles and scale,
          spacing, alignment, component hierarchy, and ASCII layout wireframes.
          Keep the four-workspace structure; explain the recommendation.
    - [ ] Review proposals against this brief and the skill's generic-design
          tells. Revise anything that could be a stock generated finance page;
          record what changed and why. Do not substitute another default kit
          (cream/terracotta, acid-green dark UI, newspaper styling, uniform
          rounded cards or decorative gradients) for an intentional direction.
    - [ ] Present the concrete proposals to the Product Owner and record the
          selected direction or requested revisions. This is a material design
          decision; leave implementation pending until a direction is selected.
  - **Evidence:** baseline captures, copy inventory, proposal/token documents,
    desktop/mobile mockups, self-critique and actual Product Owner decision.

- [ ] **S14-US02 — Implement the cohesive visual and copy overhaul**
      (P1, 3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Given** a recorded selected direction, **when** the interface is restyled,
    **then** the four workspaces share a professional visual system with less
    redundant text, usable controls and intact financial meaning.
  - Tasks:
    - [ ] Replace the current palette and type treatment with selected tokens;
          apply consistent spacing, control sizes, surfaces, charts, tables,
          dialogs/details, focus, validation and state treatments. Keep CSS
          specificity controlled rather than layering conflicting overrides.
    - [ ] Remove redundant decorative eyebrows and all-caps section labels,
          repeated introductory text, promotional slogans, decorative numbering,
          and unnecessary arrows or metadata separators. Use concise sentence
          case and consistent action names; avoid single-word headline accents.
    - [ ] Make controls, results and useful financial context the primary
          content. Consolidate repeated explanations into contextual help or
          Data & methods. Group repeated warnings for readability without
          discarding distinct warnings or hiding material problems on failure.
    - [ ] Preserve metric names, currencies, units, actual dates, security
          identity, assumptions, coverage, provenance, exports and current versus
          previous result meaning. Essential context remains discoverable and
          accessible; text reduction must not create unexplained numbers/icons.
    - [ ] Apply the system across Simulator (both investing modes), comparison
          including partial results, portfolio including transaction entry, and
          Data & methods. Preserve routes, selections, handoffs, storage and
          existing workflows. Update visual documentation to the selected system.
    - [ ] Adapt hierarchy and density to mobile, tablet and desktop: intentional
          stacking, readable labeled metrics, reachable actions and contained
          wide data views. Do not achieve mobile fit by shrinking text or merely
          squeezing the desktop layout. Respect focus and reduced motion.
  - **Evidence:** implemented token/component/copy changes, per-view state
    captures, regression results and a separate self-review of the full system.

- [ ] **S14-US03 — Critique and verify the integrated visual result**
      (P1, 3 SP; owner: main instance; review: subsequent main-instance self-review).
  - **Given** the implemented overhaul, **when** the actual website is inspected
    across widths and states, **then** remaining inconsistencies are corrected
    and the Product Owner can assess the result from concrete evidence.
  - Tasks:
    - [ ] Inspect actual rendered pages at 320, 390, 768, 1280 and 1440px;
          retain matched before/after captures for all four workspaces and
          relevant states. Verify 200% zoom, keyboard order/focus, accessible
          names, contrast, chart/table labels and no unintended page overflow.
    - [ ] Perform a separate visual self-critique against the user's brief and
          selected direction. Remove remaining nonfunctional ornament or copy;
          resolve inconsistent palette, typography, spacing and component states.
    - [ ] Run existing deterministic browser journeys and applicable static,
          Python, parity and worker checks. Change presentation expectations
          only where intended; preserve request/result identity, warnings,
          financial outputs and ledger data. Full release matrix stays in S15.
    - [ ] Present the integrated desktop/mobile outcome for human product review;
          record actual acceptance or revisions, remaining gaps and PR URL.
  - **Evidence:** viewport/state matrix, before/after images, checks and exact
    results, critique/repair log, and actual human review outcome.

## Exit criteria

- [ ] Human Product Owner reviews the outcome and evidence and accepts it or
      requests changes; record acceptance before progressing to Sprint 15.
- [ ] The reviewed visual direction and its palette/type/layout tokens are
      documented; the direction is implemented across all four workspaces.
- [ ] Redundant eyebrows and decorative/repeated UI text are removed; necessary
      financial labels, context and warnings remain accessible and intelligible.
- [ ] The current palette is replaced and desktop/mobile share a coherent visual
      identity, including empty, populated, loading, previous and failure states.
- [ ] Inspect the actual locally served website at desktop/mobile widths; all
      specified viewport, keyboard, zoom, contrast and label checks are recorded,
      and no reproduced blocking visual/accessibility defect remains.
- [ ] Relevant regressions pass; no engine, decimal, worker-protocol,
      result-envelope, route, storage, import/export or request-ownership drift.
- [ ] Retain proposals, decision, captures, self-review and check results under
      `docs/ux-redesign-evidence/sprint-14/`; no review or evidence is invented.
- [ ] Open a sprint PR in `ashcx/sg-investing-v1` with plan, changes, checks,
      evidence and remaining gaps; record its URL. A PR is not a deployment.

## Out of scope

New financial calculations, features, metrics, chart meanings, cloud ledger
sync, framework/build migration, or changing the four-workspace architecture.
Full release validation and task-based technical/design review remain in Sprint 15.
No production implementation, merge or deployment is requested by the roadmap
amendment. A later sprint execution follows all stated gates;
publication needs its own authorization and live verification.

## References

- [Frontend Design skill](/Users/macbook/.codex/skills/frontend-design/SKILL.md)
- [Roadmap](../TODO.md)
- [Redesign Scrum plan](redesign-scrum-plan.md)
- [Coordination plan](orchestration-plan.md)
- [Sprint 13 — Portfolio workflow](sprint-13-portfolio-workflow.md)
- [Sprint 15 — Release and usability](sprint-15-release-and-usability.md)

## Execution log

18 October 2026 — planning amendment only. User requested this design-overhaul
sprint and moving the existing validation/usability scope intact to Sprint 15.
Read the frontend-design skill and current sprint/coordination records. Recorded
brief, sequential tasks, proposal/decision gate, implementation boundaries and
required evidence. All entry, task and exit checkboxes remain unchecked; no
interface audit, selected palette, implementation or human acceptance is claimed.
Next action: retain earlier sprint gates and review this amended roadmap before
any execution. Main instance owns all work; no delegation.

Planning verification: PASS — Sprint 15 Tasks through Exit criteria exactly match
the original validation sprint after mechanical numbering/path substitutions.
PASS — local Markdown links in all amended planning files resolve; required
sprint sections, Not started status and unchecked entry/task/exit gates verified.
PASS — whitespace check. Separate self-review confirmed only planning files
changed by this amendment and existing unrelated local edits were preserved.
No runtime tests were needed for this documentation-only change.


18 October 2026 — preflight: user expressly requested seeing potential designs
now, before Sprint 7.5 recovery or S12–13 implementation. Early concept previews
are permitted for that decision only; production interface changes and checked
S14 task/entry gates remain blocked. Candidate directions: Research (plum,
side-by-side setup/result) and Focus (teal, workspace rail and horizontal setup).
Actual selection is pending; neither is recorded as human-accepted. Sprint 15's
five-person requirement has separately been removed by explicit user decision.

Early proposal checks: both Research and Focus previews rendered and inspected
at desktop/390px, with additional 320px overflow checks. PASS — carousel,
desktop/mobile preview controls, warning disclosures and no browser runtime
errors. Price chart uses the committed QQQ SGD series and saved result example;
no invented performance or production calculation is used in the preview.
Retained proposal source: [proposal source fragment](../docs/redesign-prototype/sprint-14-directions.html)
and [design plan](../docs/redesign-prototype/sprint-14-design-plan.md). Subsequent
selection feedback is recorded below.


18 October 2026 — Product Owner feedback on early proposals: the designs are
acceptable, visually sound, and the muted color is not a blocker. User requested
prioritizing technical work. Use the recommended Research direction as the
working implementation reference, with room to strengthen accent contrast/
saturation during the actual Sprint 14 review. This records permission to use
the proposed direction, not acceptance of an unseen integrated implementation.
Sprint entry gates remain unchanged; Sprint 7.5 recovery is still first.


Roadmap publication check, 18 October 2026: all local Markdown file links resolve,
Sprint 14/15 fixed sections exist and all implementation gates remain unchecked.
Accepted proposal source is retained under `docs/redesign-prototype/`; it is the
unchanged inline-visualization fragment, not a production page or a newly tested
standalone preview. Main-instance self-review confirms this PR changes planning
and retained concept artifacts only. Recovery implementation/evidence belongs
to PR #5. No interface sprint has started.


Roadmap-only draft PR: https://github.com/ashcx/sg-investing-v1/pull/6
This publishes the planning amendment and retained early proposal source;
it does not satisfy the Sprint 14 implementation PR or completion criteria.
Recovery PR #5 remains the prerequisite. Implementation PRs for Sprints 12–15
are still outstanding.


18 October 2026 — Product Owner explicitly selected **Research** in the design
proposal carousel. This confirms the working visual direction; slightly muted
colour remains a refinement. Technical Sprint 7.5 recovery still precedes
interface work, and this selection does not accept an unseen implementation.
