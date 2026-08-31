# Design — Citation Granularity

## Purpose

Extends `docs/citation_enrichment.md`: turns a field's citations from "these
sources were used somewhere in this answer" into "this specific sentence
came from this specific evidence," rendered as clickable superscripts
pointing into a numbered References list. For whoever extends
`report_renderer.py` and `general-report-writing/SKILL.md`.

## Why

Reviewing real output surfaced two problems this doc closes. First, a
field's `citations` array was structurally satisfied by naming the *source*
once, even when the prose drew on several distinct pages — nothing required
more, so nothing produced more. Second, a report reader had no way to see
which sentence a citation actually backed; citations lived at the bottom,
disconnected from the claims they supported. Both trace to the same cause:
citations were attached to a whole field, never to the claim within it.

## Shape

No schema restructuring — `{status, value: str, citations: list[Citation]}`
stays exactly as `docs/citation_enrichment.md` left it. What changes is what
the model writes inside `value`, and one new rendering pass.

- The model places a marker after each claim it makes:
  `[[cite:N]]`, where `N` is the index of that claim's evidence in *this
  field's own* `citations` array — not a report-wide number. The model never
  needs to know or track numbering across fields.
- `report_renderer` gains a marker-resolution pass, run after citation
  collection and before template substitution:
  1. Walk every field in template order, collecting citations exactly as
     today (`_collect_citations`'s existing dedup key:
     `(source_id, section_id, page)`), but now also assigning a sequential,
     1-based global number to each *distinct* key the first time it's seen —
     repeated evidence reuses its existing number.
  2. For each field's `value`, find every `[[cite:N]]`, resolve `N` against
     that field's own `citations` list, look up the global number for its
     dedup key, and replace the marker with
     `<sup><a href="#ref-{number}">{number}</a></sup>`.
  3. Render the References list in that same global order — unchanged
     content (name, role, lineage, page, verbatim preview, original-file
     link, from the existing `_resolve_reference`), plus a visible number and
     an anchor target the superscript can jump to.
- Anchor targets: `<li id="ref-{number}">` in the HTML template. The
  Markdown template's list is native `- ` bullets, which can't carry an
  `id` — so a standalone `<a id="ref-{number}"></a>` precedes each bullet,
  giving the same jump target without converting the list to raw HTML.

## State

None new. Still a pure, deterministic pass over already-published data —
the model's own citations, the manifest, the section index.

## Scenarios

**A claim backed by two citations.** "The study is short, about two weeks
[[cite:0]][[cite:1]]." — two adjacent markers, because `Citation` still
carries one page each; a claim resting on two pages gets two markers, not
one marker pointing at a citation that can't represent both. Renders as
two superscripts, `¹²`, each jumping to its own numbered reference.

**The same evidence cited from two different fields.** `key_findings` and
`conclusion` both cite `(src_x, sec_y, p.1)`. Both get the same superscript
number — the same anchor, the same list entry — not two entries for
identical evidence.

**A malformed or out-of-range marker.** `[[cite:9]]` where the field only
listed four citations raises `ReportRenderError`, same posture as every
other invalid-reference case already in `report_renderer`. A marker that
doesn't match the pattern at all (a stray `[[cite:]]` or typo) is left as
literal text — a cosmetic miss, not a failed render.

## Decisions

### Markers are local to a field, numbering is global

- **Options:** A — the model tracks and writes report-wide numbers itself.
  B (chosen) — the model references its own field's citation list by local
  index; the renderer assigns global numbers when it assembles the report.
- **Chose:** B.
- **Consequences:** the model's task stays simple — one field, one local
  list, no cross-field bookkeeping it can't actually see while generating
  one bounded call at a time. The renderer does the harder part it's already
  positioned to do correctly.

### Multi-page evidence stays multiple `Citation` entries, cited by adjacent markers

- **Options:** A — add a `pages: list[int]` field to `Citation`. B (chosen)
  — no schema change; a claim spanning several pages gets one `Citation`
  per page and one marker per citation.
- **Chose:** B.
- **Consequences:** the schema that already exists already covers this —
  the gap was instructional, not structural. The skill now explicitly asks
  for one citation per page rather than a page range typed into free text.

### Instruction requires a citation behind every marker, closing the root cause

- **Options:** A — keep "cite every `source_id` the value depends on" as-is.
  B (chosen) — every `[[cite:N]]` marker must reference a real entry in that
  field's `citations`; every distinct claim gets its own marker and its own
  entry.
- **Chose:** B.
- **Consequences:** this is what actually fixes the one-citation-per-field
  problem — the model can no longer satisfy the requirement by naming a
  source once, because writing a marker with nothing behind it is now
  incomplete, not just imprecise.

### Superscript, not `<details>`, not a separate page

- **Options:** A — `<details>` disclosure per field (considered two turns
  ago). B — a genuinely separate page/file per citation. C (chosen) —
  academic-style superscript, same-page anchor jump to a numbered
  References list.
- **Chose:** C, per your call.
- **Consequences:** the References section stays where it already is, on
  the same page — which means the earlier idea of dropping the 400-character
  preview cap (reasoned from "it'll open in another tab") no longer applies.
  Truncation stays, since the section is still embedded in the same
  document the reader is scrolling.

### Raw HTML superscript over native Markdown footnotes

- **Options:** A — `[^N]` / `[^N]: text` native Markdown footnote syntax.
  B (chosen) — `<sup><a href="#ref-N">N</a></sup>`, same mechanism in both
  templates.
- **Chose:** B, per your call.
- **Consequences:** one rendering approach serves both templates, consistent
  with the raw-HTML-passthrough already relied on for the preview
  blockquote. Depends on the Markdown consumer supporting inline HTML
  (true for GitHub-flavored renderers, the assumed target); a strict
  HTML-stripping renderer would show or silently drop the markup — a known,
  accepted limitation, not solved here.

## Not doing

- **Claims-list schema restructuring** — superseded; markers get the same
  per-claim precision without a new `variable_type` or Pydantic shape.
- **Character-offset citation positioning** — rejected as fragile for the
  same reason free-text citation parsing was rejected in the original
  citation-enrichment doc.
- **Schema-level enforcement of marker syntax inside `value`** — not
  possible; `value` stays a free string. Enforcement is instructional for
  the marker convention itself, with bounded, graceful failure for
  malformed syntax and hard failure only for a marker that resolves to
  nothing real.

## Open questions

The configured `openai/qwen3.6-coder` smoke run returned every field as
`not_found`, so it produced no markers or citations to compare. Renderer
agreement is covered deterministically; instruction-following remains
unverified against a model that actually extracts evidence.

## Implementation

Implemented in `report_renderer.py` and the general-report-writing skill.
Renderer tests cover template-order numbering, cross-field deduplication,
adjacent multi-page markers, Markdown and HTML anchors, malformed markers,
and hard failure for valid-looking markers that resolve out of range.

**Superseded by `docs/citation_presentation_cleanup.md`:** the "unchanged
content" and "preview blockquote" language above predates that doc, which
removed the verbatim section preview entirely and switched references from
`<ul>`/manual numbering to a native `<ol>`/`1. ` ordered list. The
superscript-and-anchor mechanism this doc introduced is otherwise unchanged.
Adjacent markers on one claim now render comma-separated
(`<sup>1</sup>,<sup>2</sup>`), not run together.
