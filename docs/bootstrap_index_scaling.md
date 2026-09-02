# Design — Index-First Bootstrap and On-Demand Section Access

## Purpose

For whoever adds `list_sections`/`read_section` to `make_workspace_tools`,
reshapes the bootstrap turn's output, and updates
`general-report-writing`/`academic-report`'s routing to match. Fixes a
real cost/latency problem, not a hypothetical one: bootstrap's current
"read every source in full, inspect every image" pass gets re-billed as
input tokens on every one of a skill's `call_group` turns, because they
share one session (`docs/extraction_session_persistence.md`). At 10
`call_group`s (the non-clinical skill's actual shape,
`study_variables.json`), that's roughly a 10× repeat of the bootstrap
payload, not a 2× one-time cost.

## Why

Traced the mechanism directly, not assumed: `_get_contents`
(`google/adk/flows/llm_flows/contents.py:98-101`) builds every turn's
model input from the *entire* prior `session.events` history. Bootstrap
runs once, but its full tool-call output — every source read in full,
every image inspected — becomes part of what every subsequent
`call_group` turn re-sends as context, because that's how a shared session
works. This scales with `N` `call_group`s, unlike the workspace-discovery
redundancy the shared session was originally built to eliminate
(`docs/extraction_session_persistence.md`), which scaled with `N` *before*
that fix. Bigger, slower requests from a heavy bootstrap payload also
compound the failure mode `docs/model_call_reliability.md` addresses —
more time in flight is more exposure to a mid-request connection reset —
so shrinking bootstrap's payload and bounding individual request time are
complementary fixes for the same live incident, not competing ones.

## Shape

- **`make_workspace_tools`** (`agent.py`) — gains two tools, over data
  `structure_indexer.Section` already computes (`section_id`, `title`,
  `heading_path`, `start_line`/`end_line`, `source_pages` — nothing new to
  index):
  - `list_sections(source_id) -> dict` — a source's table of contents:
    `section_id`, `title`, `heading_path`, `source_pages` per section, no
    body text.
  - `read_section(source_id, section_id) -> dict` — one section's content,
    sliced from `document.md` by its recorded `start_line`/`end_line`.
  - `grep_workspace` — enriched to resolve and include `section_id`/
    `source_pages` on each match, so a grep result is enough to ground a
    citation without a separate lookup.
- **`report_orchestrator._BOOTSTRAP_PROMPT`** — reworded to ask for an
  index, not a full read: source tree plus, per section, enough detail to
  judge relevance (title, heading path, page range) — explicitly *not*
  full section text, explicitly *not* inspecting every image.
- **`general-report-writing/SKILL.md` and `academic-report/SKILL.md`**,
  step 1 — changes from *"rely on that context rather than re-deriving
  it"* to instructing the model to use the index plus
  `list_sections`/`read_section`/`grep_workspace` to fetch exactly what
  this call's fields need — context no longer contains full evidence by
  default.
- **`workspace-summary/SKILL.md`** — documents the two new tools as the
  preferred path for its own existing "narrow question" case (step 3
  already says to `grep_workspace` before reading whole files); its
  general-summary behavior is unchanged, see Decisions.

## State

None new. `list_sections`/`read_section` read `document.sections.json`/
`document.md`, both already published, immutable workspace artifacts.

## Scenarios

**Bootstrap turn.** Produces an index: source tree, per-section title/
heading path/page range/`section_id`. No full section bodies, no
`inspect_image` calls, in this pass.

**A `call_group` fetching evidence.** `experimental_design_table`'s turn
sees the index (inherited from the shared session), identifies the
relevant section by title/heading, calls `read_section(source_id,
section_id)` once, gets just that section's text — not the whole document.

**Two `call_group`s needing the same section.** `protocol_overview` (group
1) reads "Materials and Methods" via `read_section`. `drug_information`
(group 2) needs the same section — it's already in the shared session's
history from group 1's turn, so group 2 doesn't re-fetch it. Cost from
on-demand fetches scales with distinct sections actually used, and each
fetch is only repeated by the groups that come *after* it, not by every
group in the run — a much smaller total than one large bootstrap payload
repeated by all `N`.

