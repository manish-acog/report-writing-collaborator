# Design — `table` Variable Type and Persisted Values

## Purpose

For whoever adds `variable_type: "table"` to `variable_config` and
`report_renderer`, and persists a run's completed value map so a report
can be re-rendered into a different template format without re-running
extraction. For whoever changes `variable_config.py`, `report_renderer.py`,
and `report_orchestrator.py`.

## Why

Only `variable_type: "text"` exists today (`variable_config._VARIABLE_TYPES`
is `{"text": str}`). `study_variables.json`'s draft already names several
fields `variable_type: "table"` — a type that was never built. As a result,
a table today is the model free-writing Markdown pipe-syntax inside a
`text` field's `value: str`. Markdown templates render that fine; HTML
templates show literal pipes and dashes, because raw Markdown syntax isn't
HTML. `variable_config._VARIABLE_TYPES`'s own code comment already names
the intended fix — *"Extend this when a skill needs a new kind of field
(e.g. a table or an image reference); `report_renderer` then needs a
matching stringifier"* — never implemented.

Separately, `write_report()`'s completed value map lives only in process
memory between the call_group loop and `render()`, discarded once
rendering finishes — a deliberate choice in `general_report_writing.md`
when only one template format existed. Re-rendering the same run into a
second format currently means re-running the entire extraction. Both gaps
share one fix: values need to be captured as structured, format-agnostic
data, and turning that data into a specific format is `report_renderer`'s
job alone, not something committed at generation time.

## Shape

- **`variable_config.Table`** (new) — `headers: list[str]`,
  `rows: list[list[str]]`.
- **`variable_config._VARIABLE_TYPES`** — gains `"table": Table`, alongside
  the existing `"text": str`.
- **`report_renderer._stringify`** — becomes type- and template-aware: a
  Markdown pipe-table renderer and an HTML `<table>` renderer for `Table`
  values, the existing passthrough unchanged for `text`.
- **`report_orchestrator.write_report`** — after each `call_group`'s turn
  (not only once at the end), writes the running `values` dict to
  `.tasks/<task_id>/values.json` (directory established in
  `docs/task_run_artifacts.md`).
- **New: a render-only path** — a function (and a CLI flag exposing it)
  that loads an existing `values.json` and calls `render()` against a
  different `template_name`, without a model call.

## State

`.tasks/<task_id>/values.json` — the durable, format-agnostic record of
one extraction run's results. Lives under the task directory established
in the sibling doc, not the workspace.

## Scenarios

**A table field, both formats.** `deviations_table` returns
`{status: "found", value: {headers: [...], rows: [[...]]}, citations: [...]}`.
Rendering to `.md` emits a pipe table; rendering to `.html` emits a real
`<table>` — same source data, no regeneration.

**Re-rendering into a second format.** `write_report()` ran once
(extraction plus a `.md` render). A render-only call later reads that same
run's `values.json` and produces `.html` too — no model call, no
re-extraction.

**A field with no supporting evidence.** Unchanged from today: `table`
fields use the same `{status: "found" | "not_found"}` wrapper every
`variable_type` already uses; `not_found` still means no `value`, no
`citations`, same renderer fallback string.

## Decisions

### A structured `Table` type, not continued string-embedding

- **Options:** A — keep `table` fields as `text`, teach the skill to also
  emit an HTML-flavored variant somehow. B (chosen) — a real structured
  type; `report_renderer` decides the presentation per template.
- **Chose:** B.
- **Consequences:** one generation, every format — matches
  `general_report_writing.md`'s own stated intent for typed values,
  finally built. A doubles-the-generation-surface option (A) was never
  seriously on the table; it fails the same test document/table content
  splitting always fails — one source of truth, not two kept in sync by
  hand.

### Table citations are whole-field, not per-cell markers

- **Options:** A — allow `[[cite:N]]` markers inside individual cell
  strings, resolved per-cell during stringification, same syntax as prose.
  B (chosen) — no in-cell markers; a table's `citations` array covers the
  whole table, shown once (e.g. as a footnote/caption), the same way
  `citations` already backs a `text` field's whole `value`.
