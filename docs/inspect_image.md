# Design — `inspect_image` Tool

## Purpose

Defines the fourth read-only workspace tool: interpreting one image asset via
a vision-capable model. For whoever wires it into `report_writing_agent/agent.py`
alongside `glob_workspace`/`grep_workspace`/`read_workspace_file`.

## Why

Attachment normalization made every supported document searchable text.
Images stay raw assets — the one content type the agent's text tools cannot
read at all. A skill needs to ask about a chart, figure, or scanned page
without the agent guessing from its filename.

## Shape

One tool, bound to the same `workspace_root` and path-safety check as the
existing three tools.

- **`inspect_image`** — sends one image plus an optional question to a
  vision-capable model, returns its answer.
  - exposes: `inspect_image(path, question=None) -> dict`
    - success: `{"status": "success", "description": str, "model": str}`
    - error: `{"status": "error", "error_message": str}` — bad path, missing
      file, unsupported format, or model-call failure
  - hands off: nothing persisted; the result returns directly to the calling
    turn

Model: the agent's own configured model (`REPORT_AGENT_MODEL`), unless a
separate vision model is set via an optional env override. Default path adds
no new required config.

## State

None. Consistent with the workspace's immutability — analysis results live in
task state or final output, never written back to the workspace.

## Scenarios

**Targeted question.** A skill asks `inspect_image("assets/src_x/fig2.png",
"what trend does this dose-response curve show?")`. Returns a grounded answer,
not a generic caption.

**Generic description.** Called with no `question` — returns a neutral
description; the skill decides what matters, same "specifics live in skills"
boundary as everything else.

**Bad path or unsupported format.** Same error-dict shape as
`read_workspace_file` today — the agent decides whether to retry, ask the
user, or mark the claim unresolved.

## Decisions

### Model source

- **Options:** A — always a separate, dedicated vision model. B (simplest) —
  always reuse the agent's own model. C — reuse the agent's model by default,
  overridable via env config for a distinct vision model.
- **Chose:** C.
- **Consequences:** zero new required config for the common case; one optional
  env var when a project wants a different vision model. The tool must fall
  back cleanly when it's unset.

### Optional question parameter

- **Options:** A — describe-only, no question. B (simplest useful) — optional
  `question`, defaulting to a neutral describe-this-image prompt.
- **Chose:** B.
- **Consequences:** one call can answer directly instead of the agent
  re-deriving an answer from a generic caption. Default prompt stays domain-
  neutral; anything specific comes from the skill.

### Failure shape

- **Options:** A — raise on failure. B (simplest, matches existing tools) —
  return an error dict.
- **Chose:** B.
- **Consequences:** all four tools share one failure convention; the agent
  handles every tool failure the same way.

## Not doing

- **Caching repeated calls on the same image** — no proven need yet.
- **Full-page rasterization or OCR** — an ingestion-side capability, not this
  tool's concern; `inspect_image` only sees assets already in
  `manifest.assets[]`.
- **Format transcoding** — unsupported formats return an error, not a
  conversion.
- **A model-selection registry** — one optional override is enough for one
  choice; no plugin system.

## Open questions

- Exact env var name for the optional vision-model override.
- Which extensions to accept — likely the same list `ElnNormalizer` already
  uses for asset detection, confirmed at implementation time.

## Next

Implement `inspect_image` in `report_writing_agent/agent.py`, add it to the
tool list, smoke-test against one real image in an existing workspace.
