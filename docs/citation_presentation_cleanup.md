# Design — Citation Presentation Cleanup

## Purpose

Small formatting fixes to citation rendering, found from real output, plus
one narrowly-scoped addition: opening a cited PDF at the right page. For
whoever touches `report_renderer.py` next.

## Why — and are we overengineering this?

No. Three of four changes remove things (a redundant bullet-plus-number, a
whole preview feature, its supporting code) rather than add them. The one
real addition — a page-jump link — is a single conditional string, not a new
mechanism: no new file, no new module, no schema change. The discipline is
in what this deliberately excludes (below), not in restraint on this list.

## Shape

All four land in `report_renderer.py`; nothing else changes.

- **Adjacent superscripts get a separator.** Consecutive `[[cite:N]]`
  markers currently resolve back-to-back with nothing between them —
  `¹²³` reads as `123`. Join them with a comma between the resolved
  superscripts.
- **References become a real ordered list, not a bullet with a number typed
  inside it.** The numbers already assigned (1..N, no gaps, since the
  underlying list is deduped) are exactly what `<ol>` numbers natively, so
  the manual `"1. "` prefix inside `<ul><li>` is redundant — switch to
  `<ol><li>` in HTML, native `1. `/`2. ` list syntax in Markdown, both
  keeping their anchor `id`/preceding `<a id>` for the superscript jump.
- **The preview goes away.** No `<blockquote><pre>` block. Preview lives
  behind a future, separate frontend, not this renderer. `_read_preview`
  and `_Reference.preview` go with it — not deferred, deleted, since nothing
  in this design still needs them.
- **"p. N" becomes "page N".**
- **A cited PDF's filename links to the exact page; other file types don't
  try to.** PDF viewers support a `#page=N` URL fragment — appending it to
  a `.pdf` link jumps straight there on open. This only means anything for
  PDFs; DOCX, PPTX, and Benchling originals have no equivalent, so their
  filename links stay plain. Either way, **only the filename is ever a
  link** — "page N" is always plain descriptive text after it, never a
  separate clickable target itself. One shared helper builds the href,
  appending `#page={page}` only when the source's original file is a `.pdf`
  and a page is present; both formatters call it instead of duplicating the
  `quote(...)` call each has today.

## State

None. No schema change, no new persisted data.

## Scenarios

**A citation to a specific PDF page.** Reference renders as `1.
[Protocol.pdf](sources/.../original.pdf#page=4) (protocol), page 4` — click
the filename, the PDF opens at page 4.

**A citation to a promoted PPTX attachment, with a page.** Renders as `2.
[Slides.pptx](sources/.../original.pptx) (attached within Entry_X), page 7`
— filename links to the file itself; "page 7" is informational text, not
clickable, since nothing can jump a PPTX to a page from a URL.

**Three adjacent citations on one claim.** `...effect [[cite:0]][[cite:1]][[cite:2]]`
resolves to `¹,²,³` — visually distinct, not `123`.

## Decisions

### Comma-separated superscripts

- **Options:** A — leave markers adjacent with nothing between them
  (current, confirmed broken). B (chosen) — join resolved superscripts with
  a comma, matching standard academic multi-citation notation.
- **Chose:** B.
- **Consequences:** none beyond the fix itself.

### Native ordered list over manual numbering in a bullet list

- **Options:** A — keep `<ul><li>1. ...` (current, redundant marker). B
  (chosen) — `<ol><li>` in HTML, native `1. ` syntax in Markdown.
- **Chose:** B.
- **Consequences:** one visual marker per reference instead of two; anchor
  ids are unaffected either way.

### Remove preview and its supporting code

- **Options:** A — keep preview, adjust its formatting. B (chosen) — remove
  it entirely; a future frontend owns evidence preview, not this renderer.
- **Chose:** B, per your call.
- **Consequences:** `_read_preview`, `_Reference.preview`, and the 400-char
  truncation constant are deleted, not retained unused. Less code, not more.

### PDF-only page-jump, explicitly not attempted for other formats

- **Options:** A — build page-jump support for every original file type
  (would require embedding an actual document viewer for DOCX/PPTX — real
  new infrastructure). B (chosen) — PDF only, via the existing `#page=N`
  browser/viewer convention; every other type keeps a plain filename link.
- **Chose:** B.
- **Consequences:** free, real value for the common case (most protocols and
  attachments here are PDFs) without building anything resembling a document
  viewer. Non-PDF sources are no worse off than they are today — just not
  improved.

## Not doing

- **Page-jump for DOCX/PPTX/other formats** — no browser-native mechanism
  exists; doing this would mean embedding a real viewer, out of scope and
  not justified by anything asked for here.
- **Separate-tab evidence preview** — raised and deliberately deferred last
  turn; unrelated to this cleanup, not reopened here.

## Open questions

None blocking.

## Next

Implement the four changes in `report_renderer.py`, delete the now-unused
preview code, update `tests/test_report_renderer.py` for the new reference
shape (no preview, ordered list, page-jump href).
