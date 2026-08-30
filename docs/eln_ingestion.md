# Design — ELN Ingestion (Benchling)

## Purpose

Defines how Benchling ELN entries become sources in the same canonical
workspace `document_input_preparation.md` already defines for PDF/DOC/PPT
— a new source producer, not a new pipeline. Read by whoever implements
ELN ingestion, or extends it to a second ELN vendor later.

## Why

Non-clinical study reports cite lab notebook entries alongside protocol
and study-report documents. The workspace needs to hold both,
indistinguishably to everything downstream of `NormalizedDocument`.

## Shape

```text
Benchling API (entry fetch)
    ↓
ElnNormalizer  →  NormalizedDocument   (same contract as DocumentNormalizer)
    ↓
StructureIndexer                       (unchanged)
    ↓
WorkspaceBuilder                       (unchanged, one new dispatch branch)
```

- **`ElnNormalizer`** — owns entry-to-artifact conversion for ELN
  sources. Fetches an entry by ID, preserves the raw fetched JSON as the
  source artifact, renders it to Markdown (reusing `BenchlingFormatter`'s
  existing note-type dispatch from `benchling_parser.py`), downloads
  external files as assets. Exposes `normalize_entry(source: ElnSource)
  -> NormalizedDocument` — same output contract as
  `DocumentNormalizer.normalize_document`, a sibling, not a subclass.
- **`StructureIndexer`** — unchanged. `ElnNormalizer`'s Markdown already
  uses ATX headings (entry title, per-day, detected embedded headings);
  section scanning needs nothing new.
- **`WorkspaceBuilder`** — unchanged except one dispatch point:
  `_build_in_staging`'s per-source loop branches on which of
  `FileSource | ElnSource` it received and calls the matching
  normalizer. Manifest assembly, validation, versioning, atomic publish
  are identical either way, because both normalizers hand back the same
  `NormalizedDocument`.

## State

No change to what persists — same canonical workspace tree. New content
within it:

- `sources/<source_id>/original.json` — the raw fetched entry, preserved
  before formatting. Same "source artifacts are never modified in place"
  invariant `DocumentNormalizer` already follows for `original.pdf`.
- `assets/<source_id>/` — downloaded external files, hashed the same way
  as PDF-derived assets.

## Scenarios

**1. Mixed-source workspace.** A protocol PDF and a related Benchling
notebook entry both belong in one workspace for one study.
`WorkspaceBuilder` gets `[FileSource(...), ElnSource(...)]`, dispatches
each to its normalizer, publishes one workspace with both sources in
`manifest.sources[]`.

**2. Extending to a second ELN vendor.** A new sibling normalizer
implementing the same `NormalizedDocument` contract, a new member of
the source union, one more branch at the dispatch point.
`StructureIndexer`, manifest shape, versioning: untouched.

## Decisions

### Source union shape

- **Options:** A (simplest) — discriminated union, `FileSource |
  ElnSource`, sharing `source_instance_id`/`source_role`/
  `parent_source_id`. B — one class, optional fields, a `kind`
  discriminator.
- **Chose:** A.
- **Consequences:** an `ElnSource` without `entry_id` (or a `FileSource`
  without `path`) is unrepresentable, not just runtime-checked.
  `_build_in_staging` gains one `isinstance` branch; nothing else in
  `WorkspaceBuilder` changes.

### Naming

- **Options:** A (simplest) — `ElnSource`/`ElnNormalizer`, vendor-neutral
  at the type/seam level, Benchling-specific inside (fields, API client,
  note-type dispatch). B — `BenchlingSource`/`BenchlingNormalizer`,
  naming the one vendor that exists today.
- **Chose:** A.
- **Consequences:** if Benchling is replaced or a second ELN vendor is
  added, nothing that imports `ElnSource` needs to change. Cost: none —
  the internals are exactly as Benchling-specific either way; this only
  changes what callers see.

### Source identity for API-fetched content

- **Options:** A (simplest) — hash the fetched entry JSON, same
  `source_id = "src_" + sha256(bytes)[:12]` convention as file sources.
  B — use Benchling's own `id`/`displayId` as identity.
- **Chose:** A.
- **Consequences:** an edited entry becomes a new `source_id`
  automatically, same as a re-uploaded PDF would — no special-casing for
  "this source is an API response, not a file." B would require deciding
  what "changed" means for an entry; A already answers that by
  construction.

### Page/section-page mapping

- **Options:** A (simplest) — none; `Section.source_pages` stays empty
  for ELN-derived sections, matching what the existing formatter already
  does (no page concept). B — a day-based analogue, since day boundaries
  are known.
- **Chose:** A.
- **Consequences:** citations to ELN-derived sections carry
  `section_id`/line range, no page number — consistent with the Evidence
  Contract, which already treats page as optional context, not a
  requirement. B stays available later if something actually needs to
  cite by day; nothing here forecloses it.

### Table extraction

- **Options:** A (simplest) — none, ported or built. B — reuse the
  deleted `benchling_table_parser.py`'s regex-based extraction and its
  Benchling/Cayuse-specific provenance shape.
- **Chose:** A.
- **Consequences:** table handling stays exactly where
  `document_input_preparation.md` already left it — deferred, and when
  built, built once, generically, for every source type. B would have
  forked table handling into a second, Benchling-only path carrying
  provenance fields (`cayuse_sections`) tied to an unrelated prior
  system.

### Exception hierarchy

- **Options:** A (simplest) — `ElnNormalizer` raises its own hierarchy
  (`ElnNormalizationError` and subtypes for fetch/auth/parse failures),
  parallel to `DocumentNormalizationError`, not reusing it. B — reuse
  `DocumentNormalizationError`.
- **Chose:** A.
- **Consequences:** `WorkspaceBuilder` doesn't care either way — it
  already catches broad exceptions and wraps them as
  `WorkspaceBuildError`. This is purely about not conflating two
  unrelated failure domains (API/auth failures vs. file-parsing
  failures) under one name for anyone calling `ElnNormalizer` directly.

## Not doing

- **Table extraction for ELN sources** — deferred with PDF table
  handling, not built separately.
- **A second ELN vendor, or any abstraction anticipating one** —
  `ElnSource`/`ElnNormalizer` are named to allow it later; nothing is
  built for it now.
- **Day-based page-mapping analogue** — not needed until something
  actually cites by day.

## Open questions

None blocking. If a second ELN vendor ever appears, that's the point to
decide whether `ElnSource` needs its own internal split.

## Next

Move `benchling_parser.py`'s fetch/format logic into
`src/report_writing_collaborator/eln_normalizer.py`, matching the
existing package layout (`document_normalizer.py`, `structure_indexer.py`,
`workspace_builder.py`). Add `FileSource`/`ElnSource` to
`workspace_builder.py`, wire the dispatch branch, smoke-test against one
real Benchling entry alongside one real PDF in the same workspace.
