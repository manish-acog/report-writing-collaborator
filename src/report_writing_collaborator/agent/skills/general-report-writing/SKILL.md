---
name: general-report-writing
description: Writes a structured report — title, executive summary, key findings, and conclusion — from the provided documents, with every field either grounded and cited or explicitly marked not found. Use when asked to write, draft, produce, or generate a report from source material, as opposed to a free-form summary.
---

# General Report Writing

Write a structured report from the provided documents. This skill runs as a
series of bounded extraction calls, one per field group; the fields for this
call are listed at the end of your instructions.

## Steps

1. This session already built a structural understanding of the workspace
   via the `workspace-summary` skill before this call began — rely on that
   context rather than re-deriving it.
2. Load the `evidence-grounding` skill and apply its status, citation,
   image-evidence, and writing-style rules to every field.
3. Fill only the fields listed at the end of your instructions. Treat
   "workspace" as an internal abstraction; do not use that term in
   user-facing field values.
