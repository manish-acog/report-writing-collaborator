# Design — Citation Marker Enforcement

## Purpose

Two coupled fixes for a real failure seen in production output: the model
wrote `[[cite:1], [cite:2]]` (a comma-joined list inside one bracket pair)
instead of `[[cite:1]][[cite:2]]` (two adjacent, complete markers), which
`report_renderer` correctly left as literal text — but that left visibly
broken bracket syntax sitting in a shipped report. For whoever edits
`evidence-grounding/SKILL.md` and `report_renderer.py`.

## Why

Marker syntax lives inside free-text prose (`value: str`), so it can't be
schema-enforced the way `status`/`citations` are — there's no way to make
Pydantic reject a wrong bracket pattern inside an otherwise-valid string
without constraining the prose itself. The skill instruction is the only
lever that shapes what the model writes, and it currently only shows the
adjacent-marker example for the multi-page case (step 5) — nothing tells the
model what to do when one claim needs two *different* citations for any
other reason, which is exactly the case that broke. Fixing the instruction
reduces how often this happens; it can't guarantee it never does — so the
renderer needs to stop tolerating the failure mode silently.

## Shape

- **`evidence-grounding/SKILL.md`** — generalizes the adjacent-marker rule
  from "several pages" to "more than one citation, for any reason."
- **`report_renderer._render_field`** — after resolving every valid
  `[[cite:N]]` run, checks the result for a leftover `cite:` substring. If
  found, raises `ReportRenderError` naming the field — consistent with
  every other invalid-reference case already in this module (unknown
  source, unknown section, unknown parent, missing `{{references}}`).

## State

None new.

## Scenarios

**A claim needing two citations for any reason.** Two attention heads
described from two different sources — the model writes
`[[cite:1]][[cite:2]]`, adjacent and separate, matching the same rule that
already covered the multi-page case, now stated generally instead of
narrowly.

**A marker still malforms anyway.** The model writes something that still
doesn't match `[[cite:N]]` — the field's rendered text still contains
`cite:` after substitution, `report_renderer` raises `ReportRenderError`
naming the field. The report never ships with visible broken syntax in it;
the failure is loud and attributable, not a silent, embarrassing pass-through.

## Decisions

### Generalize the skill's adjacent-marker rule

- **Options:** A — leave the rule scoped to multi-page, add more special
  cases as they're discovered. B (chosen) — state it once, generally: any
  claim needing more than one citation uses adjacent, separate
  `[[cite:N]]` units, never combined into one bracket pair, regardless of
  why more than one is needed.
- **Chose:** B.
- **Consequences:** one rule instead of a growing list of scoped examples
  for each reason a claim might need multiple citations.

### Fail on leftover marker-shaped text, don't tolerate it

- **Options:** A — keep today's silent degrade-to-literal-text behavior. B
  (chosen) — treat any remaining `cite:` substring after resolution as a
  hard failure.
- **Chose:** B.
- **Consequences:** matches the strict-failure posture already applied to
  every other invalid-reference case in `report_renderer` — a report either
  ships fully resolved or doesn't ship. The check is broad on purpose: it
  doesn't need to anticipate every way a marker could malform (comma lists,
  single brackets, whatever shows up next) — "citation-shaped text
  survived unresolved" is true regardless of which specific variant caused
  it.

## Not doing

- **Loosening the marker regex to accept comma-joined lists or other
  variants** — considered and rejected. More accepted formats is more ways
  to get it subtly wrong, the same fragility deliberately avoided when a
  fixed integer marker was chosen over free-text citation parsing.

## Open questions

None blocking.

## Implementation

Implemented in `src/report_writing_collaborator/agent/skills/evidence-grounding/SKILL.md`
and `report_renderer._render_field`. The instruction moved to the shared
skill per `docs/evidence_grounding_skill.md`; the renderer check remains
shared enforcement for every report-writing skill.
