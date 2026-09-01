# Design — Task-Run Artifacts (`.tasks/`)

## Purpose

For whoever builds the `.tasks/` directory and updates `report_orchestrator`
and `cli/main.py` to write everything a `write_report()` run produces there,
instead of into the published workspace tree. Supersedes
`docs/extraction_session_persistence.md`'s "`sessions.db` sits beside
`manifest.json`" decision — not far enough. Also settles: no dedicated
tracing tool right now.

## Why

The workspace directory (`<publish_root>/<id>/<version>/`) is described
everywhere in this project as immutable and published — *"safe to cite
from indefinitely"* (`README.md`) — but two things already write into it
after publish: `sessions.db` (per the prior design) and the rendered
report (`cli/main.py`'s default `report_path = options.output or
workspace_dir / options.template`). Every downstream artifact of running
the agent against a workspace — session history, the extracted value map,
the rendered report — needs a home that isn't the workspace itself, both
so the workspace genuinely stays untouched forever, and so multiple task
runs against the same version don't collide or overwrite each other.

## Shape

- **`.workspaces/<id>/.tasks/<task_id>/`** (new, sibling of the numbered
  version directories and `.staging-*` directories, under the same
  `workspace_id`) — one directory per `write_report()` invocation.
  - `task.json` — the run's provenance: `workspace_id`, `workspace_version`,
    `skill_name`, `template_name`, `model`, `started_at`, `completed_at`.
  - `sessions.db` — moved here from `workspace_root/sessions.db`.
  - `values.json` — the persisted value map; shape and use covered in
    `docs/table_variable_type.md`, not repeated here.
  - the rendered report (`report.md` / `report.html`, whatever template ran).
- **`report_orchestrator.write_report`** — writes to `.tasks/<task_id>/`
  for everything it produces; `workspace_root` stays read-only throughout,
  as it already is for extraction itself.
- **`cli/main.py`** — default report output path changes from
  `workspace_dir / options.template` to `.tasks/<task_id>/<template_name>`;
  `--output` still overrides it explicitly, unchanged.

## State

`.tasks/<task_id>/` is the durable record of one run, kept indefinitely
until a retention policy is decided (open question, unchanged in kind from
the one already on record in `extraction_session_persistence.md`, now
scoped to the whole directory). The workspace directory itself gets zero
new state, ever, after publish — this doc's entire point.

## Scenarios

**Running twice against one workspace version, different templates.** Two
`task_id`s, two `.tasks/` subdirectories, two independent
`sessions.db`/`values.json`/reports. The workspace is untouched by either
run.

**Inspecting a run after the fact.** `task.json` says which workspace
version, skill, and model were used. `sessions.db` holds the full
turn-by-turn record — tool calls, skills invoked via `load_skill`, and
per-turn token usage, since ADK's own `Event.usage_metadata` already rides
along on every persisted event (confirmed by reading ADK's `Event`/
`StorageEvent` model — no new instrumentation needed for that). Nothing to
reconstruct from logs scattered elsewhere.

**Extending: a future HTTP API.** README already names this as separate,
not-yet-built work. When it exists, kicking off report generation can
return `task_id` immediately and let a client poll
`.tasks/<task_id>/task.json` for status — the same directory this
CLI-only doc establishes serves that later without a redesign.

## Decisions

### `.tasks/` lives under the workspace_id, not a separate top-level directory

- **Options:** A — top-level `.tasks/<task_id>/`, workspace linkage
  recorded only inside `task.json`. B (chosen) —
  `.workspaces/<id>/.tasks/<task_id>/`.
- **Chose:** B.
- **Consequences:** "which workspace did this task read" is answered by
  the directory structure itself, not only a field inside a file —
  `ls .workspaces/<id>/.tasks/` lists every run against any version of one
  workspace, for free.

### `sessions.db` and the rendered report both move out of the workspace tree

- **Options:** A — leave `sessions.db` where
  `extraction_session_persistence.md` put it (beside `manifest.json`), fix
  only the report output path. B (chosen) — move both into
  `.tasks/<task_id>/`, uniformly.
- **Chose:** B.
- **Consequences:** supersedes `extraction_session_persistence.md`'s
  State/Decisions sections regarding `sessions.db`'s location — that
  doc's reasoning for *why* a session DB exists at all is untouched, only
  where it lives changes.

### No dedicated tracing tool right now

- **Options:** A — wire OpenTelemetry plus a local exporter (e.g. Arize
  Phoenix) now, since ADK already emits spans internally
  (`_node_runner.py`'s `node_tracing.start_as_current_node_span`) and the
  integration is a handful of lines, the same pattern
  `google/adk/cli/api_server.py` already uses. B (chosen) — nothing new;
  `sessions.db`'s existing event history, which already carries
  `usage_metadata` per turn, is enough until a real need for visual trace
  exploration shows up.
- **Chose:** B.
- **Consequences:** no new dependency, no new local service. The escalation
  path stays cheap and named, not foreclosed: register a `TracerProvider`
  pointed at Phoenix whenever raw rows in `sessions.db` genuinely stop
  being enough — additive, not a redesign, because the spans are already
  being emitted regardless of whether anything collects them today.

## Not doing

- **A task-runner abstraction, queue, or status API** — this doc only
  creates the directory and its provenance file; no scheduling or
  orchestration beyond what `write_report()` already does synchronously.
- **Retention/pruning policy for `.tasks/`** — same shape of open question
  already on record for `sessions.db`, now scoped to the whole directory;
  not decided here.
- **Tracing tooling** — explicitly deferred, see Decisions.

## Open questions

- **Retention.** How long do `.tasks/<task_id>/` directories live? No
  current volume makes this urgent.

## Implementation

`write_report` now generates `task_id = uuid.uuid4().hex`, creates
`.tasks/<task_id>/` as a sibling of `workspace_root`'s version directory,
points `sessions.db` there, writes the rendered report to
`<task_id>/<template_name>`, and writes `task.json` (workspace_id,
workspace_version, skill_name, template_name, model, started_at,
completed_at). Returns `WriteReportResult(text, task_id, task_dir,
report_path)` instead of a bare string — `cli/main.py` and
`scripts/smoke_test_report.py` updated accordingly; the CLI's default
`report_path` is now `result.report_path`, `--output` still writes an
explicit second copy there, unchanged in behavior. `values.json` isn't
written yet — that's `docs/table_variable_type.md`'s scope, not repeated
here. Pointer added to `docs/extraction_session_persistence.md`'s
`sessions.db`-placement decision, noting it's superseded here.
