---
name: academic-report
description: Writes an IMRaD-structured academic report — abstract, introduction, methods, results, discussion, and conclusion — from the provided documents, with every field either grounded and cited or explicitly marked not found. Use when asked to write a scientific, academic, or research report, as opposed to a general or free-form report.
---

# Academic Report Writing

Write an IMRaD-structured academic report from the provided documents. This
skill runs as a series of bounded extraction calls, one per field group; the
fields for this call are listed at the end of your instructions.

## Steps

1. This session's first turn already indexed the workspace via
   `workspace-summary` — source tree plus, per section, title, heading
   path, and page range. Use that index to identify which sections this
   call's fields need, then fetch exactly those via `list_sections`/
   `read_section`, or `grep_workspace` for a narrow lookup — full section
   text is not preloaded.
2. Load the `evidence-grounding` skill and apply its status, citation,
   image-evidence, and writing-style rules to every field.
3. Keep **results** and **discussion** strictly separate: state findings
   objectively in `results`, with no interpretation; put what they mean,
   their limitations, and how they relate back to the introduction in
   `discussion`.
4. Write **conclusion** as a summary of what the results established,
   referring back to the introduction's stated purpose. Never introduce a
   claim the results didn't already support.
5. Fill only the fields listed at the end of your instructions. Treat
   "workspace" as an internal abstraction; do not use that term in
   user-facing field values.
