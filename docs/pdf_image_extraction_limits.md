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

1. **`image_size_limit` was never set, silently using the library
   default.** `_parse_pdf`'s `pymupdf4llm.to_markdown(...)` call
   (`document_normalizer.py:442-456`) doesn't pass `image_size_limit` —
   `pymupdf4llm`'s own default is `0.05` (5% of page width/height). A
   genuinely tiny icon gets filtered; a reasonably-sized letterhead or
   banner clears 5% easily and passes through untouched, same as a real
   figure would.
2. **No content-based deduplication anywhere in the extraction path.**
   `_collect_assets` (`document_normalizer.py:477-484`) enumerates every
   file `pymupdf4llm` wrote and hashes each for tracking, but never checks
   whether two files are byte-identical. `pymupdf4llm` writes one file per
   *occurrence*, not per unique image — a logo on 50 pages produces 50
   separate, identical files, each becoming its own `Asset`.

## Shape

- **`_parse_pdf`** — passes `image_size_limit=0.10` explicitly, a
  deliberate choice instead of an implicit dependency on the library's
  own default.
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
graphic).** Filtered by the raised `image_size_limit`, same mechanism as
before, just at a higher, deliberately-chosen bar.

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

### `image_size_limit` raised to `0.10`, set explicitly

- **Options:** A — leave it unset (library default `0.05`). B (chosen) —
  pass `image_size_limit=0.10` explicitly.
- **Chose:** B.
- **Consequences:** a visible, deliberate threshold instead of an implicit
  dependency on `pymupdf4llm`'s own default that a reader of `_parse_pdf`
  would otherwise have to go look up. Filters more decorative small
  graphics before they ever reach the dedup step above.

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

`_parse_pdf` passes `image_size_limit=0.10` explicitly to
`pymupdf4llm.to_markdown(...)`. `_collect_assets` tracks seen SHA-256
hashes while iterating `assets_dir` in its existing sorted-path order,
skipping a path once its hash has already produced an `Asset` -- first
occurrence wins, nothing on disk is touched. Regression test:
`test_collect_assets_dedupes_identical_content` writes two
byte-identical files and one distinct file directly into a
`DocumentNormalizer`'s `_assets_dir`, asserts `_collect_assets` returns
one `Asset` per unique hash (first path wins) and that the skipped
duplicate file is still on disk, untouched. The existing
`test_pdf_normalization_preserves_provenance` fixture's embedded image
(a 200x200-point image on an A4 page, well above 10% of page
width/height) confirmed unaffected by the raised threshold.
