# Copy cleanup — 20 October 2026

User brief: preserve the existing design; remove unnecessary text and make the
site simple, clean and easy to use. No new portfolio workflow or engine scope.

## Skill and design plan

Downloaded [frontend-design](https://agenticskills.io/skills/frontend-design)
from its linked upstream into `docs/skills/frontend-design/SKILL.md`, alongside
its license. Read in full. The skill prioritizes purposeful words, plain actions
and restraint; the user's preservation brief takes precedence over redesign.

Keep existing colors, fonts, layout and spacing system. Palette: navy #101b2d,
paper #f5f5f0, white #fffefb, lime #d9f36a, muted gray #4e5a6b. Space Grotesk for
headings, DM Sans for UI/body, DM Mono for dates and numeric context. Existing
left-aligned setup/result columns stay; mobile stacks them.

    [ Destination title ]
    [ Setup / actions ] [ Result / actual dates ]
                        [ Data details ▸ ]

Review against brief: changing fonts/palette or introducing a new hero would
contradict the user's preference. Preserve those choices; spend this pass on
removing slogans, duplicated instructions and always-visible technical detail.

Copy principles: one instruction per action; action-oriented empty states;
concise success messages; warn only when something needs attention. Keep metric
units/periods, errors, pending/previous ownership and all provenance available.
Put supporting methodology and repeated coverage detail in native disclosures.


## Verification and separate self-review

Actual Chrome review covers all four destinations on desktop and mobile,
one-time and regular outputs, keyboard-operated coverage/error disclosures,
partial failure and actual dates. `chrome-checks.json` records the observed
values, states and exact 390px/320px widths. No comparison/simulator overflow.
The retained desktop/mobile captures show the quieter pages and unchanged
visual identity. Synthetic fixtures are clearly labeled, not market claims.

Existing comparison controller, independent values/dates, common-window and
real pack→worker→card pipeline checks pass unchanged. Static paths, module
syntax and whitespace checks pass. No financial engine or result-envelope edit.

Self-review: removed routine reassurance but kept unequal-period, partial,
missing-source and calculation warnings. Original assumptions stay in previous
result notices; provenance is available through disclosures. Corrected an empty
status fallback so untouched forms show no extra status banner. DCA no-warning
reassurance was removed, while real warnings remain visible. Error details are
escaped and inspectable. No new test suite mirrors these copy-only edits.

The user accepted the original Sprint 12 increment before requesting this pass.
These follow-up edits are ready for review in PR #8; acceptance of unseen copy
changes is not claimed. No merge or deployment is part of this pass.
