# Design — Persistent, Shared Extraction Session

## Purpose

For whoever changes `report_orchestrator`'s `call_group` loop. Records the
decision to replace per-`call_group` `InMemoryRunner` isolation with one
shared, database-backed ADK session spanning every turn of a `write_report()`
run — removing redundant per-group workspace re-discovery, and producing a
durable, queryable transcript of how each field's value was produced.
Extends `general_report_writing.md`, whose own "Not doing" section named
this and deferred it: *"Multi-`call_group` session/Working-State
continuity... Applies when the non-clinical skill is built."* The 10-group,
61-variable non-clinical `study_variables.json` config is that skill.

> **Superseded (core decision):** one shared session spanning bootstrap
> and every `call_group` turn is replaced by
> `docs/per_group_session_isolation.md` — it hit a hard TPM rate-limit
> failure in production (~190k tokens accumulated by the 6th group).
> Sessions are now isolated per `call_group`, with prior groups' extracted
> values injected as static text instead of carried via shared history.
> The bootstrap turn itself is also eliminated there, replaced by a
> deterministic function. Kept here for history; the durable,
> queryable-transcript rationale (Why, `DatabaseSessionService` choice)
> still applies — it's the *sharing across groups* that's superseded, not
> persistence itself.

## Why

Every `call_group` today runs in its own isolated `InMemoryRunner`/session
(`_run_bounded_call_async`, `report_orchestrator.py:118-139`) — the model
re-discovers workspace structure, species, protocol identity from scratch on
each of 10 group calls, and nothing survives the process to show what
actually happened. Whoever's implementing or reviewing non-clinical report
quality needs two things: fewer redundant calls, and a way to inspect a
run's turn-by-turn transcript after the fact when a field's value or
citation looks wrong. Success: one `write_report()` run shares model context
across its bootstrap + 10 extraction turns, and that run's full transcript
is queryable afterward from a durable file — without adding crash-resume
machinery nobody asked for.

## Shape

- **`report_orchestrator.write_report`** — owns the `call_group` loop.
  Changes from "new `InMemoryRunner` per group" to "one
  `DatabaseSessionService` + one session, reused turn to turn."
  - exposes: `write_report(workspace_root, skill_name, template_name,
    model) -> str` — signature unchanged.
  - hands off: nothing new externally; internally, one `session_id` threads
    through the bootstrap turn and all 10 `call_group` turns.
- **New: a session-service constructor** (`report_orchestrator.py` or a
  sibling in `agent/`) — builds one `DatabaseSessionService` pointed at a
  fixed, workspace-relative path.
  - exposes: a function building the service and the run's session.
  - hands off: the shared service + `session_id` every `Runner` built during
    the run is constructed with.

> **Superseded:** `sessions.db`'s location (this State section, and the
> "`sessions.db` sits beside `manifest.json`" Decision below) is
> superseded by `docs/task_run_artifacts.md` — it now lives under
> `.tasks/<task_id>/`, not inside the workspace directory at all. Kept
> here for history; the reasoning for *why* a shared session DB exists is
> unchanged.

## State

New: `<workspace_dir>/sessions.db` (SQLite), sibling of `manifest.json`. One
session row per `write_report()` run, many event rows per session (one per
model turn/tool call) — ADK's own `DatabaseSessionService` schema, not
custom. Accumulates across repeated runs against the same workspace,
independent, non-overwriting. Owned by the workspace directory it sits
beside — deleted or moved with it, referenced from nowhere else. No resume
state: a crashed run leaves a readable partial session row; `write_report()`
never resumes one, always starts fresh.

## Scenarios

**Normal run.** `write_report()` opens (creating if absent) `sessions.db`
beside `manifest.json`, creates a new session row with a fresh
`session_id`, runs the bootstrap turn (`workspace-summary` only), then all
10 `call_group` turns against that same `session_id` and the same agent
name, each turn's events appended. After the last turn (`conclusions`),
renders and returns — `sessions.db` now holds the complete transcript for
that run.

**Rerunning with a different template or model.** README's existing "step
2/3 rerun" case: a second `write_report()` call against the same workspace
creates a second, independent session row in the same `sessions.db`. Both
transcripts persist side by side, distinguished by `session_id`; neither
overwrites the other.

**Debugging a wrong citation.** Someone opens `sessions.db` and reads the
event stream for a `session_id`, seeing exactly which `glob`/`grep`/`read`
calls and model turns produced a given field's value — not possible today,
where only the final rendered report survives a run.

## Decisions

### `DatabaseSessionService` over a shared `InMemorySessionService`

- **Options:** A (simplest) — one `InMemorySessionService` per
  `write_report()` call, shared across its own turns only; solves the
  redundancy problem, nothing survives the process. B (chosen) —
  `DatabaseSessionService` (SQLite), same in-run sharing, plus a durable
  transcript after the process exits.
- **Chose:** B — audit/inspection of extraction runs was the explicit
  driver; A doesn't deliver it.
- **Consequences:** new dependency (`sqlalchemy[asyncio]` + `aiosqlite` —
  `DatabaseSessionService` imports them under a guarded `try`/`except`,
  currently absent from `pyproject.toml`; the bare `sqlalchemy` package
  alone is not enough, its async engine needs `greenlet`, pulled in by the
  `[asyncio]` extra — confirmed by running `DatabaseSessionService`
  directly against a throwaway SQLite file). A file to account for beside
  every workspace. No resume logic — deliberately excluded (see Not doing);
  a crash leaves a readable partial row, nothing more.

### SQLite, not a network database

