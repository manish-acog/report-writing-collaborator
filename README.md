# report-writing-collaborator

Turns a set of documents and ELN entries into an evidence-grounded,
citation-backed report, template-first — no free-form generation.

## Using it

    uv run report-writing-agent --file path/to/file.pdf

Builds a workspace, runs `general-report-writing`, and writes the report
beside `manifest.json`. Requires model credentials in
`src/report_writing_collaborator/agent/.env` — see
`src/report_writing_collaborator/agent/.env.example`.

The document/workspace layer underneath is also usable standalone, outside
this project entirely — see `src/canonical_workspace/README.md`.

## How it works

Two layers, cleanly separated. `canonical_workspace` turns your documents
and ELN entries into an immutable, versioned workspace — every source
normalized, structurally indexed, and individually citable, with no
report-specific logic in it at all. The agent and skills on top read that
workspace and produce the evidence-grounded report. The workspace layer is
the durable part, safe to build once and cite from for a long time; the
report layer can be rerun, retemplated, or extended without ever touching
it.

## Developing it

    uv sync
    uv run pytest
    uv run ruff check .
    uv run ty check

Module map and decisions: `AGENTS.md` and `docs/`.

An HTTP API and Docker packaging are planned, not yet built.
