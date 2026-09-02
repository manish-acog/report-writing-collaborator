---
name: general-report-writing
description: Writes a structured report — title, executive summary, key findings, and conclusion — from the provided documents, with every field either grounded and cited or explicitly marked not found. Use when asked to write, draft, produce, or generate a report from source material, as opposed to a free-form summary.
---

# General Report Writing

Write a structured report from the provided documents. This skill runs as a
series of bounded extraction calls, one per field group; the fields for this
call are listed at the end of your instructions.

## Steps

1. This session's first turn already indexed the workspace via
   `workspace-summary` — source tree plus, per section, title, heading
   path, and page range. Use that index to identify which sections this
   call's fields need, then fetch exactly those via `list_sections`/
   `read_section`, or `grep_workspace` for a narrow lookup — full section
   text is not preloaded.
2. Load the `evidence-grounding` skill and apply its status, citation,
   image-evidence, and writing-style rules to every field.
3. Fill only the fields listed at the end of your instructions. Treat
   "workspace" as an internal abstraction; do not use that term in
   user-facing field values.