- **Options:** A (simplest, chosen) — a SQLite file via an async driver, one
  per workspace directory. B — Postgres/MySQL, against a shared backend
  nothing here currently has.
- **Chose:** A.
- **Consequences:** no new infrastructure to run or operate. No
  cross-process concurrent-writer support beyond SQLite's own — acceptable,
  since one `write_report()` run is the only writer at a time (its own turns
  are already sequential by design). Revisit only if multiple processes ever
  generate reports concurrently against one workspace.

### `sessions.db` sits beside `manifest.json`, not inside the hashed workspace tree

- **Options:** A — inside the immutable, hashed part of the workspace
  (alongside `normalized/`). B (chosen) — sibling of `manifest.json`,
  outside anything `WorkspaceBuilder` hashes or versions.
- **Chose:** B.
- **Consequences:** doesn't perturb the workspace's existing hash/version
  identity. Same category as the rendered report file the CLI already
  writes into `workspace_dir` by default (`cli/main.py:167`) — a derived
  artifact of running the agent against a workspace, not part of the
  evidence base itself.

  **Superseded by `docs/task_run_artifacts.md`**: `sessions.db` no longer
  sits beside `manifest.json` — it moved into `.tasks/<task_id>/`, alongside
  the rest of a run's artifacts. The reasoning above (outside anything
  `WorkspaceBuilder` hashes or versions) still holds; that doc just found
  `manifest.json`'s sibling wasn't far enough outside the workspace tree
  either.

### One session per `write_report()` run, never resumed or reused across runs

- **Options:** A (chosen) — a fresh `session_id` on every `write_report()`
  call. B — one long-lived `session_id` reused across every run against a
  workspace.
- **Chose:** A.
- **Consequences:** reruns with a different template/model don't tangle into
  one growing conversation the model has to make sense of; each run's
  transcript reads independently. `sessions.db` still accumulates one row
  per run over time — retention is unaddressed (see Open questions).

### Bootstrap turn's skill set isolated from the 10 extraction turns'

- **Options:** A — offer `workspace-summary` and `evidence-grounding` on
  every turn, rely on the model noticing (from shared session context) that
  it already explored the workspace. B (chosen) — turn 1 only offers
  `workspace-summary`; the 10 `call_group` turns only offer
  `evidence-grounding` plus workspace tools.
- **Chose:** B.
- **Consequences:** `workspace-summary` runs exactly once by construction,
  not because the model happened to infer it from context — the actual
  point of sharing the session (killing 10x redundant structural passes) is
  guaranteed, not merely likely.

### Test seam stays `_run_bounded_call`, no new mock point needed

- **Options:** A (chosen) — leave `tests/test_report_orchestrator.py`'s
  existing `patch.object(report_orchestrator, "_run_bounded_call",
  return_value=...)` as the only seam; let session construction run for
  real underneath it. B — give session construction its own mockable
  function so tests never touch a real DB file.
- **Chose:** A — confirmed, not assumed. `patch.object(..., return_value=…)`
  without `autospec=True` replaces the target with a `Mock` that ignores
  its real signature entirely — verified directly: a mock built this way
  accepts extra positional args a function gains later and still returns
  the fixed value. `_run_bounded_call` can grow `session_service`/
  `session_id` params without touching the existing test. Session
  construction itself running for real is cheap and consistent with this
  project's existing test style (`_make_workspace` already writes real
  files to `tmp_path`) — confirmed empirically: `DatabaseSessionService`
  against a throwaway SQLite file creates two independent session rows
  from two `create_session` calls, and `append_event` accumulates per
  session (2 events on one, 1 on the other) without cross-contamination.
- **Consequences:** no second mock point to maintain. A separate, new test
  is still needed — not for mocking, but because today's mocked test never
  exercises real session/event behavior at all; something has to assert
  the claims in this doc's Decisions and Scenarios (fresh session per run,
  event accumulation, independent rows on rerun) against the real
  `DatabaseSessionService`.

## Not doing

- **Crash-resume** — excluded per the stated driver (audit/inspection, not
  restart-survival). `write_report()` always starts a fresh session; a
  crashed run's partial row is readable, never resumed. Revisit only if a
  real restart-survival need appears — `agent_execution_over_adk.md`
  already named this exact trigger for crossing into persistence at all.
- **Multi-process / concurrent-writer handling** beyond SQLite's own
  guarantees — nothing today runs concurrent `write_report()` calls against
  one workspace.
- **`sessions.db` pruning or retention policy** — not designed here; the
  file grows unbounded across reruns.
- **Parallelizing `call_group` turns** — settled separately: the shared
  session makes turn order load-bearing by design; not reopened here.

## Open questions

- **Retention.** Does `sessions.db` need pruning/rotation eventually? Not
  blocking — no current volume makes this matter.
- **Overridable DB path.** Should it follow the `model`/`REPORT_AGENT_MODEL`
  pattern (param + env var override) — e.g. for tests, or pointing several
  workspaces at one shared audit DB? Leaning no (workspace-relative default
  only) absent a concrete need.

## Implementation

Implemented in `report_orchestrator.py` (`_build_session`, `_build_bootstrap_agent`,
`_run_bounded_call`/`_run_bounded_call_async` threading `session_service`/`session_id`),
`pyproject.toml` (`sqlalchemy[asyncio]`, `aiosqlite`), and the
`general-report-writing`/`academic-report` `SKILL.md` step 1 (structural pass
now happens once, in the bootstrap turn, referenced not re-run). New session
test: `test_build_session_creates_independent_rows_across_reruns`.
