# Plan — README

## Purpose

Plans the root `README.md` before writing it — no README exists yet.
Follows `aganitha-project-setup`'s audience-sectioned template exactly; this
doc only settles what the project doesn't hand you for free: which commands
are real today, and what "running it" honestly means before an API exists.

## Two things to decide before writing it

### There's no Makefile yet

The standard template says "Developing it → `make install && make test`."
Neither target exists — there's no Makefile in this repo at all. Writing
`make test` into the README when it doesn't work is exactly the
docs-say-something-that-isn't-true problem `aganitha-preflight` exists to
catch.

- **Options:** A — write `make` commands anyway, aspirationally. B (chosen)
  — document the real, working commands (`uv sync`, `uv run pytest`,
  `uv run ruff check .`), note a Makefile as a natural next step, don't
  build one now since it wasn't asked for.
- **Chose:** B.

### "Running it" without a deployed service

The API + Docker layer discussed earlier is deliberately deferred — nothing
is deployed. But there's a real, already-working "see it run" story: `adk
web` (ADK's own interactive UI, already wired via `root_agent` in
`agent.py`) and `scripts/smoke_test_report.py` (build a workspace, generate
a report, print it). Both work today with zero additional infrastructure.

- **Options:** A — omit "Running it" since nothing is deployed (the template
  marks this section optional). B (chosen) — keep it, scoped to running the
  agent locally, not deploying a service.
- **Chose:** B. There genuinely is something to run; omitting the section
  would hide two real, working entry points a reader would otherwise have
  to find by reading `agent.py` and `scripts/` themselves.

## Content

```markdown
# report-writing-collaborator

Turns a set of documents and ELN entries into an evidence-grounded,
citation-backed report, template-first — no free-form generation.

## Using it

Build a canonical workspace from your sources, then hand it to a
report-writing skill:

    import report_writing_collaborator as rwc

    manifest = rwc.build_workspace(
        [rwc.FileSource(path=Path("protocol.pdf"), source_instance_id="source_01")],
        rwc.WorkspaceConfig(publish_root=Path("workspaces")),
    )

See `docs/document_input_preparation.md` for the full source/workspace model.

## Developing it

    uv sync
    uv run pytest
    uv run ruff check .
    uv run ty check

Module map and decisions: `AGENTS.md` and `docs/`.

## Running it

    uv run python scripts/smoke_test_report.py --pdf path/to/file.pdf

Builds a workspace, runs `general-report-writing`, saves and prints the
report. Requires model credentials in `src/report_writing_collaborator/agent/.env` — see
`src/report_writing_collaborator/agent/.env.example`.

For an interactive chat session with the agent instead of a scripted run:

    uv run adk web

An HTTP API and Docker packaging are planned, not yet built.
```

**Superseded by `docs/canonical_workspace_extraction.md`:** the code sample
above imports `report_writing_collaborator as rwc`. `build_workspace`,
`FileSource`, and `WorkspaceConfig` moved to `canonical_workspace`; the
shipped README uses `import canonical_workspace as cw` instead.

## Not doing

- **Makefile** — not requested this turn; the README documents real `uv`
  commands instead of commands that don't exist yet.
- **API/Docker usage instructions** — nothing to document; named as planned
  in the README itself so a reader isn't left wondering if it's forgotten.

## Next

Write `README.md` from the content above. Separately, worth noting but not
acted on here: `AGENTS.md` doesn't yet have the Map table
`aganitha-project-setup` calls for — a related gap, not this doc's scope.
