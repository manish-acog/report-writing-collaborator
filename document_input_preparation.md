# Document Input Preparation

## Goal

Convert one or more supported source documents into a structured, immutable canonical workspace.

The preparation flow should be:

- deterministic where possible
- provenance-preserving
- independently testable
- modular without over-fragmentation
- reusable across document-driven workflows
- atomic at workspace publication time

---

## Architectural Boundary

The core implementation contains three reusable modules:

```text
DocumentNormalizer
StructureIndexer
WorkspaceBuilder
```

Ownership:

```text
DocumentNormalizer
→ owns source-to-artifact conversion

StructureIndexer
→ owns deterministic Markdown structure

WorkspaceBuilder
→ owns orchestration, validation, and workspace integrity
```

`manifest.json` is the abstraction seam between input preparation and downstream consumers.

---

## 1. `DocumentNormalizer`

### Responsibility

Normalize one source document at a time.

```text
source document
→ normalized Markdown
+ extracted images
+ metadata
+ embedded files
+ links
+ provenance mappings
```

Initial supported types:

- PDF
- DOC/DOCX
- PPT/PPTX

### Processing

```text
PDF
    ↓
PyMuPDF pre-pass
    ├── inspect metadata
    ├── detect embedded files
    ├── detect links
    └── preserve page metadata
    ↓
PyMuPDF4LLM
    ├── write_images=True
    ├── embed_images=False
    ├── force_text=True
    └── selective/hybrid OCR only when needed
    ↓
normalized Markdown + image assets
```

For DOC/DOCX and PPT/PPTX:

```text
source document
→ deterministic conversion to PDF
→ same PDF normalization path
```

The converter and version must be pinned and recorded in provenance.

### Stable Contract

```python
normalize_document(source: SourceSpec) -> NormalizedDocument
```

### `NormalizedDocument`

Required fields:

```json
{
  "source_id": "src_a82f91c43b7e",
  "source_instance_id": "source_01",
  "source_type": "pdf",
  "original_path": "sources/src_a82f91c43b7e/original.pdf",
  "normalized_path": "normalized/src_a82f91c43b7e/document.md",
  "assets": [],
  "embedded_files": [],
  "links": [],
  "page_map": [],
  "header_footer": [],
  "metadata": {},
  "hashes": {
    "source_sha256": "...",
    "normalized_sha256": "..."
  },
  "tooling": {
    "normalizer": "pymupdf4llm",
    "normalizer_version": "...",
    "converter": null,
    "converter_version": null
  },
  "warnings": []
}
```

### Failure Semantics

`normalize_document()` returns `NormalizedDocument` only on success.

Fatal failures raise typed exceptions. Warnings remain on the returned object.

Example:

```python
class DocumentNormalizationError(Exception):
    ...

class UnsupportedDocumentTypeError(DocumentNormalizationError):
    ...

class DocumentConversionError(DocumentNormalizationError):
    ...

class DocumentParseError(DocumentNormalizationError):
    ...
```

A successful `NormalizedDocument` must not contain fatal errors.

### Invariants

A successful `NormalizedDocument` must satisfy:

- source file exists and hash is recorded
- normalized Markdown exists
- normalized Markdown hash is recorded
- all referenced extracted assets exist
- all declared output paths are inside the workspace staging area
- tool and version metadata are recorded
- warnings are explicit
- source artifacts are never modified in place

### Internal Concerns

Keep these internal unless a real standalone reuse case emerges:

- image extraction
- embedded-file extraction
- header/footer handling
- table extraction
- OCR fallback
- link extraction
- page mapping
- hashing
- parser warnings
- converter invocation

---

## 2. `StructureIndexer`

### Responsibility

Build deterministic structure over normalized Markdown.

```text
normalized Markdown
→ deterministic section hierarchy
```

It should produce:

- stable section IDs
- heading paths
- line ranges
- source-page mappings
- parent/child relationships

### Stable Contract

```python
index_structure(document: NormalizedDocument) -> DocumentStructure
```

### `DocumentStructure`

Required fields:

```json
{
  "source_id": "src_a82f91c43b7e",
  "sections": [
    {
      "section_id": "sec_<stable_hash>",
      "title": "4.1 Species and Strain",
      "heading_level": 3,
      "heading_path": [
        "4. Test System",
        "4.1 Species and Strain"
      ],
      "start_line": 128,
      "end_line": 147,
      "source_pages": [7],
      "parent_section_id": "sec_<parent_hash>"
    }
  ],
  "hashes": {
    "structure_sha256": "..."
  },
  "tooling": {
    "indexer": "...",
    "indexer_version": "..."
  },
  "warnings": []
}
```

### Stable Section IDs

Section IDs should not be based on absolute position alone.

Primary identity is derived deterministically from:

```text
source_id
+ normalized parent heading path
+ normalized heading title
+ occurrence index among sibling headings with the same normalized title
```

Duplicate disambiguation algorithm:

