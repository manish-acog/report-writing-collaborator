---
name: general-report-writing
description: Writes a structured report — title, executive summary, key findings, and conclusion — from the provided documents, with every field either grounded and cited or explicitly marked not found. Use when asked to write, draft, produce, or generate a report from source material, as opposed to a free-form summary.
---

# General Report Writing

Write a structured report from the provided documents. This skill runs as a
series of bounded extraction calls, one per field group; the fields for this
call are listed at the end of your instructions.

## Steps

1. Your instructions already include a **Source tree** section (sources,
   roles, hierarchy) and, once earlier call groups have run, an
   **Already extracted** section with their values — neither took a turn
   to build; this session starts fresh otherwise. Use `grep_workspace`
   (its surrounding context usually covers a claim in one call) to find
   what this call's fields need, then `read_workspace_file` with
   `offset`/`limit` to pull more around a confirmed-relevant spot if
   needed.
2. Load the `evidence-grounding` skill and apply its status, citation,
   image-evidence, and writing-style rules to every field.
3. Fill only the fields listed at the end of your instructions. Treat
   "workspace" as an internal abstraction; do not use that term in
   user-facing field values.
