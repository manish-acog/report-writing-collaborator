# Design — Extract `canonical_workspace`

## Purpose

First step of the package split discussed over the last several turns:
carve the workspace-building code out of `report_writing_collaborator` into
its own package, `canonical_workspace`. Scoped to this extraction only —
merging `report_writing_agent` into `report_writing_collaborator` (the
second half of that discussion) is deliberately not this doc's scope; it's
a separate, later step.

## Why

`report_writing_collaborator` currently holds two things that don't depend
on each other at all: workspace-building (`DocumentNormalizer`,
`StructureIndexer`, `WorkspaceBuilder`, `ElnNormalizer`) and report
rendering (`report_renderer.py`, `variable_config.py`). Confirmed by reading
the actual imports, not assumed: `report_renderer.py` and `variable_config.py`
import nothing from the workspace-building files — only their own sibling
`exceptions.py`. The two halves share a package today by accident of where
the code was first written, not because either needs the other.

## Shape

- **`canonical_workspace`** (new package, `src/canonical_workspace/`) —
  `document_normalizer.py`, `structure_indexer.py`, `workspace_builder.py`,
  `eln_normalizer.py`, moved as-is — nothing in their own cross-imports
  changes, since they already only import each other and their own
  exceptions.
- **`exceptions.py` splits** — it currently holds both workspace exceptions
  and rendering exceptions in one file. Ten move to `canonical_workspace`
  (`DocumentNormalizationError`, `UnsupportedDocumentTypeError`,
  `DocumentConversionError`, `DocumentParseError`, `StructureIndexingError`,
  `WorkspaceBuildError`, `ElnNormalizationError`, `ElnAuthenticationError`,
  `ElnFetchError`, `ElnParseError`). Two stay in `report_writing_collaborator`
  (`VariableConfigError`, `ReportRenderError`).
- **`report_writing_collaborator`** keeps `report_renderer.py` and
  `variable_config.py`, untouched — no import changes needed inside either
  file.
- **`report_writing_agent/cli/main.py`** is the only place needing a real
  code change: it imports `FileSource`, `ElnSource`, `WorkspaceConfig`,
  `build_workspace`, `WorkspaceManifest` — all move to `canonical_workspace`,
  so its import becomes `import canonical_workspace as cw` alongside the
  existing `report_writing_collaborator` rendering import it already needs
  for nothing today (it doesn't call `render`/`build_output_schema`
  directly — those are `report_orchestrator`'s job).
- **`report_orchestrator.py` needs no change** — confirmed from its actual
  imports: it only pulls `build_output_schema`, `load_variables_config`,
  `render`, `CallGroup` from `report_writing_collaborator`, nothing
  workspace-related. It receives an already-built `workspace_root: Path`
  from its caller; it never calls `build_workspace` itself.
- **`pyproject.toml`** — `[tool.uv.build-backend] module-name` gains
  `canonical_workspace` alongside the existing two entries.

## State

None new. This moves code, not behavior.

## Scenarios

**`cli/main.py`'s `_build_workspace`.** Today: `rwc.build_workspace([...],
rwc.WorkspaceConfig(...))`. After: `cw.build_workspace([...],
cw.WorkspaceConfig(...))` — same call, same arguments, new import name.

**A test importing `report_writing_collaborator.workspace_builder`.**
Moves to import `canonical_workspace.workspace_builder` instead — a rename
in the test's own imports, not a behavior change.

## Decisions

### Scope this to extraction only, defer the `report_writing_agent` merge

- **Options:** A — do both moves (extract `canonical_workspace` and merge
  `report_writing_agent` into `report_writing_collaborator`) in one pass.
  B (chosen) — extract `canonical_workspace` first, merge second, as two
  separate, independently verifiable changes.
- **Chose:** B, per "let's start with."
- **Consequences:** two smaller, reviewable diffs instead of one large one
  touching packaging, imports, and directory structure simultaneously.

### Split `exceptions.py` along the same line as everything else

- **Options:** A — leave one shared `exceptions.py`, import across the new
  package boundary for whichever half doesn't own a given exception. B
  (chosen) — split the file; each package owns only the exceptions that are
  actually its own failures.
- **Chose:** B.
- **Consequences:** no cross-package import needed just to raise an error —
  `canonical_workspace` doesn't need to import `report_writing_collaborator`
  at all after this, in either direction.

## Not doing

- **Merging `report_writing_agent` into `report_writing_collaborator`** —
  the second half of the earlier discussion; a separate, later step, not
  this one.
- **Renaming `report_writing_collaborator` itself** — out of scope here;
  it keeps its current name and contents (minus what moves out) until the
  merge step, if and when that happens.

## Open questions

None blocking.

## Next

Move the four workspace-building files and the ten workspace exceptions
into `src/canonical_workspace/`, write its `__init__.py`. Trim
`report_writing_collaborator/exceptions.py` and `__init__.py` to the
rendering-only exports. Update `cli/main.py`'s import. Update
`pyproject.toml`'s `module-name`. Move `test_document_normalizer.py`,
`test_structure_indexer.py`, `test_workspace_builder.py`,
`test_eln_normalizer.py` to test `canonical_workspace`; leave
`test_report_renderer.py`, `test_variable_config.py`,
`test_report_orchestrator.py`, `test_report_writing_agent.py`,
`test_report_cli.py` where they are. Full preflight after.

## Implementation

Implemented as specified. One correction against this doc's own premise:
`scripts/smoke_test_report.py` also imported `build_workspace`, `FileSource`,
`WorkspaceConfig` from `report_writing_collaborator` — not just
`cli/main.py` — so it got the same `cw.` rename. `_NORMALIZER_NAME` and
`_INDEXER_NAME` in `eln_normalizer.py`/`structure_indexer.py` (provenance
strings recorded in `manifest.json`) were updated to their real new module
path; `_PACKAGE_NAME` stayed `"report-writing-collaborator"` since that's
the distribution name `importlib.metadata.version()` looks up, unaffected
by which module the code lives in. Verified with a built wheel installed
into a clean venv outside the checkout: both packages import and the CLI
runs.
