# Design — `cayuse-protocol-understanding` Skill

## Purpose

Defines a loadable, content-only skill that teaches the agent how to read a
Cayuse IACUC animal-use protocol once it's normalized to Markdown — its
section vocabulary, its form-prompt-then-answer layout, and its table
quirks. For whoever authors
`src/report_writing_collaborator/agent/skills/cayuse-protocol-understanding/SKILL.md`.
Grounded in the actual normalized output of `cayuse.pdf`
(`.workspaces/ws_27c3e533-d70b-4696-91d7-c4a4e29afc9d/1/normalized/src_d9e07dacd7e4/document.md`).

## Why

`workspace-summary` and `evidence-grounding` cover structure and citation
mechanics generically — they don't know what an IACUC protocol's own
sections mean. A Cayuse export isn't prose: it's an exported web form, and
pymupdf4llm renders that form's grid layout as bold prompt lines and
Markdown tables, not narrative paragraphs. A model reading it cold
misattributes a bold question as a heading, treats a `"` ditto mark as an
answer, or cites an external attachment link as if it were inspectable
workspace content. This skill exists so any report skill that loads it gets
that interpretation right without re-deriving it, the same reason
`workspace-summary` exists for structure in general.

## Shape

One skill, `SKILL.md` only — no `variables.json`, no `templates/`. Same
shape as `workspace-summary` and `evidence-grounding`: loaded via
`SkillToolset` by whichever report skill needs it, never run standalone,
and it owns nothing about which report it's feeding or what fields exist.

- **Ingestion is unchanged.** A Cayuse export is an ordinary `FileSource`
  (a PDF), normalized by the existing `DocumentNormalizer` like any other
  document. Distinguishing "this file is a Cayuse protocol" is the caller's
  job via `source_role` — this skill doesn't detect Cayuse content, it's
  loaded deliberately by a report skill that already knows it applies.
  Nothing changes in `canonical_workspace`.
- **What the skill teaches**, based on the observed normalized structure:
  1. **Section vocabulary.** Cayuse's own page names surface as headings —
     Protocol Introduction, Protocol Overview, Species Information, Strain
     Information, Non-Surgical Procedures and Exceptions, Surgical
     Procedures, Drug Information, Experimental Agents, Euthanasia Method
     Information, Animal Numbers, Methodology (with nested subsections:
     Test Systems, Test Article and Vehicle Information, Experimental
     Design, In-Life Observations, Blood/Fluid and Tissue Sample
     Collection), Adverse Effects, Endpoints, Assurance and Attachments.
     Heading levels are inconsistent (h1 through h4, sometimes nested
     under an unrelated parent) — read `document.sections.json`'s
     `heading_path`/`parent_section_id`, not the raw `#` level, to know
     what's actually nested under what.
  2. **Prompt-then-answer layout.** A bold line (`#### **Some question
     text**`) is Cayuse's form prompt, not authored content — the actual
     protocol content is the plain text immediately following it. Don't
     quote the bold prompt as if it were the PI's statement; attribute the
     answer, not the question.
  3. **Table quirks.** Dosing/design tables (e.g. the experimental-design
     group table) use `"` as a ditto mark meaning "same value as the row
     above," not a literal quotation — resolve it to the repeated value
     before treating a cell as data. The protocol header table (PI,
     Protocol #, Status, Approved/Expires dates, Title) and the Animal
     Numbers pain-category table (USDA categories B/C/D/E: no pain, no
     pain but held for breeding, alleviated pain, unalleviated pain) are
     both structured key-value or small grids — read them as such rather
     than as prose.
  4. **External attachment links aren't workspace content.** The
     "Assurance and Attachments" and "Attachments" sections list files by
     name with links to `*.app.cayuse.com/attachment/...` — these are
     Cayuse-hosted references, not promoted workspace sources or assets.
     Cite them by name only; never claim to have inspected them, and don't
     confuse them with genuine embedded-attachment promotion (which only
     applies to attachments the normalizer actually extracted into the
     workspace).
  5. **Core protocol vocabulary** worth naming explicitly so the model
     doesn't have to infer it from context: protocol number, PI, approval
     status and expiration, pain category (USDA B/C/D/E), humane endpoint,
     ICV (intracerebroventricular) and other routes of administration,
     test article vs. vehicle, positive/negative control, group size and
     total *n*, dose, takedown time, and euthanasia method with its stated
     assurance of non-revival (primary + secondary method).

## State

None new. Static skill content, no persisted artifact.

## Scenarios

**In-vivo report skill loads this alongside `benchling-notebook-understanding`.**
The report skill's `SKILL.md` declares both loads; this skill contributes
nothing about Benchling, fields, or templates — it only changes how well
the model reads whichever source has `source_role` indicating a Cayuse
protocol.

**A dosing table cell is `"`.** The model resolves it to the value from the
row above instead of reporting a literal quotation mark or treating the
cell as missing.

**A question asks about an attached test-article form.** The model reports
that the protocol references `ARN-25-030 PRB Test Article Form.docx` by
name (citing the Cayuse source and page) and states it wasn't inspected,
rather than fabricating its contents or treating the external link as
readable.

## Decisions

### Loadable skill, not inline in a report skill's instructions

- **Options:** A — write Cayuse-reading rules directly into each report
  skill that needs them (in-vivo). B (chosen) — one shared, independently
  loadable skill, matching `workspace-summary`/`evidence-grounding`.
- **Chose:** B.
- **Consequences:** any future report skill touching a Cayuse source loads
  this once; the interpretation rules have one place to fix if a new
  Cayuse export shape surfaces a quirk this version didn't anticipate.

### No new ingestion, no Cayuse-specific field on `ManifestSource`

- **Options:** A — add a `CayuseSource`/document-kind marker in
  `canonical_workspace` so the pipeline knows a file is a Cayuse protocol.
  B (chosen) — treat it as a plain `FileSource`; the user-supplied
  `source_role` is the only signal, and it's the caller's responsibility,
  not this skill's or the ingestion layer's.
- **Chose:** B, confirmed: no new source type, no `workspace_builder.py`
  changes.
- **Consequences:** ingestion stays completely blind to document content,
  as designed. This skill is purely an interpretation aid loaded
  deliberately by whichever report skill needs it.

### Rules stated with their reason, not as bare directives

- **Options:** A — flat "always/never" rules. B (chosen) — state each
  quirk with why it matters (same convention `workspace-summary`'s design
  doc already settled on).
- **Chose:** B.
- **Consequences:** generalizes better to a Cayuse export whose exact
  wording differs from this one but shares the same form-export shape.

## Not doing

- **A Benchling understanding skill** — separate skill, separate doc;
  this one only covers Cayuse.
- **Any report skill using this** — `non-clinical-invivo-report`'s
  `variables.json`/templates are a separate follow-on, built on top of this
  once it exists.
- **Detecting "is this a Cayuse protocol" automatically** — explicitly the
  user's job via `source_role`, per your call.

## Open questions

None blocking. Worth a second look once a Cayuse export from a different
institution's IACUC template is available, to confirm the section
vocabulary and table shapes generalize rather than being specific to this
one BioMarin-configured instance.

## Next

Write `src/report_writing_collaborator/agent/skills/cayuse-protocol-understanding/SKILL.md`
covering the five points under "What the skill teaches" above, following
`workspace-summary/SKILL.md`'s reasoned-rule style. No `variables.json`, no
`templates/`.
