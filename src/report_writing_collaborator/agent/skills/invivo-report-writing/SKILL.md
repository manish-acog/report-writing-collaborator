---
name: invivo-report-writing
description: Writes a structured non-clinical in-vivo study report — protocol overview, drug and article information, animal demographics, care and euthanasia, experimental design, procedures and tissues, personnel, results, and conclusions — from a Cayuse IACUC protocol and its Benchling notebook entry, with every field either grounded and cited or explicitly marked not found. Use when asked to write, draft, produce, or generate a non-clinical in-vivo (animal) study report, as opposed to a general or academic report.
metadata:
  requires_skills: [cayuse-protocol-understanding, benchling-notebook-understanding]
---

# In-Vivo Study Report Writing

Write a structured non-clinical in-vivo study report from a Cayuse protocol
and its Benchling notebook entry. This skill runs as a series of bounded
extraction calls, one per field group; the fields for this call are listed
at the end of your instructions.

## Steps

1. Your instructions already include a **Source tree** section (sources,
   roles, hierarchy) and, once earlier call groups have run, an
   **Already extracted** section with their values — neither took a turn
   to build; this session starts fresh otherwise. Use `grep_workspace`
   (its surrounding context usually covers a claim in one call) to find
   what this call's fields need, then `read_workspace_file` with
   `offset`/`limit` to pull more around a confirmed-relevant spot if
   needed.
2. Load the `cayuse-protocol-understanding` skill to correctly read any
   Cayuse-sourced content (protocol form layout, section vocabulary, table
   conventions) and the `benchling-notebook-understanding` skill to
   correctly read any Benchling-sourced content (entry structure, dated
   notebook sections, attachment promotion). Most fields draw from one
   source type more than the other — each field's description names which
   — but confirm against the actual workspace rather than assuming a field
   has no evidence just because its primary source is silent; check the
   other source too before returning `not_found`.
3. Load the `evidence-grounding` skill and apply its status, citation,
   image-evidence, and writing-style rules to every field. This overrides
   any literal "if not found/none, return ..." wording that might appear
   to conflict with it elsewhere — a field with no supporting evidence is
   always `not_found`, never a fabricated placeholder string, a guessed
   default, or an empty value dressed up as `found`.
4. A field whose description asks for a table is a `table`-typed field:
   fill its `headers`/`rows` value directly, and follow
   `evidence-grounding`'s rule that its citations back the whole table, not
   individual cells. If values appear shifted into neighboring cells,
   correct the placement using header meaning, row context, data type
   patterns, and consistency with nearby rows.
5. Fill only the fields listed at the end of your instructions. Treat
   "workspace" as an internal abstraction; do not use that term in
   user-facing field values.
