---
name: general-report-writing
description: Writes a structured report — title, executive summary, key findings, and conclusion — from the provided documents, with every field either grounded and cited or explicitly marked not found. Use when asked to write, draft, produce, or generate a report from source material, as opposed to a free-form summary.
---

# General Report Writing

Write a structured report from the provided documents,
grounded in evidence. This skill runs as a series of bounded extraction
calls, one per field group; the fields for this particular call are listed
at the end of your instructions.

## Steps

1. Load the `workspace-summary` skill and follow its structural pass to
   build a picture of the sources, roles, and images before extracting
   anything — a report is only as trustworthy as the understanding it's
   built on.
2. For each field you're asked for, decide whether the source material supports
   an answer. A field with no supporting evidence gets `not_found` — never
   invent a value to fill a placeholder; an absent field says more than a
   fabricated one.
3. For every distinct factual claim in a `found` field's `value`, place a
   `[[cite:N]]` marker immediately after the claim. `N` is the zero-based
   index of that evidence in this field's own `citations` array.
4. Every marker must point to a real citation, and every citation must back at
   least one marker. Reuse the same index when the same evidence supports
   several claims. Include `source_id`, a page when applicable, and
   `section_id` from `document.sections.json` for bounded-section evidence.
5. When one claim depends on several pages, add one `Citation` per page and
   place their markers next to each other: `[[cite:0]][[cite:1]]`. Never put a
   page range into one citation.
6. Use `inspect_image` on an image only when a field's evidence actually
   depends on what it shows — most fields won't need it.
