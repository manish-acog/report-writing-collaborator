# Design — Citation URL for ELN Sources

## Purpose

For whoever adds citation-link support for Benchling-derived sources.
Records adding `citation_url`, a field carrying an ELN entry's live URL,
kept separate from `original_path` (the locally preserved, hash-verified
raw JSON). For whoever changes `eln_normalizer.py`, `workspace_builder.py`,
or `report_renderer.py`.

## Why

Every citation in a rendered report links back to its exact source via
`report_renderer._source_href`, built from `original_path`. For file
sources that's correct — the preserved PDF/DOCX copy is exactly what a
reviewer should open. For Benchling entries, `original_path` is the raw
JSON API response, preserved for hash-verified immutability, not a
document a human can read. Whoever reviews a report citing Benchling data
needs the citation to open the actual entry — which the entry's own
`webURL` already provides, and which Benchling users already trust and
have access to.

## Shape

- **`ElnNormalizer._entry_metadata`** (existing, `eln_normalizer.py:592-604`)
  — unchanged; already captures `web_url` into `NormalizedDocument.metadata`.
- **`workspace_builder._citation_url`** (new, sibling to the existing
  `_original_filename`, `workspace_builder.py:286-295`) —
  `normalized.metadata.get("web_url")` for an `ElnSource`, `None` for a
  `FileSource`.
  - exposes: nothing external — called once, at the same `ManifestSource(...)`
    construction site `_original_filename` already is.
  - hands off: a `str | None` written into `ManifestSource.citation_url`.
- **`ManifestSource`** (`workspace_builder.py:58-68`) — gains
  `citation_url: str | None`, written into `manifest.json`.
- **`report_renderer._Source`** (`report_renderer.py:38-44`) — gains the
  same field, read via `_optional_text`, matching `parent_source_id`'s
  existing pattern.
- **`report_renderer._source_href`** (`report_renderer.py:276-281`) —
  prefers `source.citation_url` when set; falls back to today's local-path
  link when `None`.

## State

None new. `citation_url` is derived from `manifest.json` on every render,
not separately persisted or cached.

## Scenarios

**Citing a Benchling entry.** A field cites a Benchling assay entry;
`_Source.citation_url` is set from the entry's `webURL`. The rendered
reference links straight to the live Benchling page. `original.json` stays
preserved on disk, hash-verified, untouched — just no longer what gets
linked.

**Citing a PDF, unaffected.** `citation_url` is `None`; `_source_href`
falls through to today's exact behavior — `original_path`, `#page=N` when
applicable. No new branch reached, no behavior change.

**Extending: a second ELN provider.** Its normalizer sets
`metadata["web_url"]` (or `workspace_builder._citation_url` gains one more
branch, if the key differs by provider) the same way `ElnNormalizer` does.
Either way, `ManifestSource`, `report_renderer._Source`, and
`_source_href` need zero changes — they only ever see `citation_url: str |
None`, never what produced it.

## Decisions

### Separate field, not a repurposed `original_path`

- **Options:** A — make `original_path` the Benchling URL directly for
  ELN sources. B (chosen) — a new `citation_url` field; `original_path`
  untouched.
- **Chose:** B.
- **Consequences:** preserves the hash-verification/immutability contract
  `original_path` already carries uniformly across every source type; the
  renderer gains one more field instead of one existing field acquiring a
  type-conditional meaning.

### Generic field and mechanism, not Benchling-specific

- **Options:** A — name it `benchling_url`, branch on source type inside
  `report_renderer`. B (chosen) — generic `citation_url`, populated by
  whichever normalizer produced the source; `report_renderer` stays
  source-type-agnostic.
- **Chose:** B.
- **Consequences:** a second ELN/API-backed source type gets a working
  citation link for free; `report_renderer` never needs to know what kind
  of source it's rendering, only whether `citation_url` is set.

### Reuse the `_original_filename` pattern, not a generic metadata passthrough

- **Options:** A — expose `NormalizedDocument.metadata` wholesale into
  `ManifestSource`/`manifest.json`, let `report_renderer` pick whatever
  keys it wants. B (chosen) — one named field, derived by one small
  function mirroring `_original_filename`'s existing shape exactly.
- **Chose:** B.
- **Consequences:** no generic metadata contract to define, version, or
  keep stable across normalizer changes — matches the one specific, current
  need. A future derived field means writing one more small function like
  `_original_filename`/`_citation_url`, not renegotiating a wide metadata
  contract nothing else asked for.

## Not doing

- **Linking Benchling attachments (external files) to a Benchling-hosted
  URL** — their download URLs are signed and expire; the locally preserved
  copy stays the correct, durable citation target for those, unchanged by
  this doc.
- **A generic `NormalizedDocument.metadata` → `manifest.json` passthrough**
  — rejected above.
- **Any Benchling-specific branching in `report_renderer`** — rejected
  above; it only ever sees `citation_url: str | None`.

## Open questions

- **Dual-link presentation.** Should a rendered reference ever surface
  both the live Benchling link *and* a way to reach the preserved,
  hash-verified `original.json` (for audit purposes), or is the live link
  alone sufficient? Not blocking — today's rendering shows one link per
  reference for every source type; this doesn't need to be different for
  ELN sources unless a real audit workflow asks for it.

## Implementation

`ManifestSource.citation_url` and `report_renderer._Source.citation_url`
added; `workspace_builder._citation_url` (sibling to `_original_filename`,
same construction site) reads `normalized.metadata.get("web_url")` for an
`ElnSource`, `None` otherwise. `_source_href` prefers `citation_url` when
set. Tests: `test_mixed_source_workspace_dispatches_both_normalizers`
extended with `webURL` on the fixture entry, asserting the PDF source's
`citation_url` stays `None` and the ELN source's matches; new
`test_render_prefers_citation_url_for_eln_source` in
`test_report_renderer.py`. Existing PDF-citation tests pass unchanged --
`citation_url` absent from their manifest fixtures resolves to `None` via
`_optional_text`, same as `parent_source_id`.
