# Design — General Report-Writing Skill

## Purpose

Defines the first report-producing skill — `general-report-writing` — and the
deterministic infrastructure it depends on: a variable-config-driven output
schema, and a template renderer. For whoever implements the skill and the two
new generic modules. Paves the way for the non-clinical study report skill,
which reuses the same mechanism with a larger, domain-specific `variables.json`.

## Why

Free-form report generation can't be reliably cited, reviewed, or regenerated
one field at a time. A template-first approach — fixed placeholders, values
extracted under a schema, injected deterministically — makes every report
reviewable against its source evidence and its structure predictable in
advance. This skill proves that mechanism generically before the non-clinical
skill pays for real domain content on top of it.

## Shape

Four things, three of them new:

- **`general-report-writing` skill** — content only, no logic.
  - `SKILL.md` — instructions: load `workspace-summary` first for structural
    understanding, then extract each `variables.json` field under its schema.
  - `variables.json` — one `call_groups` entry (`title`, `executive_summary`,
    `key_findings`, `conclusion`), shaped identically to a multi-group config
    so scaling up later is additive, not a rewrite.
  - `templates/report.md`, `templates/report.html` — `{{variable}}`
    placeholders; the HTML template's CSS lives inline in the file.

- **`variable_config`** (new, generic, `src/report_writing_collaborator/`) —
  loads and validates a skill's `variables.json`; for one `call_group`, builds
  the Pydantic `output_schema` the agent call uses. Every field is typed by
  its declared `variable_type` and wrapped the same way regardless of type.
  - exposes: `build_output_schema(call_group, variable_defs) -> type[BaseModel]`
  - hands off: a schema class to the ADK orchestration driver

- **`report_renderer`** (new, generic, `src/report_writing_collaborator/`) —
  takes a completed value map, one template file, and the published workspace;
  produces final report text with enriched references. No model access; pure
  function.
  - exposes: `render(template_path, values, workspace_root) -> str`
  - hands off: nothing — this is the terminal step

- **ADK orchestration driver** (extends `report_writing_agent/`) — for each
  `call_group` in the loaded skill's `variables.json`, builds that call's
  schema via `variable_config`, runs one bounded `LlmAgent` invocation
  (workspace tools + that schema), collects the result. Once every group
  completes, hands the merged value map to `report_renderer`.
  - exposes: the existing `build_agent` surface, extended to drive N bounded
    calls instead of one
  - hands off: a completed value map to `report_renderer`; a rendered report
    to whatever called it

This puts the ADK-specific orchestration loop in `report_writing_agent/`
(alongside `agent.py`), and everything deterministic — schema construction,
rendering — in `src/report_writing_collaborator/`, testable without a model.

## State

No new persisted state. The value map lives in the orchestration run's own
memory between "all `call_groups` done" and "render" — never written back to
the workspace, same immutability rule as everything else here.

## Scenarios

**Write a report on this workspace.** User asks to turn a workspace into a
report. The agent's description-driven routing loads `workspace-summary`
first, building the structural picture, then loads `general-report-writing`.
The orchestration driver reads its `variables.json`, builds the schema for its
one `call_group`, runs one bounded call with the workspace tools plus that
schema. The model returns four fields, each `{status, value?, citations?}`.
The driver hands the completed map to `report_renderer` against
`templates/report.md` (the default when no format was requested). The result
is deterministic, injected text — no model involvement past extraction.

**A field with nothing to report.** `conclusion` has no supporting evidence in
the workspace. Its output is `{"status": "not_found"}` — no `value`, no
`citations`; the schema makes a value without evidence unrepresentable in the
found case, and doesn't require fabricating one in the not-found case. The
renderer substitutes a canonical fallback string for that placeholder, so the
template itself never needs conditional logic to handle "missing."

**Extending to a second format.** Someone adds `templates/report.pdf`-adjacent
tooling later. The renderer gains one more per-`variable_type` stringifier if
the new format renders types differently (e.g., a table needs different
markup); nothing about extraction, the schema, or the other templates changes.

## Decisions

### Reuse `workspace-summary` instead of duplicating its structural pass

- **Options:** A — `general-report-writing`'s instructions re-describe reading
  `manifest.json` and building the source tree. B (chosen) — its instructions
  say to load `workspace-summary` first and build on what it establishes.
- **Chose:** B.
- **Consequences:** one structural procedure, one place it can drift. A
  request that skips straight to report-writing still gets grounded structure
  first, because the skill's own instructions require it.

### Skill package is files, not prose

- **Options:** A — describe the template and fields inside `SKILL.md`'s body.
  B (chosen) — bundle `variables.json` and `templates/` as resource files
  `SKILL.md` references by path.
