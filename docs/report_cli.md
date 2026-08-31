# Design — Report CLI

## Purpose

Defines a real, ship-quality command that builds a workspace from arbitrary
inputs and writes a rendered report — distinct from `scripts/smoke_test_report.py`,
which stays a dev-only smoke test. For whoever implements
`src/report_writing_agent/cli/main.py`. Follows `aganitha-cli-writing`.

## Why

Every real entry point so far is either a Python function called from code
or a single-purpose test script. Nothing lets a person or another script
just point at some documents and ELN entries and get a report back without
writing Python. This is that command.

## Shape

One Typer app, one command — not a multi-group CLI. There's exactly one real
operation today (build, then generate); `aganitha-cli-writing`'s subcommand
structure is for a project with several operations, which this isn't yet.

- **`src/report_writing_agent/cli/main.py`** — thin handler: validate flags,
  build the source list, call `rwc.build_workspace` then
  `report_orchestrator.write_report`, format the result. No business logic
  beyond that — both calls already exist and are unchanged by this.
  - exposes: one command, wired via `[project.scripts]` in `pyproject.toml`
  - hands off: nothing new — same two functions every other entry point
    already calls

**Superseded by `docs/canonical_workspace_extraction.md`:** `build_workspace`
moved to `canonical_workspace`; the shipped CLI calls `cw.build_workspace`,
not `rwc.build_workspace`.

## State

Same as `scripts/smoke_test_report.py` already established: workspaces
publish to `.workspaces/` at the project root, one directory per
`workspace_id`/`workspace_version`, nothing auto-cleaned. The report is
written alongside `manifest.json` inside that workspace by default.

## Scenarios

**Multiple documents, no ELN.** `--file protocol.pdf --file appendix.docx`
builds a two-source workspace, runs the default skill and template, writes
the report inside the new workspace directory, prints its path.

**Mixed documents and ELN entries.** `--file protocol.pdf
--benchling-entry-id etr_123` builds both sources into one workspace,
same as the extended smoke test already does — this CLI generalizes that
to any count of either kind, not one PDF and one optional entry.

**Missing input.** Neither `--file` nor `--benchling-entry-id` given — usage
error to stderr, exit `2`, no prompt.

## Decisions

### Should do

- **Repeatable `--file` and `--benchling-entry-id`**, at least one of either
  required. Matches "any input(s)" — not capped at one document.
- **`--skill` / `--template` / `--model`**, same defaults as
  `report_orchestrator.write_report` already has.
- **`-o` / `--output`** to override where the rendered report is written,
  defaulting to inside the built workspace when omitted.
- **`--json`**, emitting `{"ok": true, "data": {"workspace_id",
  "workspace_version", "report_path"}}` — the standard shape, so this is
  scriptable by other tools and agents, not just humans.
- **`--version`**, wired to the package version.
- **`--no-color`**, plus automatic colour stripping when piped or
  `NO_COLOR` is set — cheap, standard, no reason to skip.
- **State-change output**: `✓ Workspace built: .workspaces/<id>/<version>`,
  then `✓ Report written: <path>`.
- **Help with a real `Examples:` block** — a files-only invocation and a
  mixed files-plus-ELN one, verified by actually running `--help`.
- **Errors**: plain language plus a suggested action on stderr for expected
  failures (bad path, missing credentials); short message + exit `1` for
  unexpected ones, full traceback only under `--debug`.
- **`rich`** for output — styled state-change lines (colour-coded `✓`/`✗`),
  and an indeterminate spinner (`rich.status`) while `write_report()` runs.
  Honest because it never claims a percentage — just "Generating report...".

### Shouldn't do — yet

- **Subcommand groups** (`report generate`, `workspace build`, ...) — one
  real operation exists; structure gets added when a second one does, not
  before.
- **Per-source `--role` tagging** — `source_role` already defaults to
  `None` everywhere in the pipeline; nothing requires it. Typer has no
  clean way to pair a repeatable `--role` with a specific `--file` without
  inventing a `path:role` syntax for a feature nobody's asked for yet.
- **`--dry-run`** — there's no meaningful preview of an LLM-generated
  report; a real dry-run would mean input-only validation (do the files
  exist, is the skill valid), which is a genuinely separate feature, not
  built here.
- **`--quiet`** — `--json` mode already suppresses non-essential output;
  a separate quiet-but-human-readable mode isn't a proven need yet.
- **`--no-input`** — nothing in this command ever prompts, so a flag to
  disable prompting would be a no-op. Add it only if an interactive path
  is ever introduced.
- **Real *incremental* progress reporting** — `write_report()` runs as one
  blocking call per `call_group` today, with no hook exposing how much of
  that call is done. The `rich` spinner above covers "still working,"
  which is honest; a progress bar implying known completion would not be,
  since nothing tracks it. Genuine incremental progress means changing
  `report_orchestrator` first; not attempted here.
- **Retry or backoff on model failures** — a failed call surfaces as an
  error; no resilience machinery added beyond what already exists.

## Not doing

Everything listed under "Shouldn't do — yet" above, plus: no changes to
`report_orchestrator.write_report` or `build_workspace` — this is strictly
a new caller, not a change to either.

## Open questions

None blocking.

## Next

Implement `src/report_writing_agent/cli/main.py`, add `rich` to
`pyproject.toml` dependencies, wire `[project.scripts]`, verify `--help`
at the command level shows the examples block correctly (run it, don't
assume the framework renders it as written).
