# Design — PDF Image Extraction Limits and Deduplication

## Purpose

For whoever changes `document_normalizer.py`'s image extraction path.
Fixes: workspaces built from image-heavy PDFs — most commonly, an
institutional protocol document with a letterhead or logo repeated on
every page — end up with 100+ near-duplicate image assets, each a
separate candidate for `inspect_image`, inflating cost and latency
wherever something inspects "every image" (e.g. `workspace-summary`'s
general-summary mode, unchanged by this doc — see Not Doing).

## Why

Two independent contributors, both confirmed by reading the extraction
code directly:

1. **`image_size_limit` never reached the code that extracts images —
   confirmed dead, not just unset.** `_parse_pdf`'s
   `pymupdf4llm.to_markdown(...)` call dispatches to `_layout_to_markdown`
   whenever `pymupdf.layout` is importable (`pymupdf4llm/__init__.py:50-56`
   — *"Always attempt to use Layout by default"*), which it is in this
   environment. `_layout_to_markdown`'s own kwarg list
   (`__init__.py:59-87`) doesn't include `image_size_limit` at all — it
   falls into a trailing `**kwargs` explicitly commented *"unsupported
   options for pymupdf layout"* and is silently discarded.
   `document_layout.parse_document`, the function actually doing the
   extraction, writes every region the layout model classifies as
   `"picture"`/`"formula"` (`document_layout.py:1551-1559`) with no size
   check anywhere in that path. Passing `image_size_limit` at any value
   changes nothing under the active layout engine.
2. **No content-based deduplication anywhere in the extraction path.**
   `_collect_assets` (`document_normalizer.py:477-484`) enumerates every
   file `pymupdf4llm` wrote and hashes each for tracking, but never checks
   whether two files are byte-identical. `pymupdf4llm` writes one file per
   *occurrence*, not per unique image — a logo on 50 pages produces 50
   separate, identical files, each becoming its own `Asset`.

## Shape

- **`_parse_pdf`** — passes `dpi` explicitly (previously left at the
  library default) so the filter below has a known, fixed value to
  compare against.
- **New: a post-write size filter** — after `pymupdf4llm` writes a
  page's images, read each written file's own pixel dimensions and
  compare against that page's full-page-equivalent pixel size at the same
  `dpi` (`page.rect.width/height * dpi/72`); drop files whose width **or**
  height falls under 10% of the corresponding page dimension — either
  alone is enough, not both required. Applied post-write, not via any
  `pymupdf4llm` kwarg — there isn't one that works under the active
  layout engine.
- **`_collect_assets`** — hashes every extracted image file; keeps only
  the first occurrence (by sorted path) of each unique SHA-256. Duplicate
  files stay on disk exactly as `pymupdf4llm` wrote them — nothing is
  deleted, nothing is rewritten. Only the returned `Asset` tuple — what
  becomes `manifest.assets[]`, the list `workspace-summary` and anything
  else enumerating "assets to consider" actually sees — collapses to one
  entry per unique image.

## State

None new.

## Scenarios

**A 50-page protocol with a repeated letterhead.** All 50 near-identical
files are still written to `assets_dir` by `pymupdf4llm`, unchanged.
`manifest.assets[]` lists it once. Anything inspecting "every image found"
sees one image, not fifty.

**A genuinely small decorative icon (e.g. a 3%-of-page-width bullet
graphic).** Filtered by the post-write pixel-dimension check, comparing
its written file's own size against the source page's — not by any
`pymupdf4llm` kwarg, confirmed dead under the active layout engine.

**Two visually similar but not byte-identical images** (e.g. two
different photos of similar-looking tissue). Not deduplicated — this is
exact-hash matching, not similarity matching. Both remain distinct assets,
correctly.

## Decisions

### Dedupe the asset list, not the files on disk

- **Options:** A — delete or skip-moving duplicate files at write time,
  inside `_normalize_pdf`'s move-from-temp loop. B (chosen) — leave every
  extracted file on disk exactly as `pymupdf4llm` wrote it; only
  `_collect_assets`'s returned `Asset` tuple collapses duplicates by hash.