**Standalone "summarize this workspace" request.** Not run through
`write_report()`'s bootstrap prompt at all — `workspace-summary`'s own
instructions still apply as they do today, full read and every-image
inspection included where warranted. Unaffected by this doc; see
Decisions.

## Decisions

### Reshape bootstrap via `_BOOTSTRAP_PROMPT`, not by rewriting `workspace-summary/SKILL.md`'s own instructions

- **Options:** A — rewrite `workspace-summary/SKILL.md`'s steps
  (including its "read every source" and "inspect every image" language)
  to always produce a lean index. B (chosen) — leave
  `workspace-summary/SKILL.md`'s own instructions as they are;
  `report_orchestrator._BOOTSTRAP_PROMPT` — a separate instruction layer,
  already distinct from the loaded skill's own text — explicitly overrides
  with the lean-index behavior for this one caller.
- **Chose:** B.
- **Consequences:** `workspace-summary` is a shared skill with a second,
  real caller this doc must not break — someone directly asking the agent
  to *"summarize, describe, report on, or answer a question about the
  source material"* (its own description) still wants the thorough
  treatment, not an index. Option A would silently regress that path.
  `_BOOTSTRAP_PROMPT` is already a separate control surface
  (`report_orchestrator.py:72-77`) specifically because it's used for
  exactly one caller — this is what it's for.

### New tools live in `make_workspace_tools`, not a separate module

- **Options:** A — a new tool-building function alongside
  `make_workspace_tools`. B (chosen) — extend the existing one.
- **Chose:** B.
- **Consequences:** every `call_group` and bootstrap agent already gets
  its tool list from one call site; no second wiring path to keep in sync.

### `read_workspace_pages` is deferred, not built now

- **Options:** A — build it alongside `list_sections`/`read_section` since
  it was proposed as part of the same batch. B (chosen) — `list_sections`
  plus `read_section` plus enriched `grep_workspace` cover every case
  named in this doc; drop page-driven fetching to Not Doing.
- **Chose:** B.
- **Consequences:** matches this project's consistent YAGNI discipline —
  no tool ships ahead of a concrete gap it closes. Revisit only if a real
  case shows section-level access isn't fine-grained enough.

## Not doing

- **`read_workspace_pages`** — deferred; see Decisions.
- **Changing `workspace-summary/SKILL.md`'s general-summary or
  narrow-question behavior** — out of scope; this doc only adds tool
  documentation there, doesn't change when each mode applies.
- **A prompt-injection/trust-boundary rule for source content** — real,
  but a different root cause; covered separately in
  `docs/source_content_trust_boundary.md`, not folded in here even though
  it touches an adjacent skill file.

## Open questions

None blocking — the mechanism (`_get_contents` reading full session
history) and the fix (shrink what bootstrap puts into that history) are
both directly evidenced, not speculative.

## Implementation

`make_workspace_tools` gains `list_sections(source_id)` (section_id,
title, heading_path, source_pages -- no body text) and
`read_section(source_id, section_id)` (that section's text, sliced from
`document.md` by its recorded `start_line`/`end_line`), both reading the
already-published `normalized/<source_id>/document.sections.json` no
manifest lookup needed, the path is fixed by convention. `grep_workspace`
resolves `section_id`/`source_pages` on each match via the same lookup,
null when the matched file isn't a normalized document with a section
index. `_BOOTSTRAP_PROMPT` reworded to ask for an index (source tree plus
per-section title/heading path/page range via `list_sections`), explicitly
not a full read or image inspection. `general-report-writing`/
`academic-report` step 1 reworded to fetch evidence on demand via the new
tools instead of assuming it's preloaded. `workspace-summary/SKILL.md`
documents the two tools as the preferred path for its existing
narrow-question case; general-summary behavior (full read, every image)
untouched, per Decisions.

Regression tests: `list_sections`/`read_section` success and error paths,
`grep_workspace` enrichment (present for a normalized-document match, null
outside one), and both bounded/bootstrap agents' tool sets in
`test_report_orchestrator.py` -- proving the new tools are actually wired
into a `call_group` turn's toolset, not just implemented standalone.
