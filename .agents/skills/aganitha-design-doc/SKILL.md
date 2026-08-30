---
name: aganitha-design-doc
description: Write a design doc before building anything non-trivial — a decisions-and-options document in the industry sense (Google design docs, RFCs), not an implementation spec. Use this skill when starting a new system, package, module, or non-trivial feature, or when someone says "design doc", "write up the design", "RFC", or "let's design this before coding". Interrogates the design until it stands up, then records the decisions, the options considered, and their consequences in docs/design.md. Replaces the older design-first skill.
---

# Design Doc

A design doc records **decisions, options, and consequences — never
implementation**. Implementation detail is best expressed in code; the doc
exists so a reader can understand *what was chosen, what else was on the
table, and why* — without reading any code. If a section could be recovered
by reading the code, it doesn't belong in the doc.

## Posture — probe the frayed ends

Designs rarely unravel at the centre. The core abstraction, the data model, the
main algorithm — those get attention because they are obviously hard. What
fails is the edge: a sentence standing in for a whole mechanism nobody has
worked out yet.

The job is not to disprove the design. It is to put light on the parts that got
a phrase instead of a decision, and make the author think them through.

**Phrases that stand in for an unmade decision:**

| Written | Ask |
|---|---|
| "the user provides the input" | Through what — a CLI, a web form, WhatsApp, a file drop? Typed, uploaded, or pasted? In what format? |
| "the system informs them" | Pushed or fetched? Landing where? What happens when nobody is there to receive it? |
| "the system knows X" | Declared, discovered, or derived? If discovered — by what, and when? If declared — by whom, and where does that live? |
| "on a change" / "periodically" | What starts the run — a person, a schedule, a webhook, a poll? |
| "it reads from the source" | Who owns the credentials? What happens when the source is down, slow, or has changed shape? |
| "for their project" | How does it know which project, and which person is asking? |

**"By a REST call" is not an answer to any of these.** The question underneath
is about the model, not the transport: does the system hold this knowledge or
go and find it, and what does it do when what it finds is not what it expected?

**How to ask.** One question at a time, always giving your own recommended
answer first — the goal is shared understanding, not an exam. If an answer can
be verified by reading the codebase, read the code instead of asking. When the
user asserts how something works and the code disagrees, surface it: *"You said
X, but the code does Y — which is right?"*

## Calibrate to scope

| Scope | Treatment |
|---|---|
| New system or package | Full run — all steps |
| Non-trivial feature (new module, significant behaviour change) | Steps 1 + 3 (targeted) + 4; skip Step 2 if the mental model is stable |
| Minor addition or refactor | Step 1, one or two targeted questions, done |
| Small change you understand well | Ask once: *"Is there a design decision here not already in design.md?"* If no — skip entirely |

Non-trivial means: a new public surface, a new dependency, or a new pattern
others will follow. When none of those apply, don't ceremonialize it.

---

## Step 1 — Read context

- `docs/vision.md` — the north star. Every design decision is judged against
  it. **If this is a new project and no vision exists, run the `aganitha-vision` skill
  first** — designing without a vision is optimizing an unknown objective.
- `docs/mental-model.md`, `docs/design.md` — what's already been decided.
- **Feature-level:** a feature doesn't get its own vision file. Open the
  feature's design doc with a short *Why* section — problem, who it's for,
  what success looks like (the `aganitha-vision` skill's questions, one paragraph
  total) — then proceed.

Summarise what you understand and let the user correct it before going on.

## Step 2 — Mental model (only if missing or thin)

If `mental-model.md` lacks substance, pin it down first: core concepts (what
each *is* and *is not*), invariants, boundaries, relationships. One question
at a time, recommended answer first. Write the file as concepts resolve. Don't
accept names without definitions or "it depends" without the cases.

## Step 3 — Interrogate the design

**Running through all of it — options, never a single candidate.** For every
significant choice, put at least two real options on the table with honest
trade-offs. Always include the *simplest thing that could work*, and make the
more complex choice justify itself against it. A design doc with no rejected
alternatives wasn't designed — it was transcribed. This is not one lens among
the others; it applies to every answer the lenses below produce.

Follow the thread — this is a conversation, not a fixed list. But these seven
lenses are the skill's core, in three groups. Every design passes through them.

### Before building — is it needed, and is it as small as it can be?

*Answers land in Decisions and Not doing.*

**1. Bend the requirement before building the machinery.** This is the
highest-leverage question and the easiest to forget: before designing
anything custom, ask whether the *requirement* can flex so that something
that already exists — a standard, a library, a proven pattern, code we
already have — covers it. Alignment with the broader tech scene is a feature
in itself: standard choices get documentation, hiring familiarity, and
tooling for free. Push back early: *"There's a standard for this. It covers
everything except Y. Is Y actually core, or can the requirement move?"*
Only protect what is genuinely core to the vision. Diverge only when
better — and only if we're willing to own the difference forever.

**2. YAGNI — no speculative structure.** No abstraction before a second
implementation exists or is concretely scheduled. No configuration for
values that never vary. No "for flexibility" without a named future need.
Every element in the design must trace to a requirement that exists today.
Ask of each piece: *what breaks if we just don't build this?*

**3. Consistency.** Does this follow the patterns the org and this codebase
already use — same layering, same naming, same conventions — or does it invent
a parallel way? Core capabilities belong in libraries; CLIs, APIs, and skills
are thin interfaces over them. Where existing code almost fits, prefer bending
the requirement (lens 1) over forking it.