- **Chose:** B.
- **Consequences:** zero risk of breaking `document.md`'s inline image
  references — `pymupdf4llm` (`write_images=True`, `embed_images=False`)
  writes Markdown image links pointing at each page's own extracted file;
  removing files at write time (A) could leave a reference pointing at
  nothing. B only changes what's reachable via `manifest.assets[]`, never
  the Markdown or what's on disk. Costs a small amount of duplicate disk
  space; correctness matters more here than that.

### First occurrence wins, sorted for determinism

- **Options:** A — whatever order the filesystem iteration happens to
  return. B (chosen) — sort by path before deduplicating; first occurrence
  in sorted order is kept.
- **Chose:** B.
- **Consequences:** matches this project's existing convention —
  `_collect_assets` already sorts before iterating, `_extract_embedded`
  already sorts `embfile_names()`. The same PDF, run twice, keeps the same
  instance of a duplicated image both times.

### Superseded: `image_size_limit` kwarg does nothing under the active layout engine

- **What changed:** the original decision here (pass `image_size_limit=0.10`
  to `pymupdf4llm.to_markdown(...)`) was implemented, then confirmed dead —
  `pymupdf.layout` is installed in this environment, `pymupdf4llm` prefers
  it by default, and the layout code path never reads that kwarg at all
  (see Why). The threshold was never actually applied; every image, of
  every size, was written regardless.
- **Replacement:** a post-write pixel-dimension filter — see Shape.
  Compares each written file's own size against its source page's
  full-page-equivalent size at a `dpi` we now pass explicitly, entirely
  independent of `pymupdf4llm`'s kwargs.
- **Consequences:** couples this code to `document_layout.py`'s filename
  convention (`f"{filename}-{page:04d}-{index:02d}.{ext}"`) to recover
  which page a written file belongs to — an internal convention of a
  third-party library, not a public API, and a real fragility a future
  `pymupdf4llm` upgrade could break silently. Mitigation: parse strictly
  and raise (not silently skip filtering) if a filename doesn't match the
  expected pattern, so a library-side naming change fails loud instead of
  quietly disabling the filter.

### Superseded: filter required both dimensions small, not either

