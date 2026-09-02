# Design — Search-First Workspace Access

## Purpose

For whoever removes `list_sections`/`read_section` from `make_workspace_tools`,
adds `context_lines` to `grep_workspace` and `offset`/`limit` to
`read_workspace_file`, and updates everything that currently references the
removed tools: `report_orchestrator._BOOTSTRAP_PROMPT`, and the
`workspace-summary`, `general-report-writing`, `academic-report`, and
`cayuse-protocol-understanding` skills. Supersedes
`docs/bootstrap_index_scaling.md`'s `list_sections`/`read_section` Shape and
Decisions.

## Why

`list_sections`/`read_section` existed to avoid reading a whole document when
only a fraction is relevant — a real problem for a document with a handful of
large sections. Real use surfaced a document shape that inverts that
assumption: a Cayuse-exported protocol with roughly 200 sections across
roughly 30 pages. `structure_indexer._build_sections` creates one section per
detected heading with no size coalescing, and Cayuse renders every form
question as its own heading — one section per form field, not per topic. At
that granularity, `list_sections`' own 200-entry table of contents costs more
in replayed context (the same shared-session cost `docs/bootstrap_index_scaling.md`
already fixed once for full document content, resurfacing one layer down for
the *index*) than the surgical reads it was meant to save.

Checked how this is actually solved elsewhere before designing a fix here.
Claude Code uses plain, context-aware `Grep` (ripgrep-backed, genuinely
supports before/after context) and an offset-ranged `Read` — no bespoke
fetch-by-structural-unit tool. Aider's repo-map is a structural *discovery*
aid (which files are relevant) computed via tree-sitter, never a specialized
per-unit fetch mechanism — once something is relevant, Aider reads the actual
file. Neither precedent supports keeping `read_section` as a dedicated tool;
both support `document.sections.json` staying a plain, directly-readable
artifact for genuine structural discovery, which is already true today
(`workspace_builder.py:422-428` — a normal workspace-relative file, listed in
`manifest.json`'s `sections_path`).

## Shape

- **`make_workspace_tools`** — `list_sections` and `read_section` removed.
- **`grep_workspace`** — gains `context_lines: int = _DEFAULT_CONTEXT_LINES`
  (default 2, floor 0, cap `_MAX_CONTEXT_LINES = 3`). Each match gains a
  `"context"` field: the block of `context_lines` before through
  `context_lines` after the matched line, joined by newlines.
  `section_id`/`source_pages` continue to resolve from the matched line only.
- **`read_workspace_file`** — gains optional `offset`/`limit` (1-indexed
  starting line, line count). Omitted: whole file, unchanged from today.
- **`document.sections.json`** — untouched. Still written by
  `structure_indexer`/`workspace_builder`, still listed in `manifest.json`,
  still readable via plain `read_workspace_file` whenever a genuine
  structural-discovery need exists.
- **`report_orchestrator._BOOTSTRAP_PROMPT`** — no longer asks the model to
  enumerate every source's sections; see Decisions.
- **Skills updated**: `workspace-summary`'s narrow-question path (currently
  points at `list_sections`/`read_section`), `general-report-writing`/
  `academic-report` step 1 (currently says "use the index plus
  `list_sections`/`read_section`"), `cayuse-protocol-understanding` (gains
  new guidance — grep with context over browsing 200 sections, since this
  document shape is the one that motivated this doc).

## State

None new. No schema change to any persisted workspace artifact — this is a
tool-surface change, not a data-model one.

## Scenarios

**Cayuse "Route of Administration" lookup.** One `grep_workspace` call,
default `context_lines=2`, returns the prompt line and the answer line
after it in the same response. The old design needed two calls for this —
`list_sections` to find the right `section_id`, `read_section` to fetch it.

**A confirmed-relevant spot needing more than a little context.**
`read_workspace_file(path, offset=830, limit=40)`, widened progressively
(`offset=800, limit=100`) if the first window isn't enough — no re-search,
each widening is an independent, cheap call against an already-known
location.

**A genuine "what's in this source" discovery need.** Rare —
`workspace-summary`'s own general-summary path already reads whole
normalized documents for exactly this. When it comes up elsewhere:
`read_workspace_file("normalized/<source_id>/document.sections.json")`
directly — the same tool used for everything else, not a specialized one.

