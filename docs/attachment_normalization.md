# Design — Attachment Normalization

## Purpose

Defines how workspace construction turns attached documents into searchable,
provenance-linked sources. This is for implementers and reviewers deciding the
boundary between ingestion and agent-time analysis.

## Why

A study workspace may contain a protocol PDF and an ELN entry whose attachments
hold report evidence. Today those attachments are preserved, but PDF, DOCX, and
PPTX assets remain unreadable to the agent's text tools. Success means every
supported document attachment is normalized and indexed before publication,
while images remain available for targeted analysis without eager model work.

## Shape

Workspace construction expands its input list into a source graph. Normalizers
convert one source and report its preserved attachments; they do not orchestrate
other normalizers. `WorkspaceBuilder` promotes supported document attachments,
normalizes them, indexes them, validates the complete graph, then publishes it
atomically.

- **Source normalizers** — convert one file or ELN entry and report preserved
  attachments.
  - exposes: the existing `NormalizedDocument` contract
  - hands off: normalized content, assets, embedded files, hashes, and warnings
    to `WorkspaceBuilder`
- **`WorkspaceBuilder`** — owns source-graph expansion and complete publication.
  - exposes: the existing workspace-build contract
  - hands off: each normalized document to `StructureIndexer`, then one validated
    manifest to downstream consumers
- **`StructureIndexer`** — indexes one normalized Markdown document.
  - exposes: the existing structure-indexing contract
  - hands off: a section index to `WorkspaceBuilder`
- **Agent runtime** — explores published text and requests image analysis only
  when a skill needs it.
  - exposes: workspace exploration tools; image analysis is a separate design
  - hands off: analysis results to task state or output, never to the workspace

This promotes supported attachment normalization from deferred composition
policy to canonical workspace behavior. It supersedes the deferral in
`eln_ingestion.md`. External URL retrieval remains workflow policy.

## State

No new mutable state exists between builds. A published workspace remains an
immutable, versioned record.

Each promoted attachment becomes a child source:

- `source_id` remains content-derived from SHA-256
- `source_instance_id` is deterministically derived from the parent occurrence
  and the attachment's preserved relative path
- `parent_source_id` points to the immediate containing source
- `source_role` is unset; it is neither inferred nor inherited
- the original bytes, normalized Markdown, section index, hashes, and extracted
  assets belong to that child source

Promoted documents appear in `manifest.sources[]`, not also in
`manifest.assets[]`. Images and unsupported files remain in `manifest.assets[]`.
Repeated document content is normalized once per workspace content identity,
while each occurrence retains its own collection-local `source_instance_id` and
parent relationship. An ancestor content repeat terminates expansion.

Image-analysis results belong to task working state or final output. They do not
modify the canonical workspace.

## Scenarios

### ELN entry with mixed attachments

The caller supplies a protocol PDF and a Benchling entry. Using the existing
Benchling credentials, `ElnNormalizer` fetches the entry and acquires its
referenced attachments during staging: one PDF, one PPTX, and one image.
`WorkspaceBuilder`
promotes the PDF and PPTX to child sources, runs their normalizer and indexer,
keeps the image as an asset of the ELN source, validates the graph, and publishes
one workspace. The agent can search all three Markdown sources and inspect the
image only if its skill requires it.

### Nested supported attachment

A promoted PDF contains an embedded DOCX. Its normalizer reports the DOCX;
`WorkspaceBuilder` promotes it as a child of the PDF and continues until no
unseen supported document attachment remains. A repeated ancestor content hash
ends that branch without repeating normalization.

### Attachment failure

A source references an attachment that cannot be acquired. Workspace construction
fails regardless of file type because the evidence set is incomplete. If an
acquired supported document cannot be normalized or indexed, construction also
fails. The staging workspace remains inspectable; no published workspace appears.

### Extending supported documents

A developer adds a new file type to the existing document-normalization contract.
`WorkspaceBuilder` then promotes that type wherever it is attached, without a
Benchling-specific branch or an agent change.

## Decisions

### Reuse the existing normalization path

