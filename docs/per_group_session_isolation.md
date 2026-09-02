# Design — Per-`call_group` Session Isolation

## Purpose

For whoever moves `write_report()` from one shared session across bootstrap
and every `call_group` to an isolated session per `call_group`, replaces
raw session replay with targeted prior-value injection for coherence, and
bounds `read_workspace_file`'s `limit`. Fixes a real, hard failure: a
production run hit an org-enforced TPM rate limit around the 6th
`call_group`, with roughly 190k tokens already accumulated in the shared
session by that point, compounded by one turn firing 7 parallel,
unbounded `read_workspace_file` calls. Supersedes
`docs/extraction_session_persistence.md`'s core "one shared session"
decision, part of `docs/bootstrap_index_scaling.md` (the bootstrap turn
itself, not just its payload), and `docs/task_run_artifacts.md`'s "one
session row per run" State/Scenarios.

## Why

One shared session was chosen so `call_group`s wouldn't redundantly
rediscover workspace structure, modeled on empirically-good chat-session
behavior. Both premises have eroded since: bootstrap now builds nothing
but a source tree (`docs/bootstrap_index_scaling.md`, then
`docs/workspace_search_tools.md`), and `study_variables.json`'s own
group descriptions show only one real cross-group dependency —
`conclusions` on `results` — not the general case. What one shared
session actually bought, by the time this failed, was a small bootstrap
prefix, for a cost that's now a hard TPM rejection, not just inefficiency.

The chat-versus-batch distinction is the real dividing line, not a rough
preference. Chat is open-ended — you can't know the next question in
advance, so continuity can't be replaced by precomputed context.
`write_report()` is the opposite: a fixed schema, a known field list per
group, a known dependency graph declared right in the config. That
predictability is what makes session continuity *replaceable* by handing
each turn exactly what it needs, instead of replaying everything and
hoping the model finds what's relevant in it.

Separately: retrying an oversized request doesn't fix it — a request that
exceeds a rate limit fails identically on retry unless something about it
changes. The 7-parallel-unbounded-reads spike is a distinct, structural
gap: `read_workspace_file`'s `limit` has no cap.

## Shape

- **`report_orchestrator.write_report`** — no longer builds one session
  for the whole run. For each `call_group`, builds a fresh
  `DatabaseSessionService` session (still inside `.tasks/<task_id>/sessions.db`
  — one file, now one row per group instead of one row total), runs that
  group's bounded call in isolation, and moves on. No bootstrap turn.
- **Bootstrap becomes deterministic code, not a model call.** A new
  `_render_source_tree(manifest_path) -> str` reads `manifest.json`
  directly and renders the source tree (sources, roles, hierarchy via
  `parent_source_id`) as plain text — the same information
  `workspace-summary`'s structural pass produced, computed without a
  model call, since it's pure data transformation over already-structured
  JSON. No judgment involved, nothing to delegate.
- **`_build_instruction`** — every `call_group`'s instruction gets two
  static, injected sections instead of session-carried context: the
  source tree (from `_render_source_tree`, identical for every group in
  a run) and *already extracted* — bare `field_name: value` pairs from
  every previously-completed group, built from the same `values` dict
  `write_report()`'s loop already accumulates. No citations in this
  section — citations are for the final render, not for a later
  extraction turn judging consistency.
- **`read_workspace_file`** — `limit` capped at `_MAX_READ_LINES`,
  applied even when omitted (no more "whole file" as a default).
- **`_summarize_usage`** — sums across every session row for the task,
  not one.

## State