- **Chose:** B.
- **Consequences:** `check_citation_markers` (the `model_validator` from
  `docs/citation_marker_retry.md`) applies only to `text`-typed fields'
  `value: str` — a `table` field has no single prose string to run marker
  resolution over. Every table field this project currently names
  (`experimental_design_table`, `tissue_collection_organ_weights_table`,
  `deviations_table`) is transcribed wholesale from one contiguous source
  region — whole-table citation matches the actual evidence shape. Revisit
  only if a real table needs row-level citation granularity — nothing
  named today does.

### `values.json` is always written, unconditionally

- **Options:** A — write it only when a second render is explicitly
  requested. B (chosen) — every `write_report()` run writes it, always.
- **Chose:** B.
- **Consequences:** no conditional path to test; the data's already fully
  built in memory at that point, the write is cheap. Simpler than deciding
  ahead of time whether a given run will ever need re-rendering.

### `values.json` is written incrementally, not only at the end

- **Options:** A (as first implemented) — one write, after the whole
  `call_group` loop finishes. B (chosen) — overwrite `values.json` with
  the running `values` dict after every `call_group`'s turn.
- **Chose:** B.
- **Consequences:** if a later `call_group` fails after retries exhaust
  (`docs/citation_marker_retry.md`), every field extracted before that
  point is still on disk, not lost with the in-memory `values` dict. Each
  write is a full overwrite of current state, not an append log — cheap,
  and `values.json` never needs reconciling from partial fragments. Not a
  resume mechanism — `write_report()` still always starts a fresh run;
  this only stops a late failure from discarding already-completed work.

### The render-only path is built now, not deferred

- **Options:** A — persist `values.json` in this pass, leave re-rendering
  from it as unbuilt future work. B (chosen) — build the minimal
  render-only function (and CLI flag) alongside persistence.
- **Chose:** B.
- **Consequences:** the actual motivating need — a second format without
  re-extraction — is usable immediately, not stored for a future pass that
  might not happen. `report_renderer.render()` was already documented as a
  pure function; this exposes that property, it doesn't add one.

## Not doing

- **Per-cell citation markers in tables** — rejected above; revisit only
  with a concrete need.
- **An `image` variable type** — named as a future case in
  `variable_config`'s own comment; out of scope here, no current field
  needs it.
- **A generic re-render HTTP endpoint or API surface** — the render-only
  path is a function plus a CLI flag; no service wrapping it here.

## Open questions

None blocking — both the type shape and the citation-granularity question
were resolved above against the fields that actually exist today.

## Implementation

`variable_config.Table` (`headers`/`rows`), `_VARIABLE_TYPES["table"]`, and
`_FIELD_DESCRIPTIONS` (per-type `citations`/`value` field descriptions --
table's omits marker language, text's unchanged). `check_citation_markers`
already guarded on `isinstance(value, str)`, so it no-ops for tables
without changes.

`report_renderer._render_field`/`_stringify` take `template_suffix`; a
`dict` value renders as a Markdown pipe table or an HTML `<table>`, with
every citation appended once after it (no per-cell markers to resolve).

`report_orchestrator.write_report` overwrites `values.json` in `task_dir`
after every `call_group`'s turn, not only once at the end -- a later
group failing after retries exhaust (`docs/citation_marker_retry.md`)
still leaves everything extracted so far on disk. New `rerender_task(
task_dir, workspace_root, skill_name=, template_name=)` reads it back and
renders with no model call. `cli/main.py` exposes `--rerender-task
<task_id>`, resolving `task_dir`/`workspace_root` from that task's
`task.json` (globbed under `.workspaces/*/.tasks/<task_id>/`); mutually
exclusive with `--file`/`--benchling-entry-id`. Regression test:
`test_write_report_persists_partial_values_before_a_later_group_fails`.
