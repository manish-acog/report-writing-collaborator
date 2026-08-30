---
name: general-report-writing
description: Writes a structured report — title, executive summary, key findings, and conclusion — from a published document workspace, with every field either grounded and cited or explicitly marked not found. Use when asked to write, draft, produce, or generate a report from a workspace, as opposed to a free-form summary.
---

# General Report Writing

Write a structured report from a published, read-only document workspace,
grounded in evidence. This skill runs as a series of bounded extraction
calls, one per field group; the fields for this particular call are listed
at the end of your instructions.

## Steps

1. Load the `workspace-summary` skill and follow its structural pass to
   build a picture of the workspace's sources, roles, and images before
   extracting anything — a report is only as trustworthy as the
   understanding it's built on.
2. For each field you're asked for, decide whether the workspace supports
   an answer. A field with no supporting evidence gets `not_found` — never
   invent a value to fill a placeholder; an absent field says more than a
   fabricated one.
3. For a field you can answer, cite every `source_id` (and page number,
   when the evidence traces to one) the value depends on. A claim without a
   citation isn't evidence-grounded, whatever the sentence says.
4. Use `inspect_image` on an image only when a field's evidence actually
   depends on what it shows — most fields won't need it.
