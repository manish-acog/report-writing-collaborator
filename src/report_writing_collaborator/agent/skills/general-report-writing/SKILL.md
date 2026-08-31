---
name: general-report-writing
description: Writes a structured report — title, executive summary, key findings, and conclusion — from the provided documents, with every field either grounded and cited or explicitly marked not found. Use when asked to write, draft, produce, or generate a report from source material, as opposed to a free-form summary.
---

# General Report Writing

Write a structured report from the provided documents. This skill runs as a
series of bounded extraction calls, one per field group; the fields for this
call are listed at the end of your instructions.

## Steps

1. Load the `workspace-summary` skill and follow its structural pass before
   extracting anything.
2. Load the `evidence-grounding` skill and apply its status, citation, and
   image-evidence rules to every field.
3. Fill only the fields listed at the end of your instructions. Treat
   "workspace" as an internal abstraction; do not use that term in
   user-facing field values.