`.tasks/<task_id>/sessions.db` still one file, same location, same
schema (`docs/task_run_artifacts.md`'s own design already supports many
sessions per file — this uses that, doesn't change it). Now holds one
row per `call_group` instead of one shared row. No new artifact type.

## Scenarios

**A 10-`call_group` run.** No bootstrap turn. Each group's instruction
opens with the same static source tree, then whatever's already been
extracted by groups before it in the array, then its own field list.
Each group's session starts empty otherwise — its own grep/read work,
nothing accumulated from siblings. Token growth per call is now bounded
by (source tree + prior values so far + this group's own work), not by
the sum of every prior group's full exploration trace.

**`conclusions` needing `results`.** No special-casing required —
`results` precedes `conclusions` in `study_variables.json`'s own array,
so its extracted value is already in the "already extracted" section by
the time `conclusions`'s instruction gets built. The one real declared
dependency falls out of the general mechanism, not a separate rule.

**Seven parallel reads in one turn.** Each capped at `_MAX_READ_LINES`
regardless of how many fire together — bounds the worst case
deterministically; a model wanting more issues another call with a later
`offset`, the same progressive-widening pattern already established.

**One broad `grep_workspace` call.** A single call_group's first turn
issuing `grep_workspace(pattern="A|B|C|...", glob_pattern="**/*",
context_lines=3)` — a wide OR-pattern across every workspace file — hit a
TPM rejection on its own, faster than the original gradual-accumulation
failure this doc otherwise fixes: 198 matches, 500K+ combined characters
in one response, well inside a single call_group. `_MAX_GREP_MATCHES`
alone didn't bound this — a fixed match count says nothing about how
much text each match carries. `_MAX_GREP_RESPONSE_CHARS` stops
collection once the combined `line`+`context` text crosses the budget,
regardless of match count or line length, the same principle as
`_MAX_READ_LINES`.

**Debugging a run afterward.** `sessions.db` shows N independent turns,
each inspectable on its own — arguably clearer than before, since a
group's own session isn't tangled with nine others' history to page
through.

## Decisions

### Isolate sessions per `call_group`, inject values instead of replaying raw history

- **Options:** A — keep one shared session (status quo, hits the TPM
  ceiling). B — shared session plus compaction (ADK-native
  `EventsCompactionConfig`), reducing but not eliminating growth. C
  (chosen) — isolated sessions, targeted value injection for coherence.
- **Chose:** C.
- **Consequences:** eliminates the growth curve at its source rather than
  managing it — no compaction tuning, no risk of an LLM-based summarizer
  smoothing over grounding precision (a real, independently-documented
  risk of compaction). Real cost, quantified: injected prior values are
  short extracted text, not raw exploration traces — 61 fields, even at
  a generous 100-300 words each, tops out around 8,000-24,000 tokens for
  the last group seeing everything before it, against the 190k the old
  design hit by call 6. An order of magnitude (or two) cheaper for
  materially the same coherence benefit.

### Bootstrap becomes deterministic code, not an LLM turn

- **Options:** A — keep a lean bootstrap LLM turn (as
  `docs/bootstrap_index_scaling.md` already reduced it to), just run it
  once and inject its output as static text into every group instead of
  via session continuation. B (chosen) — replace the turn entirely with
  a plain function reading `manifest.json` directly.
- **Chose:** B.
- **Consequences:** the source tree is pure data transformation over
  already-structured JSON (`sources[]`, `parent_source_id`,
  `source_role`) — no natural-language judgment was ever actually
  involved, it was only a model call because the original design routed
  everything through `workspace-summary`'s skill instructions. Matches
  this project's consistent preference for deterministic code over a
  model call wherever no genuine judgment is required (`report_renderer`
  is the same shape: "no model access, pure function"). One fewer LLM
  call per run, zero risk of this specific step ever contributing to
  token growth or a rate-limit failure, since it no longer touches the
  model at all.

### `read_workspace_file`'s `limit` is capped, including when omitted

- **Options:** A — cap only when a caller passes an excessive value,
  leave the omitted case as "whole file" (today's behavior). B (chosen)
  — cap unconditionally; omitted `limit` gets the cap too, not the whole
  file.
- **Chose:** B.
- **Consequences:** bounds the worst case regardless of model behavior —
  this is what actually caused the reported failure (7 reads, `limit`
  omitted on at least some of them, each returning a whole file). A
  model wanting more of a file makes another call with a later `offset`
  — the exact progressive-widening pattern `read_workspace_file` was
  already designed around.

### `grep_workspace` caps total response characters, not only match count

- **Options:** A — lower `_MAX_GREP_MATCHES` further (from 200), hoping a
  smaller count bounds worst-case size well enough in practice. B —
  truncate each match's `line`/`context` field to a fixed length,
  independent of total match count. C (chosen) — track combined
  `line`+`context` characters across all matches; stop once
  `_MAX_GREP_RESPONSE_CHARS` is crossed, same trigger shape as the
  existing match-count cap.
- **Chose:** C.
- **Consequences:** bounds the worst case regardless of match count *or*
  line length — the actual failure (198 matches, 500K+ characters) was
  within the existing count cap the whole time; only a size-based check
  catches it. A alone would still fail for wide OR-patterns with long
  matched lines; B alone would still fail for many-small-matches (JSON
  overhead across hundreds of short entries). Kept `_MAX_GREP_MATCHES` as
  a second, cheap backstop for that many-small-matches case — the two
  caps defend different degenerate shapes, not redundant with each
  other.

## Not doing

- **ADK-native compaction (`EventsCompactionConfig`)** — considered,
  rejected in favor of eliminating the growth curve rather than managing
  it; see Decisions. Revisit only if isolation plus value injection
  still shows unexpected growth in practice.
- **Sliding-window truncation or sub-agent isolation via a `Workflow`
  graph** — the broader options surveyed for context management; neither
  is needed once accumulation itself is removed at the source.
- **Selective/relevance-filtered value injection** (only including prior
  groups judged related to the current one) — unnecessary complexity
  given the total cost of injecting everything is already small; revisit
  only if the linear growth across 10 groups is shown to matter in
  practice.

## Open questions

- **Retention/growth of prior-value injection across a much larger
  skill** (more than 10 groups, more than 61 fields) — not a concern at
  today's scale, per the quantified estimate above; revisit only if a
  future skill's shape changes that math materially.
- **Exact value for `_MAX_GREP_RESPONSE_CHARS`.** Set at 20,000 by
  order-of-magnitude reasoning against the observed 500K+ character
  failure, not by measuring real Cayuse/large-table document
  characteristics. Generous enough for the "cheap context across many
  matches" purpose at today's scale; revisit if a legitimate narrow
  search still needs more matches than the budget allows before finding
  what it's looking for.

## Next

Add `_render_source_tree(manifest_path) -> str` (plain function, no
model call). Change `write_report` to build one session per `call_group`
instead of one for the whole run; remove the bootstrap agent/turn
entirely. Add the "already extracted" section to `_build_instruction`,
sourced from the same `values` dict already accumulated. Cap
`read_workspace_file`'s `limit` unconditionally. Update `_summarize_usage`
to sum across every session row in `sessions.db` for the task, not one.
Add pointers from `docs/extraction_session_persistence.md`,
`docs/bootstrap_index_scaling.md`, and `docs/task_run_artifacts.md` to
this doc, per the project's supersede-don't-erase convention. Regression
test: a multi-group run's later `call_group` instruction contains an
earlier group's extracted value verbatim; `read_workspace_file` with no
`limit` still returns a bounded result; token count for a full run stays
well under the old accumulation curve. Full preflight after.

## Implementation

`_render_source_tree(manifest_path)` reads `manifest.json` directly,
groups `sources[]` by `parent_source_id`, and renders an indented
`- source_id (role): original_filename` tree, depth-first, siblings
sorted by `source_id` for deterministic output. `write_report` calls it
once per run (not once per group -- the tree itself doesn't change
across a run) and passes the result into every `call_group`'s
`_build_instruction` call alongside the running `values` dict.

`_build_instruction(skill, call_group, source_tree, values)` appends a
`## Source tree` section (always present) and an `## Already extracted`
section (present once any prior group's field has `status: "found"`) as
`- **field_name**: value` pairs, before the existing `## Fields for this
call` section. Table-typed values are rendered via `json.dumps`, not
left as raw dicts -- the only field types `study_variables.json` names
today are `text` and `table`.

Session isolation: `_open_session_service(task_dir)` opens
`sessions.db` without creating a session; `_build_session` calls it,
then `create_session`, once per `call_group` (previously once per run).
`_summarize_usage(session_service)` dropped its `session_id` parameter --
it now calls `list_sessions()` first, then sums each session's own
events, covering every row the run's `call_group`s created. Fetched via
one extra `_open_session_service` call after the main loop, before its
own `close()`, preserving the existing "fetch before close" rule
(`docs/task_run_artifacts.md`) with a fresh instance rather than a reused
per-group one.

`_MAX_READ_LINES = 500`, resolving the open question below: generous
enough for a genuine multi-paragraph read (the project's own documents
run well under that per normalized section), bounded enough that seven
parallel unbounded reads can no longer reproduce the incident --
7 x 500 lines is an order of magnitude below a large document's full
line count, not a whole-document replay.

`_run_bounded_call`/`_run_bounded_call_async` dropped the `expect_output`
parameter -- its only caller was the now-removed bootstrap turn; every
remaining call always expects structured output.

`general-report-writing`/`academic-report` `SKILL.md` step 1 reworded:
no more "this session's first turn already built..." (there is no first
turn) -- now describes the two static sections every instruction already
carries.

Regression tests: `test_write_report_injects_earlier_groups_values_into_later_instruction`
(a multi-group run's later instruction contains an earlier group's value
verbatim), `test_write_report_uses_a_fresh_session_per_call_group` (every
group's own distinct session_id, proving isolation rather than
measuring live token counts against a real model),
`test_summarize_usage_sums_across_every_session_row_for_the_task`,
`test_read_workspace_file_caps_lines_even_without_limit`, and
`test_read_workspace_file_caps_limit_above_max`. Full preflight run
after: 150 passed, `ruff check .` clean, `ty check src` clean.

**Addendum: `grep_workspace` response-size cap.** Deployed the above,
then hit a second, sharper production failure — a single call_group's
first turn issued one broad `grep_workspace` call (`glob_pattern="**/*"`,
wide OR-pattern) that alone returned 198 matches, 500K+ characters, a
hard TPM rejection ~30 seconds in. `_MAX_GREP_MATCHES` (200) never
engaged; it bounds count, not size. Added `_MAX_GREP_RESPONSE_CHARS =
20_000`: `grep_workspace` now tracks combined `line`+`context`
characters across matches and stops, marking `truncated: true`, once
that budget is crossed — same trigger shape as the existing count cap,
bounding the worst case regardless of match count or line length.
`_MAX_GREP_MATCHES` kept as a second backstop for many-small-matches,
which a size budget alone doesn't cap as cheaply (JSON overhead per
match). Regression test:
`test_grep_workspace_caps_total_response_chars_before_match_count` — a
300-line file of long matching lines truncates well short of 200
matches, proving the size cap (not the count cap) is what stops it.
Full preflight after: 151 passed, `ruff check .` clean, `ty check src`
clean.
