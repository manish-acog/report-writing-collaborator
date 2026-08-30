---
name: workspace-summary
description: Produces an evidence-grounded summary of a published document workspace, citing source_id and page numbers for every claim. Use when asked to summarize, describe, report on, or answer a question about the contents of a workspace built by WorkspaceBuilder.
---

# Workspace Summary

Summarize (or answer a question about) the documents in a published,
read-only workspace, grounded in evidence.

## Steps

1. Read `manifest.json` at the workspace root to discover every source: its
   `source_id`, `source_role`, and `normalized_path`.
2. For each source, read its normalized Markdown (`normalized_path`) — the
   full document text, headed by `#`/`##`/... section markers.
3. Use `grep_workspace` to locate content relevant to the request before
   reading whole files, when the workspace has many sources.
4. Write one summary per source, then a short overall synthesis if there is
   more than one source.

## Grounding rule

Every factual claim must cite the `source_id` it came from and, when the
claim traces to a specific page, the page number(s). Page numbers for a
section come from that source's `document.sections.json`
(`source_pages` on the section covering the claim) — read that file via
`read_workspace_file` when a citation needs a page number. Never state
something the workspace text doesn't support — say what's missing instead
of guessing.

## Output shape

Plain Markdown. No fixed template beyond this:

```
## <source_role or source_id>
<summary, with inline citations like (src_..., p. N)>
```

If asked a specific question instead of "summarize", answer the question
using the same grounding rule, and skip sources that aren't relevant to it.
