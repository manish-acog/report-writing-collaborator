# Design — Citation Marker Index Retry

## Purpose

For whoever changes `variable_config.py`, `report_orchestrator.py`, and
`evidence-grounding/SKILL.md`. Records the fix for an intermittent
production failure: a `found` field's `[[cite:N]]` marker sometimes
references an index beyond its own `citations` array's length, caught today
only at final `report_renderer.render()` — after every other `call_group`
in the run has already completed. Extends `citation_marker_enforcement.md`,
which fixed a sibling marker failure (comma-joined brackets) with fail-loud
validation; this is the same defect class — marker/citations drift — with a
different manifestation, caught late enough to waste real, already-paid-for
work.

## Why

The model self-tracks how many citations it has declared for a field,
purely from memory, while simultaneously writing prose that references them
by 0-based position — confirmed by reading the schema: no field carries an
explicit index, no schema-level text reinforces the rule, and `value` is
schema-ordered before `citations`, so markers are written before the array
they reference is committed. Whoever operates report generation needs
fewer runs to hit this at all, and when a group's turn does produce a bad
marker, only that group should retry — with the actual error visible to the
model — before the whole run pays the cost, instead of surfacing only after
all 11 turns already ran.

## Shape

- **`variable_config._field_type`** — field order changes: `citations`
  declared before `value` in the `found` model (shared by every
  report-writing skill through `build_output_schema`). Adds
  `Field(description=...)` restating the 0-based-index rule on both
  fields, next to where the model generates them, not only in
  `evidence-grounding/SKILL.md`'s shared prose.
  - exposes: `build_output_schema(call_group) -> type[BaseModel]` —
    signature unchanged; the schema it returns changes shape.
- **New: a cross-field validator** on the `found` model — checks every
  `[[cite:N]]` in `value` against `len(citations)` immediately after that
  JSON parses.
  - exposes: nothing new externally — raised as a `pydantic.ValidationError`
    from the same `model_validate_json` call ADK already makes.
- **`report_orchestrator._run_bounded_call`** — gains a bounded retry: on a
  schema validation failure for one `call_group`'s turn, sends the
  validation error back into the same session as a corrective turn,
  re-asks, capped at a small fixed count; raises today's existing
  `RuntimeError` only once retries are exhausted.
  - hands off: nothing new externally; internal control flow only.

## State

None new. `sessions.db` (from the earlier persistence work) already records
every retry attempt as its own turn — reviewing a failed run shows exactly
what was retried and why, for free.

## Scenarios

**A field with 2 declared citations, model writes `[[cite:2]]`.** The
validator raises inside that group's own turn, as soon as the JSON parses.
The orchestrator catches it, appends the validation error text (*"Citation
marker index 2 is out of range for field 'x' — only 2 citations declared
(valid: 0-1)"*) as a new turn in the shared session, and re-runs that same
`call_group`'s bounded call. The model corrects — fixes the marker or adds
the missing citation — and the orchestrator proceeds to the next group as
normal.

**Retries exhausted.** Two consecutive bad attempts: the orchestrator
raises the same `RuntimeError` it already raises for other unrecoverable
model-call failures. No new failure surface, no silent tolerance — matches
`citation_marker_enforcement.md`'s "ships fully resolved or doesn't ship."

**Extending.** A third report-writing skill, built later, reuses
`build_output_schema` unchanged — reordered fields, the description text,
and the validator all apply automatically, because they live in the shared
`_field_type`, not per-skill code.

## Decisions

### Reorder schema fields: `citations` before `value`

- **Options:** A (simplest, chosen) — swap field order only. B — leave
  order as-is, rely solely on the validator + retry to catch what
  prevention doesn't.
- **Chose:** both A and the validator/retry below — not exclusive.
  Reordering is free prevention; the validator/retry is the safety net
  regardless of how much reordering helps.
- **Consequences:** the model commits its evidence list before referencing
  it by position, in generation order, for every skill using this schema
  builder — no per-skill opt-in needed.

### Cross-field validator lives in the generated Pydantic model, not `report_renderer`

- **Options:** A — leave the check in `report_renderer`, only ever fires
  when it does today. B (chosen) — a `model_validator` on the `found`
  model itself, firing at the same point ADK's own `validate_schema`
  already runs, right after that turn's model call.
- **Chose:** B.
- **Consequences:** failure surfaces immediately after the offending turn,
  not after every subsequent turn also ran. `report_renderer`'s own bounds
  check (`report_renderer.py:143-148`) stays — a correct last-resort
  guarantee for anything that somehow bypasses the validator — not removed,
  just no longer the first or only place this is caught.

### Bounded retry with the validation error as session feedback, not a blind retry

- **Options:** A — retry blindly, re-asking with the identical prompt,
  hoping stochastic variance fixes it. B (chosen) — feed the actual
  validation error back as a new turn in the same session, then retry.
- **Chose:** B.
- **Consequences:** the model sees precisely what it got wrong, in a
  session it already has context for — real odds of self-correction, not
  a second independent roll of the dice. Retry count stays small and
  fixed (e.g. 2); not designed to be configurable — no evidence anything
  but a small fixed cap is needed yet.

### Retry scoped to the failing `call_group` only

- **Options:** A (simplest, chosen) — only the failing group's turn
  retries; every other group's already-completed work stands. B — restart
  the whole `write_report()` run from the bootstrap turn on any group's
  failure.
- **Chose:** A.
- **Consequences:** matches the actual reason this was worth fixing — one
  group's mistake no longer costs the other 9-10 groups' already-paid-for
  work.

## Not doing

- **Replacing positional integer markers with model-assigned string
  citation IDs** — a bigger schema/renderer change across both skills;
  nothing shows the three changes above won't already fix most of this.
  Revisit only if the retry still fails at a rate that matters.
- **Configurable retry count or retry policy** — fixed, small cap; no
  stated need for it to vary per skill or call site.
- **Removing `report_renderer`'s existing bounds check** — stays as the
  last-resort guarantee; this doc adds earlier detection, doesn't replace
  the final one.

## Open questions

- **Exact retry cap** — 2 attempts, or something else? No data yet on how
  often the first retry actually succeeds; start with a small number,
  revisit once this has run against real reports.
- **Corrective feedback shape** — send the validation error's own message
  verbatim, or a rewritten instruction? Start with the message as-is
  (already descriptive: *"Citation marker index N is out of range for
  field 'X'"*); no evidence a rewritten form does better.

## Implementation

Implemented in `variable_config._field_type` (`citations` before `value`,
`Field(description=...)` on both, `check_citation_markers` model_validator),
and `report_orchestrator._run_bounded_call_async` (bounded retry loop,
`_corrective_prompt`/`_validation_messages`). Regression test:
`test_build_output_schema_rejects_out_of_range_citation_marker`
(`tests/test_variable_config.py`) — written first, confirmed failing
against the old schema, then passing. Retry behavior covered by
`test_run_bounded_call_retries_once_on_validation_error_then_succeeds` and
`test_run_bounded_call_raises_after_retries_exhausted`
(`tests/test_report_orchestrator.py`). Retry cap fixed at 2 total attempts
(one corrective retry).
