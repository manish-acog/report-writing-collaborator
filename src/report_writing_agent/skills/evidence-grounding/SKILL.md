---
name: evidence-grounding
description: Defines found/not_found and citation-marker rules for schema-constrained report fields. Load alongside workspace-summary whenever a report-writing skill fills fields from source evidence.
---

# Evidence Grounding

Apply these rules to every schema-constrained report field.

## Steps

1. **Choose the supported status.** Use `found` only when the source material
   supports an answer. Otherwise return `not_found` without a `value` or
   `citations`; never invent content to fill a placeholder.
2. **Mark every factual claim.** In a `found` field's `value`, place a
   `[[cite:N]]` marker immediately after every distinct factual claim. `N` is
   the zero-based index of that evidence in this field's own `citations`
   array.
3. **Keep markers and citations paired.** Every marker must point to a real
   citation, and every citation must back at least one marker. Reuse the same
   index when the same evidence supports several claims. Include `source_id`,
   a page when applicable, and `section_id` from `document.sections.json` for
   bounded-section evidence.
4. **Keep multiple markers separate.** When one claim needs more than one
   citation for any reason, place complete markers next to each other:
   `[[cite:0]][[cite:1]]`. Never combine indexes inside one marker or bracket
   pair, such as `[[cite:0,1]]` or `[[cite:0], [cite:1]]`.
5. **Cite pages precisely.** Use one `Citation` per page and place their
   complete markers next to each other. Never put a page range into one
   citation.
6. **Inspect images only when needed.** Use `inspect_image` only when a field's
   evidence actually depends on what it shows — most fields won't need it.
