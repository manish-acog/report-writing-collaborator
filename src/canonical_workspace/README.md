# canonical_workspace

Turns a heterogeneous set of source documents and ELN entries into an
immutable, versioned, individually-citable workspace. Standalone — no
dependency on `report_writing_collaborator`, no agent framework, no model
calls. Usable by anything that needs a durable evidence base, not just this
project's own report generation.

## What it does

```text
sources                     canonical_workspace/<id>/<version>/
┌─────────────┐             ┌────────────────────────────────┐
│ protocol.pdf│──normalize──▶│ manifest.json                  │
│ appendix.docx│─normalize──▶│ sources/   (preserved originals)│
│ Benchling ID │──fetch─────▶│ normalized/(Markdown + sections)│
│  entry      │             │ assets/    (images, attachments)│
└─────────────┘             └────────────────────────────────┘
                                        │
                              atomic publish, immutable once written
                              workspace_version: 1 ─▶ 2 ─▶ 3 ...
```

Each source — a PDF, a Word or PowerPoint file, or a fetched Benchling
entry — is normalized to Markdown, structurally indexed into sections with
stable, content-addressed IDs, and hashed for provenance. Everything is
assembled into one workspace, published atomically: either the whole thing
exists correctly, or nothing does.

## Why this is the real work, not the document conversion

PDF/DOCX/PPTX → Markdown is a solved, commodity problem — tools like
Docling, Unstructured, and LlamaParse already do it, some with more
sophisticated layout analysis than the parser used here. That part is
swappable by design; nothing outside `document_normalizer.py` knows or
cares which conversion library produced a `NormalizedDocument`.

What none of those tools give you, and what this module is actually for:

- **Immutable, versioned, lineage-tracked publication.** A workspace is
  published once, atomically, and never mutated in place — `workspace_id` +
  monotonically increasing `workspace_version` + `previous_version`, so a
  citation can point at an exact version and stay correct.
- **Content-addressed section IDs, durable across versions** — built for
  being cited by a human-facing report later, not for retrieval-time
  relevance the way RAG chunking is.
- **Recursive attachment promotion.** An embedded or attached document
  becomes its own first-class, independently indexed child source, with
  `parent_source_id` lineage back to where it came from — not flattened
  into its container's text.
- **One identity and versioning contract across file sources and API
  sources.** A Benchling entry and a PDF share the exact same
  `NormalizedDocument` shape, hashing, and section-indexing path — not a
  bolted-on connector with its own rules.

## Using it standalone

```python
import canonical_workspace as cw

manifest = cw.build_workspace(
    [cw.FileSource(path=Path("protocol.pdf"), source_instance_id="source_01")],
    cw.WorkspaceConfig(publish_root=Path("workspaces")),
)
```

Mixing a file and a Benchling entry in one workspace:

```python
manifest = cw.build_workspace(
    [
        cw.FileSource(path=Path("protocol.pdf"), source_instance_id="source_01"),
        cw.ElnSource(entry_id="etr_123", source_instance_id="source_02"),
    ],
    cw.WorkspaceConfig(
        publish_root=Path("workspaces"),
        benchling_api_key=...,
        benchling_url=...,
    ),
)
```

## Explicitly out of scope

No embeddings, no vector search, no semantic retrieval — this is the
durable-evidence layer underneath a retrieval system, not a retrieval
system itself. A consumer either reads the manifest and reasons over it
directly (as this project's agent does), or builds retrieval on top.

Full design and every decision behind this shape:
`docs/document_input_preparation.md`, `docs/eln_ingestion.md`,
`docs/attachment_normalization.md`.