- **Chose:** B, matching the resource-bundling pattern (`references/`,
  `assets/`) already established for skill packages generally.
- **Consequences:** templates and field config are reviewable and editable on
  their own, without touching the routing/instructions text.

### Minimal generic field set, one `call_group`

- **Options:** A — build out the full multi-group batching machinery now,
  even though four fields don't need it. B (chosen) — one `call_group`, but
  the same `variables.json` shape a multi-group config would use.
- **Chose:** B.
- **Consequences:** no session/Working-State continuity design needed yet —
  genuinely out of scope until a skill with more than one group exists (the
  non-clinical report). Scaling up later adds groups; it doesn't change the
  shape.

### Field values are typed and status-wrapped, not bare strings

- **Options:** A — plain string values, with "not found" encoded as a
  sentinel string inside the value (the old system's convention). B (chosen)
  — `{status: "found" | "not_found", value?, citations?}`, `value` typed per
  `variable_type`.
- **Chose:** B.
- **Consequences:** "nothing found" and "found, empty" are no longer
  indistinguishable by convention — the schema makes the difference explicit
  and unrepresentable to get wrong.

### Citations are structured output, not parsed from prose

- **Options:** A — the model writes citations inline in prose text; a parser
  extracts them after the fact. B (chosen) — the model returns a structured
  `citations: [{source_id, section_id?, page?}]` list alongside prose,
  enforced by the field's schema.
- **Chose:** B.
- **Consequences:** enforcement is real — a response missing `citations` on a
  found field doesn't parse against the schema, so it can't silently succeed.
  No regex fragility against however the model chose to format an inline
  citation.

### Mandatory references are a renderer guarantee, not a skill-authored field

- **Options:** A — every skill's `variables.json` must remember to declare a
  `references` field. B (chosen) — the renderer mechanically unions and
  dedupes `citations` across every field and requires every template to
  contain a reserved `{{references}}` placeholder.
- **Chose:** B.
- **Consequences:** no skill can ship without references by omission — the
  mechanism enforces it, not per-skill discipline. The non-clinical skill
  inherits this for free later.

### Plain placeholder substitution, no template engine

- **Options:** A — Jinja2 or similar, with conditionals and loops. B (chosen)
  — regex `{{variable}}` substitution; typed values (table, image) are
  pre-stringified per template language by the renderer before substitution;
  not-found fields get a fixed fallback string instead of a conditionally
  omitted section.
- **Chose:** B.
- **Consequences:** templates stay flat placeholder maps, approachable to
  author without knowing a template language. Revisit only if a real need for
  conditional section inclusion (not just fallback text) appears.

### Injection stays deterministic code, not an agent tool — for now

- **Options:** A — expose rendering as a tool the agent calls itself. B
  (chosen) — a plain function the orchestration driver calls after the
  agent's run completes.
- **Chose:** B, per your call.
- **Consequences:** rendering can't be influenced by model behavior — same
  input always produces the same output. Tool-ifying it later is a possible
  extension, not a redesign, once there's a concrete reason an agent needs to
  trigger rendering mid-task.

### Deterministic modules stay ADK-agnostic

- **Options:** A — put schema-building and rendering inside
  `report_writing_agent/`, coupled to ADK types. B (chosen) — keep them in
  `src/report_writing_collaborator/`, testable without a model or ADK; only
  the orchestration loop that drives multiple bounded calls lives in the ADK
  wiring layer.
- **Chose:** B, consistent with the existing split between the generic
  ingestion package and the ADK-specific agent wiring.
- **Consequences:** schema construction and rendering get ordinary unit tests,
  no model or ADK runtime required.

## Not doing

- **Multi-`call_group` session/Working-State continuity** — already designed
  in principle (shared session, Working State over raw event replay, batch by
  evidence locality); not re-solved here because this skill's one group
  doesn't need it. Applies when the non-clinical skill is built.
- **A template engine with conditionals** — plain substitution plus a
  not-found fallback string covers every case this skill has today.
- **Rendering as an agent-callable tool** — explicitly deferred.
- **Output formats beyond Markdown and HTML** — no third format has a
  concrete need yet.
- **Citation format validation beyond schema typing** — `source_id` existing
  in the workspace isn't cross-checked here; that's the Verification module's
  job, unchanged.

## Open questions

None blocking.

## Next

Implement `variable_config` and `report_renderer` in
`src/report_writing_collaborator/`, extend the ADK orchestration driver to run
one bounded call per `call_group` and merge results, then author the
`general-report-writing` skill's `variables.json` and both templates.
Smoke-test end to end against one real workspace.
