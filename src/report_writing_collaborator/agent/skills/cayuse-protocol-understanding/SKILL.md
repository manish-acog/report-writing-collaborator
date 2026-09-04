---
name: cayuse-protocol-understanding
description: Teaches how to read a Cayuse IACUC animal-use protocol once normalized to Markdown — its section vocabulary, form-prompt-then-answer layout, and table quirks. Load alongside a report skill whenever a source's source_role marks it as a Cayuse protocol; does not detect Cayuse content itself.
---

# Cayuse Protocol Understanding

A Cayuse export isn't prose: it's an exported web form, and the normalizer
renders that form's grid layout as bold prompt lines and Markdown tables, not
narrative paragraphs. Apply these rules whenever reading a source whose
`source_role` marks it as a Cayuse protocol.

## Section vocabulary

Cayuse's own page names surface as headings — Protocol Introduction, Protocol
Overview, Species Information, Strain Information, Non-Surgical Procedures
and Exceptions, Surgical Procedures, Drug Information, Experimental Agents,
Euthanasia Method Information, Animal Numbers, Methodology (with nested
subsections: Test Systems, Test Article and Vehicle Information, Experimental
Design, In-Life Observations, Blood/Fluid and Tissue Sample Collection),
Adverse Effects, Endpoints, Assurance and Attachments. Heading levels are
inconsistent (h1 through h4, sometimes nested under an unrelated parent) —
read `document.sections.json`'s `heading_path`/`parent_section_id`, not the
raw `#` level, to know what's actually nested under what.

## Search, don't browse

This document shape is why `docs/workspace_search_tools.md` exists: roughly 200
sections, one per form question rather than per topic, makes browsing a
structural table of contents expensive and searching past it cheap. Prefer
`grep_workspace` for a known term from the vocabulary below (protocol
number, pain category, route of administration, ...) — its surrounding
context usually returns the form prompt and its answer in one call. Fall
back to reading `document.sections.json` directly (via
`read_workspace_file`) only for a genuine, rare structural-discovery need
— not as the default way to find a field.

## Prompt-then-answer layout

A bold line (`#### **Some question text**`) is Cayuse's form prompt, not
authored content — the actual protocol content is the plain text immediately
following it. Attribute the answer, not the question: don't quote the bold
prompt as if it were the PI's statement.

## A study's groups aren't a fixed shape — read its own group-definition table

Don't assume what a "control" or "comparator" is from convention (e.g. an
older-generation drug, a second active compound); some studies compare a
test article only against its own vehicle, others against a distinct
non-vehicle article, others against more than one. The protocol's own
group-definition table (in Experimental Design or similar) states this
per study — resolve each study's actual design from that table before
labeling any article's role, and treat every other field that names an
article by its role the same way once resolved.

## Table quirks

Dosing/design tables (e.g. the experimental-design group table) use `"` as a
ditto mark meaning "same value as the row above," not a literal quotation —
resolve it to the repeated value before treating a cell as data. The protocol
header table (PI, Protocol #, Status, Approved/Expires dates, Title) and the
Animal Numbers pain-category table (USDA categories B/C/D/E: no pain, no pain
but held for breeding, alleviated pain, unalleviated pain) are both
structured key-value or small grids — read them as such rather than as
prose.

## External attachment links aren't workspace content

The "Assurance and Attachments" and "Attachments" sections list files by name
with links to `*.app.cayuse.com/attachment/...` — these are Cayuse-hosted
references, not promoted workspace sources or assets. Cite them by name
only; never claim to have inspected them, and don't confuse them with
genuine embedded-attachment promotion (which only applies to attachments the
normalizer actually extracted into the workspace).

## Core vocabulary

Read these terms directly rather than inferring them from context: protocol
number, PI, approval status and expiration, pain category (USDA B/C/D/E),
humane endpoint, ICV (intracerebroventricular) and other routes of
administration, test article vs. vehicle, positive/negative control, group
size and total *n*, dose, takedown time, and euthanasia method with its
stated assurance of non-revival (primary + secondary method).