### The parts and how they connect

*Answers land in Shape and State.*

**4. Public contract.** For each module: what does it expose, who calls it,
and is every exposed element something you're ready to support indefinitely
(Hyrum's Law: every observable behaviour becomes a contract)? What stays
internal? A module you can't describe in one sentence is doing too much.

**5. Data and state.** Lenses 4 and 7 describe each module on its own. Two
things a list of modules never shows:

*Across the boundary.* For each pair that works together, what actually
crosses, and in what form? A structured record and a written report are not
interchangeable. A design where one module emits prose the next must
re-interpret has a defect that no amount of describing either module reveals.

*Across time.* What does the system remember between runs — where does it live,
whose is it, and what breaks when it is lost? Any requirement phrased as *new*,
*changed*, *since last time*, or *resume* is a state requirement in disguise.
"Show what changed since last time" means per-user state; "show changes in a
date range" means none at all. Those are different systems, and the difference
is usually found late.

### What happens when it changes

*Answers land in Scenarios and Decisions.*

**6. Replaceable parts.** YAGNI's counterweight: you don't build for
imagined futures, but you also don't weld parts together. Identify what is
volatile (likely to change: formats, providers, models, external services)
vs stable, and make sure volatile parts sit behind a seam that lets them be
swapped or extended without rewriting the stable core. The test: *"If X is
replaced next year, what has to be rewritten?"* — the answer should be
"X's adapter", not "everything".

**7. Extension path.** Lens 6 asks *whether* a volatile part can be replaced.
This asks *how* someone does it: who makes the change, what they add, where it
goes, what stays unchanged, how the system finds the extension, and how they
check that it works. Answer at the contract level — *"a developer implements
the renderer interface and registers the name"* — not as code. If nothing in
this design is meant to be extended, say so and move on.

## Step 4 — Write the doc

Write `docs/design.md` **as decisions crystallise** — never batch to the end.

The prose itself — style, how much to explain, which claims need justifying —
follows `aganitha-doc-writing`. This skill decides the sections; that one
decides the writing.

```markdown
# Design — <name>

## Purpose

<What this proposes, who should read it, and what decision it supports.
Two or three sentences.>

## Why (feature-level docs only)

<Problem, who it's for, what success looks like. One paragraph.
Project-level docs skip this — vision.md carries it.>

## Shape

<One paragraph: the modules and how they relate. Then one line per module:>

- **<module>** — <its one-sentence responsibility>
  - exposes: <the public contract — functions/commands/endpoints callers rely on>
  - hands off: <what it passes to which module, and in what form>

## State

<What persists between runs, where it lives, and whose it is. "None" is a valid
answer and worth stating outright — an unsaid answer reads as an unasked
question.>

## Scenarios

<Two or three walkthroughs that let a reader execute the design mentally: who
starts the action, what they supply, which module handles it, what comes back,
and where responsibility passes on. Include one that shows someone extending
the system (lens 7). Boundaries and responsibilities — never implementation
steps.>

## Decisions

### <Decision title>

- **Options:** <A — trade-off. B (simplest) — trade-off. C — trade-off.>
- **Chose:** <which and why — tied to vision or a real requirement>
- **Consequences:** <what gets easier, what gets harder, what's now hard to change>

## Not doing

- **<Excluded thing>** — <why: not core, standard covers it, deferred, YAGNI>

## Open questions

<Unresolved decisions, assumptions the design rests on, risks, dependencies,
scenarios not yet covered. Distinct from "Not doing": that is deliberate
exclusion, this is what nobody has settled yet.>

## Next

<What the reader should do: approve, comment on a named question, compare two
options, or implement a defined part.>
```

Reserve the full ADR format (Status / Context / Supersedes...) for decisions
that are hard to reverse, surprising without context, *and* involved a real
trade-off — all three. Everything else uses the compact form above. When a
decision changes later, supersede it; don't erase the history.

The **Not doing** section is required. If it's empty, the scope hasn't been
thought through — and lenses 1 and 2 above didn't happen.

## Checklist before finishing

Report each as `[✓]` / `[✗]`:

- [ ] The doc opens with who reads it and what decision it supports
- [ ] Design was judged against `vision.md` (or the doc's own Why section)
- [ ] Every significant decision shows ≥2 options, including the simplest one
- [ ] At least one requirement was questioned — "can this bend to reuse what
      exists?" was actually asked, not skipped
- [ ] Nothing speculative survived — every element traces to a current need
- [ ] Volatile parts are named and sit behind seams; the "replace X" test has
      an answer better than "rewrite everything"
- [ ] Every module has a one-sentence responsibility and an explicit public
      contract
- [ ] Every pair of modules that work together says what crosses between them,
      and in what form
- [ ] What the system remembers between runs is stated — where it lives and
      whose it is, or explicitly "none"
- [ ] Every edge where the system meets a person or an outside system says how:
      how input arrives, how output is delivered, and whether what the system
      knows is declared, discovered, or derived
- [ ] At least one scenario lets a reader execute the design mentally, and one
      shows someone extending it (skip only if nothing is extensible)
- [ ] Not-doing section is non-empty
- [ ] Open questions are stated — assumptions, risks, what nobody has settled
- [ ] The reader knows what to do next
- [ ] No implementation detail in the doc — decisions and consequences only