- **Options:** A (simplest) — leave attachments as raw assets and add binary tools
  to the agent. B — build attachment-specific converters. C — reuse
  `DocumentNormalizer` → `StructureIndexer` for attached documents.
- **Chose:** C. The workspace already has the required deterministic conversion,
  identity, structure, and provenance contracts.
- **Consequences:** attachment handling follows the same evidence boundary as
  top-level files. Normalizers remain single-source components.

### Normalize attachments from every source type

- **Options:** A (simplest) — normalize only direct Benchling attachments. B —
  normalize one attachment level under every source. C — expand supported
  attachments under every source until none remain.
- **Chose:** C. Both document and ELN normalizers already discover attachments;
  one source-agnostic rule avoids parallel ingestion behavior.
- **Consequences:** the workspace becomes a graph rather than only the caller's
  flat source list. Expansion must terminate safely on repeated content.

### Publish promoted documents only as sources

- **Options:** A (simplest) — keep every attachment only as an asset. B — publish
  promoted documents as both assets and sources. C — publish promoted documents
  only as child sources; retain images and unsupported files as assets.
- **Chose:** C. One artifact should have one canonical manifest representation.
- **Consequences:** consumers distinguish searchable documents from raw assets
  through manifest membership, without deduplicating two records.

### Derive child identity from content and occurrence

- **Options:** A (simplest) — use only the content-derived `source_id`. B — assign
  random child instance IDs. C — keep content-derived `source_id` and derive a
  collection-local instance ID from the parent occurrence plus the attachment's
  preserved relative path.
- **Chose:** C. It preserves existing content identity while representing repeated
  files and stable parent relationships.
- **Consequences:** identical bytes share normalization output but may have
  multiple manifest occurrences. The relative path supplies a vendor-neutral
  occurrence identity.

### Fail on incomplete attachment acquisition or normalization

- **Options:** A (simplest and current ELN behavior) — publish best-effort and keep
  warnings. B — make strictness configurable. C — fail acquisition for every
  referenced attachment and fail normalization/indexing for supported documents.
- **Chose:** C. A plausible but incomplete workspace can produce an unsupported
  report without exposing the missing evidence to the agent.
- **Consequences:** one unavailable attachment blocks publication. The failure is
  visible at construction time, and staging remains available for diagnosis.

### Analyze images lazily

- **Options:** A (simplest) — preserve and hash images, then let the agent analyze
  a selected image when required. B — generate model descriptions for every image
  during construction. C — run OCR for every image, but defer interpretation.
- **Chose:** A. Image meaning is task-dependent; eager interpretation adds cost
  and generated claims to an otherwise deterministic ingestion boundary.
- **Consequences:** the workspace is complete without being semantically expanded.
  A later image-analysis tool must preserve source-path and model provenance in
  task evidence.

### Normalize repeated content once

- **Options:** A — normalize every attachment occurrence, risking duplicate work
  and recursive cycles. B (simplest safe option) — normalize each content identity
  once while retaining each occurrence and relationship. C — reject repeated
  content as invalid.
- **Chose:** B. Repetition is valid; repeated computation and non-termination are
  not.
- **Consequences:** normalization output is shared by content identity. Manifest
  occurrences still preserve collection-local context.

## Not doing

- **Image-analysis tool** — its model, evidence schema, and failure behavior need a
  separate design.
- **Eager image descriptions or OCR** — neither is required for searchable
  document attachments.
- **Unsupported format conversion** — unsupported files remain preserved assets.
- **External URL retrieval** — only source-contained attachments are in scope.
- **Semantic role inference** — child roles remain unset unless a future workflow
  supplies authoritative metadata.
- **Configurable recursion or failure policy** — there is one required behavior;
  no second workflow currently justifies configuration.
- **Agent changes** — normalized child sources use the existing manifest and text
  exploration contract.

## Open questions

No blocking questions. The later image-analysis design must decide its accepted
formats, model boundary, evidence record, and unresolved-result behavior.

## Next

Review this design, then prepare the implementation plan for source-graph
expansion, strict attachment failures, manifest changes, and focused tests.