1. normalize the heading title
2. identify sibling headings under the same normalized parent path
3. count prior siblings with the same normalized title
4. assign a 1-based occurrence index

Example identity input:

```text
src_a82f91c43b7e
> 4. Test System
> Observations
> occurrence_2
```

A hash of this identity may be used as the stored `section_id`.

Line numbers and source-page coordinates are provenance attributes, not section identity.

Section IDs are stable within a single workspace version. Stability
across workspace versions is not guaranteed — a normalizer or indexer
upgrade can change heading structure and therefore section identity.

### Invariants

A successful `DocumentStructure` must satisfy:

- every section belongs to exactly one source
- every section has a stable ID
- line ranges are valid and non-negative
- parent/child relationships are internally consistent
- heading paths agree with hierarchy
- source-page mappings, when available, point to valid source pages
- the structure hash is recorded
- indexing does not modify normalized Markdown

---

## 3. `WorkspaceBuilder`

### Responsibility

Build and publish a canonical workspace containing one or more source documents.

```text
SourceSpec[]
    ↓
DocumentNormalizer
    ↓
StructureIndexer
    ↓
workspace validation
    ↓
atomic publish
    ↓
Canonical Document Workspace
```

### Stable Contract

```python
build_workspace(
    sources: list[SourceSpec],
    config: WorkspaceConfig
) -> WorkspaceManifest
```

### Workspace Ownership

A workspace represents a document collection, not a single document.

A collection may contain one source or many.

This keeps the normalization API single-document and independently testable while allowing the workspace contract to scale.

### Workspace Identity

`workspace_id` and `workspace_version` follow the rules in "Workspace
Identity and Versioning" below. `WorkspaceBuilder` validates and applies
the lineage context supplied by its caller — it does not discover or
decide lineage itself.

- Changed canonical content creates a new workspace version rather than
  mutating a published version in place.

### Atomic Creation

Workspace creation must be atomic.

The staging directory and final destination must reside on the same filesystem/mount so publication can use an atomic rename/move.

```text
build in temporary staging directory
    ↓
run all transformations
    ↓
validate workspace invariants
    ↓
write manifest/provenance
    ↓
atomic rename within same filesystem
    ↓
published workspace
```

Failed runs must not leave a plausible partial canonical workspace.

### Responsibilities

`WorkspaceBuilder` should:

- accept one or more source specifications
- create a staging workspace
- preserve original source files
- invoke `DocumentNormalizer`
- invoke `StructureIndexer`
- place artifacts predictably
- validate workspace invariants
- generate `manifest.json`
- generate provenance records
- generate debug logs
- atomically publish only after validation succeeds

It should orchestrate modules, not contain parser logic.

---

## Source Identity

Source identity must be independent of input ordering.

### `source_id`

`source_id` identifies source content and is derived from the source SHA-256:

```text
src_<first-12-hex-characters-of-sha256>
```

Example:

```text
src_a82f91c43b7e
```

### `source_instance_id`

`source_instance_id` identifies a specific occurrence of that source in the workspace.

This allows identical files to appear intentionally more than once without changing content identity.

Example:

```json
{
  "source_id": "src_a82f91c43b7e",
  "source_instance_id": "source_01"
}
```

`source_id` is content-stable.

`source_instance_id` is collection-local.

---

## Header and Footer Handling

Repeated headers and footers should not pollute searchable Markdown.

Recommended behavior:

```text
repeated header/footer
→ remove from body Markdown
→ preserve separately when useful
```

Potentially useful metadata includes:

- document ID
- version
- effective date
- sponsor/owner
- confidentiality marker
- page numbering

Header/footer interpretation may be workflow-specific, but provenance behavior should remain uniform.

---

## Images

Use:

```text
write_images=True
embed_images=False
```

Images should be stored separately and referenced from Markdown.

Do not eagerly describe images during input preparation.

Images remain source-derived assets.

---

## Embedded Files and Links

### Embedded Files

Embedded files should be extracted and preserved as source-derived artifacts.

```text
extract
→ store under embedded/<source_id>/
→ record in manifest/provenance
```

Whether embedded files are recursively normalized is workflow/composition
policy. A recursively normalized embedded file becomes a child source in
the same workspace: it gets its own `source_id`, runs the normal
`DocumentNormalizer` → `StructureIndexer` path, and appears in
`manifest.json` `sources[]` with a `parent_source_id` pointing back to
the source it was embedded in. It does not spawn a separate workspace.

### Links

Extract and record:

- internal links
- external URLs
- remote file links

Whether external URLs are downloaded is workflow/composition policy.

---

## Table Handling

Use deterministic extraction first.

```text
default extraction
    ↓ fail
alternate deterministic strategy
    ↓ fail
optional bounded LLM repair
```

LLM repair must never silently replace canonical deterministic extraction.

Store repaired output separately:

```text
normalized/
→ deterministic extraction

derived/<source_id>/repaired_tables/
→ repaired table artifact
```

A repaired artifact should have one authoritative transformation record in `provenance/transformations.json` containing:

