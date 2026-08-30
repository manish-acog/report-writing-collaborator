# Design — `workspace-summary` Skill Rewrite

## Purpose

Defines the rewritten `workspace-summary` skill's content and structure, for
whoever authors the new `SKILL.md`. Grounded in the manifest's current shape
(source graph, roles, assets) and the agent's existing `inspect_image` tool.

## Why

The current skill predates attachment normalization and `inspect_image`. It
treats every source as a flat list and never mentions the promotion hierarchy,
assets, or image content. A workspace summary should give the full picture —
structure and content — not just per-source text.

## Shape

One skill, one file: `report_writing_agent/skills/workspace-summary/SKILL.md`.
No new tool; the rewrite only reorders and extends how the existing four tools
(`glob_workspace`, `grep_workspace`, `read_workspace_file`, `inspect_image`)
get used.

The frontmatter `description` is the routing rule the agent uses to decide
whether to load this skill at all — not documentation for a human reader — so
it must name what triggers it, not just what it produces.

Image detection uses the same extension set `inspect_image` already accepts
(`_VISION_IMAGE_TYPES` in `agent.py`), so the skill never tries to inspect a
format the tool will reject.

- exposes: frontmatter (`name`, `description`) + instructions body, loaded via
  the agent's existing `load_skill`/`SkillToolset` mechanism
- hands off: nothing — the skill only sequences tool calls already available

## State

None. Static skill content; no new persisted artifact.

## Scenarios

**General summary.** "Summarize this workspace." The skill reads
`manifest.json`, builds the source tree from `parent_source_id`, notes each
source's `source_role`, and lists `assets[]` per source. It inspects every
image via `inspect_image` — a complete picture means every image gets read,
not a subset chosen by count. Output opens with the structural picture
(sources, roles, hierarchy, asset/image counts), then per-source content,
cited by `source_id` and page.

**Narrow question.** "What test article lot number is used?" The skill still
builds the structure internally — knowing a source is a child of another
matters for deciding relevance — but the rendered output skips the structural
section and answers directly, citing evidence, matching the skill's existing
narrow-question branch.

**No images present.** The image step contributes nothing; the skill proceeds
without it. No special case needed — inspecting an empty set of images is a
no-op.

## Decisions

### Description names its own triggers

- **Options:** A (current) — "Produces an evidence-grounded summary... Use
  when asked to summarize, describe, report on, or answer a question about the
  contents of a workspace." B — extend it to explicitly name structural
  questions ("what sources," "what's in this workspace," "what images") as
  triggers.
- **Chose:** B.
- **Consequences:** the skill now routes reliably for structural questions the
  old description wouldn't reliably catch. Under-triggering is the default
  failure mode for skill descriptions, so triggers need to be named, not
  implied.

### Structural section only for general summaries

- **Options:** A — always render the structural section. B (chosen) — build
  it internally every time (cheap, one manifest read); render it as output
  only for general/overview requests.
- **Chose:** B.
- **Consequences:** narrow questions stay focused. The skill still uses the
  structural pass internally either way — it just doesn't surface it unless
  the request is asking for an overview.

### Exhaustive image inspection

- **Options:** A — scale inspection depth to image count. B (chosen) —
  inspect every image found, for a general summary.
- **Chose:** B — a "full, complete picture" means every image gets read, not
  a subset chosen by volume.
- **Consequences:** a workspace with many images makes a general summary
  slower, one model call per image — the deliberate cost of comprehensiveness.
  Narrow questions don't pay this cost; they only inspect images the question
  actually needs.

### Rules stated with their reason, not as capitalized directives

- **Options:** A — write steps as ALWAYS/NEVER/MUST directives. B (chosen) —
  state each rule with why, so the model generalizes to cases the skill
  didn't spell out.
- **Chose:** B, per Anthropic's own skill-authoring guidance: rigid
  capitalized rules produce literal rule-following that misses edge cases the
  skill never anticipated.
- **Consequences:** slightly longer prose per rule; better generalization to
  workspace shapes not explicitly enumerated (a source with no assets, a
  workspace with exactly one source).

### Single file, no `references/` split

- **Options:** A — split extended detail into a `references/` file loaded on
  demand (the progressive-loading pattern Anthropic's guidance describes for
  larger skills). B (chosen) — keep one `SKILL.md`.
- **Chose:** B.
- **Consequences:** the rewritten body — structure pass, image policy,
  existing content pass — stays short enough that a second file would add
  indirection without payoff. Revisit only if the body outgrows a single read.

## Not doing

- **A `kind`/mime field on `ManifestAsset`** — the skill infers image vs.
  other asset from the file extension. Not needed unless that inference
  proves unreliable in practice.
- **A numeric image-count cutoff** — superseded by "inspect every image."
- **New tools** — the existing four already cover everything this rewrite
  needs.
- **Real-usage refinement loop** — Anthropic's guidance recommends testing a
  skill against real tasks and tightening it from observed failures; that's a
  follow-up activity once this version exists, not part of this design.

## Open questions

None blocking.

## Next

Write the rewritten `SKILL.md`: structural pass (source tree, roles, assets)
→ exhaustive image inspection for general summaries → existing per-source
content pass. Output shape: structural section only for general summaries,
content section always, grounding rule unchanged.
