---
name: workspace-summary
description: Produces an evidence-grounded summary of the provided documents, citing source_id and page numbers for every claim. Use when asked to summarize, describe, report on, or answer a question about the source material — including structural questions like which sources were provided, what they contain, how they're organized, or what images they have.
---

# Workspace Summary

Summarize (or answer a question about) the provided documents, grounded in
evidence.

## Steps

1. **Build the structure.** Read `manifest.json` and, from `sources[]`, build
   the source tree by following each source's `parent_source_id` back to its
   root. Note each source's `source_role` (or its absence) and, from
   `assets[]`, which files belong to it. This pass runs for every request,
   not only "summarize" ones — knowing that a source is a promoted attachment
   of another matters for judging relevance even when the output only
   answers a narrow question.
2. **Inspect the images.** Among each source's assets, an image is one whose
   extension is `.png`, `.jpg`, `.jpeg`, `.gif`, or `.webp` — the same set
   `inspect_image` accepts, so nothing gets sent that the tool would reject
   anyway. For a general summary, call `inspect_image` on every one found;
   a complete picture of the source material means every image gets read, not
   a sample chosen by count. For a narrow question, call it only on images the
   question actually turns on. No images among the sources simply means
   skipping this step — there's nothing to special-case.
3. **Read the content.** For a general summary, read each source's
   normalized Markdown (`normalized_path`) in full — the complete document
   text, headed by `#`/`##`/... section markers. For a narrow question,
   call `list_sections` first to see a source's table of contents, then
   `read_section` for just the section(s) the question turns on — or
   `grep_workspace` to locate the right spot first when the answer's
   location isn't obvious from titles alone. Avoid reading a whole
   document when only a fraction of it is relevant.
4. **Write the output.** For a general summary, open with the structural
   picture built in step 1 (source tree, roles, asset and image counts),
   then give per-source content, folding in what step 2 found about each
   source's images. For a narrow question, skip the structural section —
   it already did its job by helping decide what's relevant — and answer
   directly.

## Grounding rule

Every factual claim must cite the `source_id` it came from and, when the
claim traces to a specific page, the page number(s). Page numbers for a
section come from that source's section index — `list_sections`,
`read_section`, and `grep_workspace` all already surface `source_pages`
directly; read `document.sections.json` via `read_workspace_file` only if
you need a field they don't already give you. An `inspect_image` result is
evidence like any other: cite the image's path and its source_id. Don't
state something the source text or an image doesn't support — say what's
missing instead of guessing.

## Output shape

Plain Markdown. No fixed template beyond this:

```
## Source Overview
<source tree with roles; asset and image counts per source>

## <source_role or source_id>
<content, with inline citations like (src_..., p. N) or (src_..., path)>
```

Include the "Source Overview" section only when the request is a general
summary or asks about the source material's structure or contents rather than a
specific fact. For a narrow question, answer it directly using the same
grounding rule, and skip sources that aren't relevant to it.
