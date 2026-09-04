---
name: benchling-notebook-understanding
description: Teaches how to read a normalized Benchling ELN entry — its heading/date structure, its "heading detected by shape" quirk, promoted-attachment duplication, and its table and custom-field conventions. Load alongside a report skill whenever a source's source_role marks it as a Benchling notebook entry.
---

# Benchling Notebook Understanding

A normalized Benchling entry isn't authored prose — it's a rendering of
Benchling's block-based note types, and `BenchlingFormatter` makes
deliberate, sometimes surprising choices translating that block structure to
Markdown. Apply these rules whenever reading a source whose `source_role`
marks it as a Benchling notebook entry.

## Entry metadata header

The first block (`# <entry name>` then a bullet list: `ID`, `Display ID`,
`Created`, `Modified`, `Author`, `Web URL`) is Benchling's own entry identity,
not authored content — useful for citing which entry a claim came from, but
not itself a finding.

## `## <date>` sections are dated notebook days, not report structure

Benchling entries are organized by the day work was logged
(`## 2025-05-28`), each holding that day's notes in original order. Don't
read a date heading as a topic; read what's under it as "what was recorded
that day," and state the date when a finding is time-sensitive (e.g. an
observation logged on a specific day).

## A short line before a table or list can be an inferred heading, not the author's literal title

The formatter promotes a short (≤80 char), non-terminal-punctuation line
immediately preceding a table, list, or text box to `### heading` — because
Benchling's own block types don't carry a heading flag the exporter can read
directly. This is inference, not ground truth: read it as a label for what
follows, and don't treat its exact wording as something the author
necessarily typed as a heading.

## A `**File:** [id](path)` link may repeat

The same attachment note can appear more than once in the entry's raw note
sequence (e.g. the same file linked six times under "Historical Data"); this
reflects the entry's actual authored repetition, not a normalization bug.
Don't inflate evidence weight by citing the same attachment as if each
repetition were independent support — collapse to one citation per distinct
file when synthesizing.

## Attachments are promoted, first-class sources — read them, don't just name them

Unlike a Cayuse export's *external* attachment links (hosted off-workspace),
a Benchling entry's `external_file` notes that the normalizer resolved to an
`asset_paths` entry are promoted into the workspace as their own source,
with `parent_source_id` pointing back to this entry (e.g. an attached
protocol PDF, PPTX design deck, or manifest spreadsheet each get their own
`source_id`). Follow `parent_source_id` to know an attachment belongs to
this entry, then read the attachment's own `normalized_path` directly —
don't treat the entry's inline link as a substitute for reading it.

## Tables render as plain Markdown tables, headers included

A `table`/`registration_table`/`results_table` note becomes a `**<name>**`
label followed by a standard `| --- |` Markdown table; read it like any
other table — no special quirk, unlike a Cayuse table's ditto-mark
convention.

## `## Custom Fields` at the end is structured entry metadata, not a late-added section

Benchling's custom fields (e.g. `Research Project Code`, `Study Number`)
always print last, after every dated day — treat them as entry-level
metadata (like the header block), not as the entry's concluding content.

## A results-style section's actual finding may live only in an attached image

Benchling entries often record a chart, plot, or gel image as the finding
itself, with only a short caption or none — this is a normal way results
get logged here, not a gap in the entry. A heading like "Results," "Data,"
or "Analysis" followed by images and little surrounding text is a sign the
finding is in the image; inspect it before concluding the entry has
nothing to say.

## An attached record may name the same material differently than the study does

A promoted attachment (e.g. a Certificate of Analysis, formulation, or
dosing record) often identifies test/control material by its own internal
code, batch, or lot designation rather than whatever name the study
protocol uses for that article. Don't rule out an attachment as
irrelevant on name mismatch alone — resolve the link through shared
attributes the two documents do share (dose level, chemistry, timing,
study/group identifiers) before treating either as silent on the other.

## Core vocabulary

Entry (the notebook record itself) vs. attachment (a promoted child
source); day section; custom field; the entry's own project/study
identifiers, when present, as the anchor for tying an entry to the study it
documents.