- source artifact
- source page/coordinates
- original extracted representation
- repaired representation
- repair model/version
- prompt/version
- timestamp
- uncertainty flags
- validation status

`manifest.json` stores only a lightweight reference, for example:

```json
{
  "derived_artifact_id": "drv_123",
  "provenance_ref": "transform_456"
}
```

---

## Canonical Workspace

```text
document_workspace/
├── manifest.json
│
├── sources/
│   ├── src_a82f91c43b7e/
│   │   └── original.pdf
│   └── src_b1930ed11842/
│       └── original.docx
│
├── normalized/
│   ├── src_a82f91c43b7e/
│   │   ├── document.md
│   │   └── document.sections.json
│   └── src_b1930ed11842/
│       ├── document.md
│       └── document.sections.json
│
├── assets/
│   ├── src_a82f91c43b7e/
│   │   └── images/
│   └── src_b1930ed11842/
│       └── images/
│
├── embedded/
│   ├── src_a82f91c43b7e/
│   └── src_b1930ed11842/
│
├── derived/
│   ├── src_a82f91c43b7e/
│   │   └── repaired_tables/
│   └── src_b1930ed11842/
│       └── repaired_tables/
│
├── provenance/
│   ├── transformations.json
│   ├── hashes.json
│   └── source_map.json
│
└── debug/
    ├── parser_output/
    ├── conversion_logs/
    └── failures/
```

---

## Manifest

`manifest.json` is the stable abstraction boundary for downstream consumers.

Example:

```json
{
  "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
  "workspace_version": 2,
  "previous_version": 1,
  "workspace_state": "published",
  "sources": [
    {
      "source_id": "src_a82f91c43b7e",
      "source_instance_id": "source_01",
      "source_role": "protocol",
      "source_type": "pdf",
      "original_path": "sources/src_a82f91c43b7e/original.pdf",
      "normalized_path": "normalized/src_a82f91c43b7e/document.md",
      "sections_path": "normalized/src_a82f91c43b7e/document.sections.json"
    }
  ],
  "assets": [],
  "embedded_files": [],
  "derived_artifacts": []
}
```

Downstream consumers should rely on:

```text
manifest
source identity
source role
normalized representation
structure
assets
provenance
```

not parser-specific implementation details.

Downstream references to a `section_id` must always carry the
`workspace_version` it was resolved against — `section_id` alone is not
a durable pointer across versions.


## Workspace Identity and Versioning

`workspace_id` identifies a workspace lineage.

Rules:

- a new lineage receives a UUID
- all later versions in that lineage keep the same `workspace_id`
- `workspace_version` is a monotonically increasing integer starting at `1`
- each version records `previous_version`
- published versions are immutable
- lineage discovery is owned by the application/workflow layer
- `WorkspaceBuilder` validates and applies supplied lineage context

Example:

```json
{
  "workspace_id": "ws_550e8400-e29b-41d4-a716-446655440000",
  "workspace_version": 3,
  "previous_version": 2
}
```

## Workflow Policy vs Core Behavior

Core modules should remain workflow-agnostic.

### Core behavior

Uniform across workflows:

- normalization contracts
- structure contracts
- hashing
- provenance
- source preservation
- immutable published workspaces
- atomic publication
- error/warning semantics
- tool/version recording

### Workflow/composition policy

Defined outside core modules:

- `source_role`
- document-specific validation rules
- header/footer interpretation
- embedded-file normalization policy
- external-link policy
- use-case-specific metadata requirements

---

## Read-Only Definition

A published canonical workspace is read-only in two senses.

### 1. Immutable workspace version

Published workspace contents are never mutated in place.

Any transformation that changes canonical content creates a new workspace version.

### 2. Downstream filesystem access

Downstream consumers should receive filesystem-level read-only access where practical.

They may create outputs elsewhere, but cannot modify published canonical source, normalized, provenance, or manifest artifacts.

---

## Provenance and Logging

For every transformation, record:

```text
input path
input hash
output path
output hash
tool/parser version
converter/version where applicable
parser/conversion settings
timestamp
success/failure
warnings
errors
```

Keep:

```text
provenance/ = durable transformation record
debug/      = troubleshooting output
```

Debug output must never be the only source of important provenance.

---

## Module Boundary

Top-level reusable modules:

```text
DocumentNormalizer
StructureIndexer
WorkspaceBuilder
```

Keep lower-level concerns internal unless a clear standalone capability emerges.

Examples:

```text
ImageExtractor
EmbeddedFileExtractor
HeaderFooterProcessor
LinkExtractor
HashGenerator
TableRepairStrategy
OfficeConverter
```

Independently testable does not require independently exposed.

---

## Final Flow

```text
Source Documents
    ↓
workflow-specific composition/configuration
    ↓
WorkspaceBuilder
    ↓
DocumentNormalizer
    ↓
StructureIndexer
    ↓
workspace validation
    ↓
atomic publish
    ↓
Immutable Canonical Document Workspace
```

The modules remain generic. Workflow-specific composition decides how they are used.