- **What changed:** the original implementation filtered only when width
  **and** height both fell under 10% — real-world verification against
  two actual documents found this too narrow. A small, roughly square
  logo (Cayuse's) was correctly filtered. A wide letterhead banner
  (Charles River's, ~27-31% of page width but a thin strip vertically)
  was not — its width clears 10% even though its height doesn't, and
  `and` requires both to fail.
- **Replacement:** width **or** height under 10% is enough to filter —
  see Shape. This also corrects an inconsistency with `pymupdf4llm`'s own
  legacy (pre-layout-engine) `image_size_limit` implementation
  (`pymupdf_rag.py`), which used `or`, not `and`, for the same check —
  the original choice here diverged from the library's own precedent
  without a reason to.
- **Consequences:** a real content image that happens to be a wide, thin
  strip (e.g. a horizontal color scale, a single-row timeline) could now
  be filtered from `manifest.assets[]` too — accepted, since it's rare for
  this project's actual documents and, unlike deletion, the file stays on
  disk and directly readable via `inspect_image` by path; nothing is
  lost, only excluded from automatic iteration.

## Not doing

- **Similarity-based (non-exact) deduplication** — e.g. perceptual
  hashing for near-identical-but-not-pixel-identical images. Exact-hash
  dedup covers the actual observed case (a literally repeated logo); no
  evidence a fuzzier match is needed.
- **Deleting duplicate files from disk or rewriting Markdown image
  references** — rejected in Decisions; the correctness risk isn't worth
  the disk-space savings.
- **Changing `workspace-summary`'s "inspect every image for a general
  summary" behavior** — deliberately kept intact. This doc only reduces
  how many *distinct* images exist to consider; it doesn't change when or
  whether they get inspected.

## Open questions

None blocking.

## Implementation

**Dedup: implemented and confirmed correct.** `_collect_assets` tracks
seen SHA-256 hashes while iterating `assets_dir` in its existing
sorted-path order, skipping a path once its hash has already produced an
`Asset` — first occurrence wins, nothing on disk is touched. Regression
test: `test_collect_assets_dedupes_identical_content` writes two
byte-identical files and one distinct file directly into a
`DocumentNormalizer`'s `_assets_dir`, asserts `_collect_assets` returns
one `Asset` per unique hash (first path wins) and that the skipped
duplicate file is still on disk, untouched. Independently re-verified
against a real multi-page document: a logo repeated across 7 pages,
byte-identical, collapses to exactly 1 asset entry.

**Size filter: implemented, but with the `and`/`or` bug described in the
superseded Decision above — not yet corrected.** `_parse_pdf` now passes
`dpi=150` explicitly (`_IMAGE_DPI`, matching the library's own prior
implicit default — not a behavior change to rendering, just a fixed
value the filter below can compare against). `_collect_assets` opens the
source PDF once and, for every file already moved into `assets_dir`,
parses its page number from the filename and excludes it from the
returned `Asset` list (same "never touch disk" principle as dedup) when
**both** its own pixel width and height fall under 10% of its source
page's full-page-equivalent pixel size at that dpi — the condition that
real-world verification found too narrow (misses wide-but-short
banners). Needs changing to **either** width or height under 10%; see
Next.

One correction found while implementing: the filename convention's
prefix is *not* the `filename=` kwarg passed to `to_markdown()` — traced
to `parse_document`'s own `document.filename = mydoc.name if mydoc.name
else filename`, so it's the opened `pymupdf.Document`'s own `.name`
(the source PDF's path) whenever one is given, which is always, here.
Confirmed empirically: `filename="document"` produced
`original.pdf-0001-00.png`, not `document-0001-00.png`. The strict
pattern match (`_IMAGE_FILENAME_PATTERN`) is written prefix-agnostic —
it matches the stable trailing `-page-index.ext` shape regardless — so
this doesn't weaken the "fail loud on a library-side naming change"
mitigation; it just means the prefix was never an assumption worth
encoding in the first place.

Regression tests: `test_collect_assets_filters_undersized_images` (a
200x200px image survives, a 10x10px one on the same 200x200pt page
doesn't; the filtered file itself stays on disk),
`test_collect_assets_rejects_unexpected_image_filename` (a non-matching
name raises `DocumentParseError` rather than passing through
unfiltered), and `test_collect_assets_dedupes_identical_content`
rewritten to use realistic filenames and real, size-appropriate PNGs so
it exercises both filters together. Independently re-verified against a
real two-page PDF (a 400x400px content image, a 12x12px decorative
graphic): both files land in `assets_dir`; only the large one appears in
`result.assets`.

Full preflight run (before the `and`/`or` correction above): 141 passed,
`ruff check .` and `ty check src` clean.

## Next

Done. `_is_undersized_image` now excludes a file when its pixel width
**or** height falls under 10% of the page's full-page-equivalent
dimension — either alone is sufficient. Docstring and the
`_IMAGE_SIZE_RATIO` comment updated to say "either, not both". New
regression test `test_collect_assets_filters_wide_but_short_banner`: a
750x15px banner on a 400x200pt page (width clears 10%, height doesn't) is
filtered; a 600x300px image on the same page (large in both dimensions)
still survives. Existing `test_collect_assets_filters_undersized_images`
(small-in-both-dimensions case) still passes.

Full `tests/test_document_normalizer.py` run: 13 passed, plus 3
pre-existing failures unrelated to this change (`test_office_source_*`,
`test_office_conversion_failure_is_typed` — a Windows-only environment
limitation: `subprocess.run` can't exec a `#!`-shebang script directly,
confirmed present before this change too). `ruff check` and `ty check` on
both changed files clean.
