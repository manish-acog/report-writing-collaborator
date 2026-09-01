---
name: academic-report
description: Writes an IMRaD-structured academic report — abstract, introduction, methods, results, discussion, and conclusion — from the provided documents, with every field either grounded and cited or explicitly marked not found. Use when asked to write a scientific, academic, or research report, as opposed to a general or free-form report.
---

# Academic Report Writing

Write an IMRaD-structured academic report from the provided documents. This
skill runs as a series of bounded extraction calls, one per field group; the
fields for this call are listed at the end of your instructions.

## Steps

1. This session already built a structural understanding of the workspace
   via the `workspace-summary` skill before this call began — rely on that
   context rather than re-deriving it.
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
