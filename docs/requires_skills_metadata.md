# Design — `requires_skills` Metadata for Report Skills

## Purpose

For whoever wires `invivo-report-writing`'s dependency on
`cayuse-protocol-understanding` and `benchling-notebook-understanding` into
`report_orchestrator.py`. For whoever changes `report_orchestrator.py` and
`invivo-report-writing/SKILL.md`'s frontmatter.

## Why

`invivo-report-writing/SKILL.md` already instructs the model to "load the
`cayuse-protocol-understanding` skill" and "the `benchling-notebook-
understanding` skill" — but nothing wires either into a `SkillToolset` the
model can actually call. `_build_bootstrap_agent` registers only
`structure_skill` (`workspace-summary`); `_build_bounded_agent` registers
only `grounding_skill` (`evidence-grounding`) — both hardcoded, singular,
shared by every report skill today. A `SkillToolset` only exposes the
skills passed to its constructor (`self._skills = {skill.name: skill for
skill in skills}` — no filesystem auto-discovery); a skill absent from that
list can't be listed, viewed, or loaded by the model no matter what any
instruction text says. The two domain-understanding skills are silently
unreachable — the SKILL.md instruction does nothing today.

`general-report-writing` and `academic-report` never needed a third skill,
so this gap went unbuilt. `invivo-report-writing` is the first report skill
that genuinely needs source-type-specific reading rules beyond the two
skills every report skill already shares.

## Shape

- **`invivo-report-writing/SKILL.md` frontmatter** — gains a `metadata:
  {requires_skills: [...]}` key, a plain list of skill directory names
  under `skills/`.
- **`report_orchestrator.write_report`** — after `skill =
  load_skill_from_dir(skill_dir)`, reads `skill.frontmatter.metadata.get(
  "requires_skills", [])` and loads each named skill the same way
  `structure_skill`/`grounding_skill` already are.
- **`_build_bootstrap_agent` / `_build_bounded_agent`** — each gains an
  `extra_skills: Sequence[Skill] = ()` parameter, appended to their
  existing `SkillToolset(skills=[...])` list.

## State

None new. `requires_skills` is read fresh from `SKILL.md` frontmatter on
every `write_report()` call, the same way `skill.instructions` already is.

## Scenarios

**`invivo-report-writing` runs.** `skill.frontmatter.metadata[
"requires_skills"]` is `["cayuse-protocol-understanding",
"benchling-notebook-understanding"]`. Both get loaded and appended to the
bootstrap agent's and every bounded extraction agent's `SkillToolset` —
the model can now actually call `list_skills`/`view_skill` for either, and
the existing SKILL.md instruction to load them does something.

**`general-report-writing` or `academic-report` runs.** Neither has a
`requires_skills` key in its frontmatter (`metadata` defaults to `{}`).
`extra_skill_names` is `[]`, `extra_skills` is `[]`, and both agent
builders' `SkillToolset` lists are unchanged from today — no observable
behavior change, no test to update for either.

**A typo'd or missing skill name.** `load_skill_from_dir(SKILLS_DIR /
name)` raises the same error it already raises for a bad `skill_name` CLI
argument — fails loud, at the start of the run, before any model call.
No new error-handling path; the existing failure mode already fits.

## Decisions

### `frontmatter.metadata`, not a new top-level frontmatter field

- **Options:** A — add `requires_skills` as a first-class field on ADK's
  `Frontmatter` model itself. B (chosen) — use the existing free-form
  `metadata: dict[str, Any]` field every `Frontmatter` already has
  (`extra="allow"` at the model level, plus `metadata` itself accepting
  arbitrary keys beyond the two ADK-reserved ones it validates).
- **Chose:** B.
- **Consequences:** A would mean vendoring or patching `google.adk.skills.
  models.Frontmatter` — out of scope and fragile against upstream updates.
  B needs no ADK change at all; `metadata` is already validated permissive
  (unknown keys pass through untouched), and reading it back is one
  `dict.get` in code this project already owns.

### Both bootstrap and extraction turns get `extra_skills`, not just extraction

- **Options:** A — wire `extra_skills` into `_build_bounded_agent` only,
  since field extraction is where Cayuse/Benchling reading rules matter
  most. B (chosen) — wire into both `_build_bootstrap_agent` and
  `_build_bounded_agent`.
- **Chose:** B.
- **Consequences:** the bootstrap turn builds the structural index
  (`list_sections`' title/heading_path/page range) every later call_group
  depends on (`docs/bootstrap_index_scaling.md`); Cayuse's own inconsistent
  heading levels and Benchling's inferred-heading quirk
  (both documented in their own SKILL.md) can affect how that index itself
  gets built, not only how a value gets extracted afterward. Symmetric
  wiring costs nothing when `extra_skills` is `[]` for every other report
  skill.

### No validation beyond what `load_skill_from_dir` already does

- **Options:** A — validate `requires_skills` is a list of strings
  matching real skill directory names before attempting to load any of
  them, raising a project-specific error. B (chosen) — pass each name
  straight to `load_skill_from_dir(SKILLS_DIR / name)` and let its own
  existing failure mode surface.
- **Chose:** B.
- **Consequences:** one fewer thing to build and test; a bad entry fails
  exactly as loud, at the same point in the run (before any model call),
  as a bad `--skill` CLI argument does today. Revisit only if
  `requires_skills` grows enough independent callers that a clearer,
  skill-specific error message earns its cost.

## Not doing

- **A generic skill dependency graph (skills requiring skills requiring
  skills).** `requires_skills` is read once, from the top-level report
  skill only; a listed skill's own frontmatter (if it had one) is not
  itself inspected for further requirements. No report skill needs
  transitive dependencies today.
- **Deduplicating `requires_skills` against `structure_skill`/
  `grounding_skill`.** A report skill listing `workspace-summary` or
  `evidence-grounding` in its own `requires_skills` would register it
  twice in the `SkillToolset` list; harmless (the toolset keys skills by
  name into a dict, so a duplicate simply overwrites itself), but not
  guarded against, since no current skill does this.

## Open questions

None blocking.

## Implementation

`invivo-report-writing/SKILL.md` frontmatter:

```yaml
metadata:
  requires_skills: [cayuse-protocol-understanding, benchling-notebook-understanding]
```

`report_orchestrator.py`:

```python
_REQUIRES_SKILLS_KEY = "requires_skills"

...

skill = load_skill_from_dir(skill_dir)
extra_skill_names = skill.frontmatter.metadata.get(_REQUIRES_SKILLS_KEY, [])
extra_skills = [load_skill_from_dir(SKILLS_DIR / name) for name in extra_skill_names]
```

`_build_bootstrap_agent(workspace_root, model, structure_skill,
extra_skills)` → `SkillToolset(skills=[structure_skill, *extra_skills])`.

`_build_bounded_agent(workspace_root, model, output_schema, instruction,
grounding_skill, extra_skills)` → `SkillToolset(skills=[grounding_skill,
*extra_skills])`.

Both call sites in `write_report()` pass `extra_skills` through.
`rerender_task()` is unchanged — it never calls a model.

Regression tests: `test_write_report_wires_requires_skills_into_bootstrap_
and_bounded_agents` (a skill with `requires_skills` set, asserting both
agent builders' `SkillToolset` include the extra skill by name) and
`test_write_report_defaults_to_no_extra_skills_when_unset` (a skill with no
`requires_skills` key, asserting `general-report-writing`/`academic-report`
behavior is unchanged).
