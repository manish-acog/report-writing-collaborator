# Design — `academic-report` Skill

## Purpose

Defines a second report-writing skill, following IMRaD (Introduction,
Methods, Results, Discussion) — the standard structure for scientific
reports, not specific to any one source. For whoever authors
`academic-report/variables.json` and its templates. Grounded in IMRaD
convention and the OU report-writing guide, not one source alone.

## Why

`general-report-writing`'s four fields (title, executive summary, key
findings, conclusion) are deliberately generic — a minimal proof that the
template-first, evidence-grounded pipeline works at all. Scientific and
academic reports have a real, standard shape of their own, with a
discipline `general-report-writing` doesn't enforce: findings are stated
objectively, separate from what they mean, and a conclusion draws only on
what was established, referring back to a stated purpose rather than
introducing anything new. This is also the second, real consumer of
`evidence-grounding` and `workspace-summary` that justified extracting them
in the first place.

## Shape

Same mechanism as `general-report-writing`, different field list.

- **`academic-report/SKILL.md`** — loads `workspace-summary`, loads
  `evidence-grounding` (status/citation/marker/style rules, unchanged),
  fills the fields below, plus two rules specific to this structure.
- **`academic-report/variables.json`** — one `call_group`:

  ```
  title
  abstract      — brief, self-contained: aims, methods, key results, conclusion
  introduction  — background, the question or problem addressed, its significance
  methods       — how the work was conducted, in traceable detail
  results       — findings, stated objectively — no interpretation here
  discussion    — what the findings mean, limitations, relation back to the introduction
  conclusion    — summary and implications; refers back to the introduction's
                  stated purpose; introduces nothing new
  ```

- **`academic-report/templates/report.md`, `report.html`** — same shape as
  `general-report-writing`'s templates, one section per field, `{{references}}`
  required as always.

## State

None new.

## Scenarios

**A workspace with a described procedure.** `methods` gets a `found` value —
dosing regimen, experimental design, whatever the source describes as how
the work was done.

**A workspace that's pure document review, no procedure described.**
`methods` returns `not_found` — same discipline as any other field with
no supporting evidence, not a special case for this skill.

**Results and Discussion, kept apart on purpose.** A finding ("BLEU score
of 28.4, exceeding prior models") goes in `results`, cited, stated plainly.
What that means (why it matters, how it compares, what's uncertain) goes in
`discussion`, not mixed into the same sentence.

## Decisions

### Follow IMRaD, not the OU guide's fuller optional-sections list

- **Options:** A — include every section the OU guide names as possible
  (literature review, appendices, bibliography). B (chosen) — Abstract,
  Introduction, Methods, Results, Discussion, Conclusion — the actual
  cross-discipline standard, References handled automatically as it
  already is everywhere else.
- **Chose:** B.
- **Consequences:** a literature-review field would sit `not_found` for
  most of the workspaces this project actually produces (a protocol plus
  ELN entries, not a literature corpus) — matches nothing, included on
  spec. IMRaD is the field set actually earned by real report content.

### Results states; Discussion interprets — made explicit, not assumed

- **Options:** A — leave the distinction implicit in the field names. B
  (chosen) — state it directly in each field's `variables.json`
  description, since it's the one discipline point this structure has
  that `general-report-writing` doesn't.
- **Chose:** B.
- **Consequences:** without stating it, there's no reason to expect the
  model draws the line differently than `key_findings` already does.

### `methods` is optional like every other field, not specially handled

- **Options:** A — treat `methods` as required, since IMRaD assumes an
  experiment. B (chosen) — same `not_found` discipline as everything else;
  a workspace without a described procedure just doesn't populate it.
- **Chose:** B.
- **Consequences:** the skill works on document-review-style workspaces
  too, not only ones describing a formal procedure.

## Not doing

- **Literature review, appendices, bibliography as separate fields** — not
  matched by what this project's workspaces actually contain; References
  already covers citation listing.
- **Discipline-specific IMRaD variants** (engineering's design section,
  social science's extended discussion) — no evidence yet any of this
  project's workspaces need them; add if a real one does.

## Open questions

**Skill name** — using `academic-report`, no strong alternative considered.
Flag if a different name fits better.

## Next

Author `academic-report/variables.json`, `SKILL.md`, and both templates.
Smoke-test against a workspace with a described procedure and one without,
confirming `methods` gracefully returns `not_found` in the second case.
