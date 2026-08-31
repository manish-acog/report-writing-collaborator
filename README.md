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

1. **Build a workspace.** Every document and ELN entry is normalized to
   Markdown, structurally indexed, and published as one immutable,
   versioned workspace — the durable evidence base, safe to cite from
   indefinitely.
2. **Run a skill.** An agent reads the workspace through a skill's
   instructions, filling each requested field with either a grounded,
   cited value or an explicit "not found" — never a guess.
3. **Render the report.** Every citation resolves to a numbered
   reference linking back to its exact source and page.

A new template or a different model reruns steps 2 and 3 only; the
workspace built in step 1 never changes.

## Developing it

    uv sync
    uv run pytest
    uv run ruff check .
    uv run ty check

Module map and decisions: `AGENTS.md` and `docs/`.

An HTTP API and Docker packaging are planned, not yet built.