**Extending: a second document type with the same many-small-sections
shape.** No code change needed — the fix here is generic (`grep_workspace`'s
`context_lines`, `read_workspace_file`'s `offset`/`limit`), not Cayuse-specific.
Only a new document-shape skill (analogous to `cayuse-protocol-understanding`)
would need the same "prefer grep over structural browsing" guidance, if a
future format shows the same pattern.

## Decisions

### Bootstrap no longer builds a per-source section index at all

- **Options:** A — bootstrap still reads `document.sections.json` (via
  `read_workspace_file`) for every source, building the same structural
  index as before, just through the generic tool instead of `list_sections`.
  B (chosen) — bootstrap builds only the source tree (`manifest.json`:
  sources, roles, hierarchy) — no per-source section enumeration; call_group
  turns grep and read entirely on demand, with `document.sections.json`
  available if a specific need calls for it.
- **Chose:** B.
- **Consequences:** bootstrap's own turn gets leaner than
  `docs/bootstrap_index_scaling.md` already made it — matches how coding
  agents actually start work, searching as needed rather than pre-building a
  structural index nothing may end up using. A source's full section index
  gets read only by whichever call_group turn genuinely wants a discovery
  pass over it, not built upfront for every source regardless of need.

### Drop the bespoke section-fetch tools, keep the artifact they wrapped

- **Options:** A — keep `list_sections`/`read_section`, just deprioritize
  them in instructions. B (chosen) — remove both tools; `document.sections.json`
  stays exactly where it is, readable via the tool that already reads
  everything else.
- **Chose:** B.
- **Consequences:** one fewer tool pair to maintain, document, and keep
  consistent with `grep_workspace`/`read_workspace_file`'s own conventions.
  No functionality lost — anything `list_sections`/`read_section` could do,
  `read_workspace_file` on the same underlying file already does.

### `context_lines` defaults non-zero, capped tight

- **Options:** A — default `0` (matches ripgrep's own convention), model
  opts in when it wants context. B (chosen) — default `2`, capped at `3`.
- **Chose:** B.
- **Consequences:** context is present automatically, not dependent on the
  model remembering to ask for it — the same reliability concern already
  named for tool availability generally (a tool being callable doesn't mean
  it's faithfully used). The cap stays tight on purpose: this tool's job is
  cheap context across *many* matches, not becoming a second way to read a
  large chunk — that's `read_workspace_file(offset, limit)`'s job,
  deliberately kept separate.

### No shell access — reconsidered explicitly this session, same conclusion

- **Options:** A (chosen, unchanged) — plain functions, no shell. B — a
  sandboxed, read-only, allowlisted shell.
- **Chose:** A, per `docs/agent_execution_over_adk.md`'s original "Tool
  surface" decision, re-examined rather than assumed.
- **Consequences:** no metacharacter/injection surface exists — directly
  relevant given `docs/source_content_trust_boundary.md`'s own concern
  (arbitrary, untrusted source content). A shell means the model constructs
  a string that gets *parsed*; `re.compile()` failing on a bad pattern just
  returns an error dict. Re-considering this explicitly, rather than
  inheriting the old decision unexamined, reached the same conclusion,
  strengthened by the trust-boundary doc that didn't exist when the original
  decision was made.

## Not doing

- **Semantic/embedding search** — no evidence plain grep plus curated domain
  vocabulary (`cayuse-protocol-understanding`'s own section-vocabulary
  guidance, functionally serving the same role Cursor's embeddings do, at
  far lower cost given a known, fixed domain) is insufficient. Cursor's own
  research shows real limits to grep-alone for conceptual queries — worth
  revisiting only with equivalent evidence here, not preemptively.
- **Removing `document.sections.json` or any indexing pipeline code** — only
  the two tool wrappers around it are removed; the underlying artifact and
  everything that produces it (`structure_indexer.py`) is untouched.
- **Resolving `section_id`/`source_pages` from the context window instead of
  the matched line** — unnecessary complexity; a context window rarely
  crosses a section boundary, and citation grounding doesn't need it to.

## Open questions

None blocking.

## Next

Remove `list_sections`/`read_section` from `make_workspace_tools`. Add
`context_lines` to `grep_workspace` (default 2, cap 3) and `offset`/`limit`
to `read_workspace_file`. Reword `_BOOTSTRAP_PROMPT` to build only the
source tree, not a per-source section index. Update `workspace-summary`'s
narrow-question path, `general-report-writing`/`academic-report` step 1, and
add new `cayuse-protocol-understanding` guidance preferring grep-with-context
over structural browsing. Regression tests: `grep_workspace` context window
correctness at each boundary (start of file, end of file, `context_lines=0`);
`read_workspace_file` offset/limit correctness (partial file, offset beyond
EOF); confirm removed tools are gone from the returned tool list. Full
preflight after.
