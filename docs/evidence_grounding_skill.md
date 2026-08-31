# Design — Shared Evidence-Grounding Skill

## Purpose

Factors the found/not_found and citation-marker rules out of
`general-report-writing/SKILL.md` into their own loadable skill, so a future
second report-writing skill (the non-clinical study report) reuses them
instead of re-authoring the same rules. Supersedes
`docs/citation_marker_enforcement.md`'s instruction-side fix — that fix now
lands here, not in `general-report-writing/SKILL.md` in place.

## Why

`general-report-writing/SKILL.md`'s steps 2 through 6 aren't specific to
writing a title, summary, findings, or conclusion — they're rules about how
the `status`/`value`/`citations` schema and `[[cite:N]]` marker resolution
work, enforced by `report_renderer`/`variable_config` regardless of which
skill runs. The only genuinely skill-specific content is which skill to load
for structure and which fields to fill — the fields aren't even in
`SKILL.md`, they're in `variables.json`. A second report-writing skill needs
these exact same rules; left inline, that's a second copy silently able to
drift from the first, for content that was never skill-specific to begin
with.

## Shape

One new skill, `evidence-grounding`, loaded by any report-writing skill
alongside `workspace-summary` — independent of it, not layered on top of it:
one covers understanding the workspace, the other covers how to cite what
you found in it.

- **`src/report_writing_agent/skills/evidence-grounding/SKILL.md`** — the
  found/not_found rule, the `[[cite:N]]` marker convention (placement, every
  marker backed by a real citation, index reuse for repeated evidence,
  adjacent markers for any claim needing more than one citation — not just
  the multi-page case — and one `Citation` per page), and `inspect_image`
  usage guidance. All of it moved, not duplicated, from
  `general-report-writing/SKILL.md`.
- **`general-report-writing/SKILL.md`** — shrinks to: load
  `workspace-summary`, load `evidence-grounding`, fill the fields listed at
  the end of your instructions (unchanged — still supplied by the
  orchestrator from `variables.json`).

## State

None new.

## Scenarios

**`general-report-writing` runs today.** Its instructions now say to load
both `workspace-summary` and `evidence-grounding` before extracting
anything. Behavior is unchanged from a filled-field's perspective — the
rules didn't change, only where they're written.

**The future non-clinical study report skill.** Its `SKILL.md` loads
`workspace-summary` and `evidence-grounding` the same way, adds only what's
actually domain-specific (e.g. protocol-as-context-only for conclusions),
and never re-authors marker syntax or the found/not_found rule.

**A marker still malforms.** `report_renderer`'s leftover-`cite:` check
(from `docs/citation_marker_enforcement.md`) catches it regardless of which
skill produced the field — that enforcement lives in shared code, not a
skill, so it protects every report-writing skill equally, present or future.

## Decisions

### Factor into a loadable skill, not leave inline per report-skill

- **Options:** A — keep citation rules inline in each report-writing
  skill's own `SKILL.md`, duplicated. B (chosen) — one shared skill, loaded
  by reference, same pattern already used for `workspace-summary`.
- **Chose:** B.
- **Consequences:** one place to fix when a rule needs iterating (as it just
  did) instead of N skills to update in lockstep.

### `evidence-grounding` stays independent of `workspace-summary`, not merged into it

- **Options:** A — merge both into one "workspace-summary" skill covering
  structure and citations. B (chosen) — two separate skills, each loaded on
  its own.
- **Chose:** B.
- **Consequences:** `workspace-summary` still answers "what's in this
  workspace" on its own, unrelated to report generation; `evidence-grounding`
  is meaningful only in the context of filling a schema-constrained field.
  Merging them would tie two concerns that don't actually depend on each
  other.

## Not doing

- **Moving the field list or `variables.json` into the shared skill** —
  that's genuinely per-report-skill content, stays where it is.
- **Building the non-clinical study report skill now** — this doc only
  prepares the shared piece it will need; the skill itself isn't built here.

## Open questions

None blocking.

## Implementation

Implemented in `src/report_writing_agent/skills/evidence-grounding/SKILL.md`,
`src/report_writing_agent/skills/general-report-writing/SKILL.md`,
`src/report_writing_agent/report_orchestrator.py`, and
`report_renderer._render_field`. The orchestrator exposes both shared skills
to each bounded agent; the general report skill tells the model to load them;
the renderer rejects any `cite:` text left after valid marker resolution.
Tests cover shared-skill wiring, the skill boundary, and malformed markers.
