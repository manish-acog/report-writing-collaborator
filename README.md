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

    uv run report-writing-agent --file path/to/file.pdf

Builds a workspace, runs `general-report-writing`, and writes the report
beside `manifest.json`. Requires model credentials in
`src/report_writing_agent/.env` — see `src/report_writing_agent/.env.example`.

An HTTP API and Docker packaging are planned, not yet built.
