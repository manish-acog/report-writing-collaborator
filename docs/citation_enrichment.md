# Design — Citation Enrichment

## Purpose

Defines how `report_renderer` turns a `Citation` into a human-legible,
traceable, evidence-previewing reference entry, replacing today's raw
`source_id`-only citation. For whoever extends `report_renderer.py` and the
`variable_config.py`/`workspace_builder.py` schemas it depends on.

## Why

A report's reader isn't the workspace's audience — the workspace exists to
give the agent evidence to work from. A citation reading `src_a82f91c43b7e,
p. 4` tells a human nothing: not what document that is, not whether it's
traceable to something they could open, not what it actually says. A report
citing evidence should read like evidence, not like an internal identifier.

## Shape

One extension to `report_renderer`, two schema additions.

- **`report_renderer`** — gains access to the workspace it's rendering
  against (`manifest.json`, and each cited source's `document.sections.json`
  and normalized Markdown), alongside the value map and template it already
  takes. Enrichment lives here, next to the existing mandatory-references
  mechanism — both are the same responsibility: turning raw citations into a
  References section, not two separate passes over the same data.
  - exposes: `render(template_path, values, workspace_root) -> str`
  - hands off: nothing — still the terminal step, still no model access

- **`ManifestSource`** gains `original_filename: str` — the source's name as
  supplied, mirroring `EmbeddedFile.original_name`. File sources preserve the
  supplied basename, promoted attachments preserve their embedded name, and
  Benchling sources use the entry name with the entry ID as fallback.

- **`Citation`** gains `section_id: str | None = None` — which section of the
  cited source the claim traces to, when it traces to one. Optional: a claim
  synthesizing a whole document doesn't have one bounded section to point at,
  and shouldn't be forced to invent one.

For each citation, the renderer resolves, in one deterministic pass:
1. **Legible name** — `source_role` when set, `original_filename` always;
   never falls back to a bare `source_id`.
2. **Traceability** — the source's `original_path`, the preserved raw file.
3. **Preview** — when `section_id` is present, the verbatim text between that
   section's `start_line`/`end_line` in its normalized Markdown, truncated to
   400 characters. Verbatim, not model-generated — a paraphrase would
   reintroduce exactly the risk a citation exists to rule out.

`general-report-writing`'s `SKILL.md` asks for `section_id` whenever the claim
traces to one bounded section. Whole-document synthesis omits it rather than
inventing a section reference.

## State

None new. Still a pure, deterministic computation over already-published,
immutable data — `manifest.json`, `document.sections.json`, normalized
Markdown. Nothing is written back to the workspace.

## Scenarios

**A claim backed by one section.** `executive_summary` cites `{source_id:
src_a82f91c43b7e, section_id: sec_..., page: 4}`. The reference renders as
"Protocol.pdf (protocol), p. 4" with a short verbatim excerpt from that
section beneath it — traceable, legible, and spot-checkable without opening
the workspace.

**A claim without a bounded section.** A synthesis citing a source broadly,
with `section_id` unset. The reference renders with name and page (if given),
no preview line — nothing invented to fill a slot that doesn't apply.

**A citation to a promoted child source.** The cited source is an attachment
promoted out of a Benchling entry (`parent_source_id` set). Name resolution
combines with the lineage enrichment already planned: "Appendix_Slides.pptx,
attached within [parent's name]" — one mechanism, not two competing ones.

## Decisions

### Renderer gains workspace access, not a separate enrichment pass

- **Options:** A — keep `render()`'s signature as-is; enrich citations in the
  orchestrator before calling it. B (chosen) — pass `workspace_root` into
  `render()`; enrichment lives beside the existing citation-collection and
  mandatory-references logic.
- **Chose:** B.
- **Consequences:** one place walks citations, dedupes them, and formats the
  References section — not two passes over the same data with the risk of
  drifting apart.

### Add `ManifestSource.original_filename`

- **Options:** A — derive a display name from `source_role` alone, no schema
  change. B (chosen) — add `original_filename`, mirroring
  `EmbeddedFile.original_name`.
- **Chose:** B.
- **Consequences:** `source_role` is optional and categorical ("protocol"),
  not a specific document name — relying on it alone would fall back to a
  raw `source_id` too often to call the result legible.

### Add `Citation.section_id`, optional

- **Options:** A — require it on every citation. B (chosen) — optional;
  claims that trace to one bounded section get a preview, broader claims
  don't.
- **Chose:** B.
- **Consequences:** not every citation gets a preview, but nothing forces a
  claim into a section reference it doesn't actually have.

### Preview is a deterministic, bounded, verbatim slice

- **Options:** A — a model-generated summary of the cited section. B (chosen)
  — the literal text between `start_line` and `end_line`, truncated.
- **Chose:** B.
- **Consequences:** the preview is exactly what's being cited, trustworthy by
  construction. It is capped at 400 characters, including the trailing
  ellipsis when truncated.

## Not doing

- **Exporting or attaching original files alongside a rendered report** — the
  renderer surfaces `original_path`, but whether a standalone report needs
  the actual file bundled is a delivery decision, not settled here.
- **Previewing more than one bounded excerpt per citation** — no "show full
  section" mechanism.
- **Citation-preview handling for images or tables** — image citations
  already have their own representation via the asset path; table preview
  isn't addressed by this doc.

## Open questions

- **Original-file delivery** — carried over from last turn, still open: does
  "traceable" mean a workspace-relative path is enough, or does a shipped
  report need the cited files exported alongside it?

## Implementation

Implemented in `workspace_builder.py`, `variable_config.py`, and
`report_renderer.py`. The general-report-writing skill requests bounded
`section_id` values, and the promoted-attachment integration test exercises
name resolution, traceability, preview extraction, and parent lineage.
