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
  - `usage.json` — a slim, derived summary of the run's session: model,
    tool/skill call counts, and prompt/completion/cached token totals,
    computed from `sessions.db`'s own event history. Not a trace, not raw
    events — see the new Decision below.
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

### `usage.json` is a derived summary, not a reversal of "no tracing tool"

- **Options:** A — leave session stats unsurfaced; anyone who wants them
  queries `sessions.db` directly. B (chosen) — write a small, computed
  summary (`usage.json`) after the run, alongside the raw `sessions.db` it
  was derived from.
- **Chose:** B.
- **Consequences:** this is the fallback the tracing decision above already
  named — *"`sessions.db`'s existing event history... is enough until a
  real need for visual trace exploration shows up"* — being realized, not
  reopened. `usage.json` adds no instrumentation: every `Event` already
  carries `usage_metadata` (prompt/completion/cached token counts, every
  provider ADK supports), and tool/skill calls are already visible as
  `function_call` parts on existing events. This is aggregation of data
  already captured, computed once after `session_service.close()`, not a
  new capability. Kept separate from `task.json` — that file is what was
  *requested* (skill, template, model, workspace); `usage.json` is what
  *happened* (counts, tokens) — conflating the two blurs two different
  questions a reader might ask.

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

## Implementation (`usage.json`)

`_summarize_usage(session_service, session_id)` sums each event's
`usage_metadata` (`prompt_token_count`, `candidates_token_count` as
`completion_tokens`, `cached_content_token_count`, `total_token_count`)
and counts events whose content carries a `function_call` part
(`event.get_function_calls()`), then `write_report` writes the result to
`.tasks/<task_id>/usage.json`. `model` is left out of `usage.json` --
already in `task.json`, not worth the extra plumbing for a field the
reader can get one file over.

> **Superseded:** `_summarize_usage` summed one `session_id` because one
> `write_report()` run held one shared session
> (`docs/extraction_session_persistence.md`). `docs/per_group_session_isolation.md`
> replaces that with one session per `call_group` — `_summarize_usage` now
> sums across every session row for the task, not a single `session_id`.
> `usage.json`'s own shape (model, call counts, token totals) is unchanged,
> only how it's computed.

**Deviates from this doc's own "Next" wording.** It said fetch the
session *after* `session_service.close()`. Confirmed empirically instead:
a `get_session()` call issued after `close()` opens a fresh pooled
connection whose `aiosqlite` worker thread the already-disposed engine
never reclaims -- the call itself returns in milliseconds, but the
interpreter then sits alive for ~20s past a clean run's own exit (0.7s
baseline), waiting on that leaked non-daemon thread. Fetching the session
*before* `close()` -- functionally identical, since nothing else touches
the session in between -- avoids it entirely; timed at the same ~0.8s as
the no-reopen baseline. `write_report` now computes `usage.json` right
before its one and only `session_service.close()` call.
