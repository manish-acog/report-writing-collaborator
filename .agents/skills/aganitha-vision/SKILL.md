---
name: aganitha-vision
description: Establish the north star for a project — why it exists, who it serves, and what success looks like — written down as docs/vision.md before anything else. Use this skill at project birth, when someone says "write the vision", "what is this project for", or starts a new project/product/system. Also use when a project has no vision.md, or when the mission itself has changed and the vision needs a deliberate revision. For a single feature, the same questions apply but the output goes into the feature's design doc instead — this skill routes there.
---

# Vision

The vision is the north star — more important than any spec, because every
later decision (design, scope, trade-offs) is judged against it. It is written
**once, at project birth**, and revised only when the mission itself changes.
Not per feature, not per release.

**Write for an expert evaluating, not a reader being convinced.** The vision is
read by whoever has to place this system among the others — usually an architect
or a lead deciding where its boundaries fall and what it must not absorb. They
know the domain. They are not a customer, and they do not need the general
background explained to them.

**Length is not the constraint. Density is.** Every paragraph should carry
something the reader did not already know: a boundary, a dependency, a rejected
alternative, a constraint that binds, a user whose way of working changes the
design. Three pages of that are fine. What fails is a document that runs long
because it restates, argues, or explains what an expert already understands —
and a one-page version of that document fails identically.

The vision answers "why does this exist, who uses it, where does it stop, and
how do we know it's working". Question 2 borrows Moore's template, which is a
positioning tool: keep it for the one line it produces, and do not let its voice
spread into the rest of the document.

## Scope check first

- **Project or system** → this skill, produces `docs/vision.md`.
- **A feature within a project** → same questions, but the answers become the
  opening section of that feature's design doc (see the `aganitha-design-doc` skill).
  Do not create a separate vision file per feature.
- **Vision exists and mission hasn't changed** → stop. Point at the existing
  `docs/vision.md`. Keeping it in sync with reality is `aganitha-system-health`'s job,
  not a reason to rewrite it.
- **The audiences don't overlap** → probably more than one system. Answer
  question 3 early and read the list: when two audiences share no artifact, no
  moment of use, and no lifecycle, one vision written over both hides the
  boundary instead of drawing it. Say so, and either split it or name one system
  as primary and the others as consumers of what it produces. Deciding this
  after the vision is written is expensive; the vision is where scope is set.

## How to run it

Ask **5–7 questions, one at a time**. For each: give your own recommended
answer first (derived from the README, the code, and the conversation so far),
then let the user confirm or correct. This is a conversation, not a form.

**On an existing codebase:** draft answers from what's already there before
asking anything — the user should be reacting to a credible draft, not
producing answers from a blank page.

### The questions

1. **Problem — why does this need to exist?** What is painful or broken
   without it? Why now?

2. **Positioning — how do you explain it in one breath?** Use Moore's
   template as the scaffold:

   > For **<who>** that **<need>**, **<name>** is a **<category>** that
   > **<key benefit>**. Unlike **<the alternative they'd use instead>**,
   > it **<key difference>**.

   Then compress it into a familiar analogy if one fits — *"Netlify publish,
   but for internal deploys."* The analogy is often the most-repeated line of
   the whole document.

   **One sentence, plus the analogy.** The section is called "In one line" and
   the template is a scaffold for thinking, not the output. A 90-word
   positioning statement has failed the question.

3. **Audiences and journeys — who touches this, and how?** For each role that
   genuinely differs (end user, developer, ops/deployment — only the roles that
   actually exist): in what context do they use it, how do they get it
   (install / access / onboard), and what can they do with it. Drop any role
   whose journey is a variation on another's — near-duplicate roles are padding.

   **Then one concrete trace.** A named person, a real moment, and what happens
   step by step *across* the parts — not one path per role, but one path that
   crosses them. *"Priya asks on Tuesday. The watcher finds nine changes. The
   analyzer keeps two and lists the seven it dropped. She gets one page with a
   link on every line."* Per-role paragraphs describe the parts; only a trace
   shows whether they fit together.

   If writing the trace forces you into design detail, that is itself the
   signal — the vision is describing more machinery than it should own.

4. **Where it fits — what does this sit next to?** Which systems it depends on,
   which depend on it, and where the boundary falls with each. Name the
   neighbour that owns what this one stops short of. An architect placing the
   system needs this more than anything else in the document, and it is the
   section most often missing.

5. **Must satisfy — what are the non-negotiables?** Constraints that any
   version of this system must honor: security boundaries, platforms,
   compliance, compatibility. If a design choice violates one of these, it's
   wrong no matter how elegant.

6. **Success and exit criteria — how do we know it's working?** What does
   success look like, concretely (adoption, a workflow that becomes possible,
   a cost that disappears)? And what is the exit criteria — the point at which
   this project is *done* or should be *stopped*? A vision without a failure
   condition can't be falsified.

7. **Not for — who or what is this explicitly not serving?** The anti-scope.
   One honest line here prevents ten scope arguments later. Distinct from
   question 4: *Where it fits* says what sits next to this and owns the rest;
   *Not for* says what nobody should expect from it at all.

Skip a question when the answer is already obvious from context — say what you
inferred and move on. Do not pad the conversation to hit every question.

## The document

Write `docs/vision.md` as answers land — don't batch to the end.

The prose follows `aganitha-doc-writing`. A vision attracts unjustified claim
adjectives — *scalable*, *world-class*, *seamless* — more than any other
document. Justify each one with a mechanism, or delete it.

```markdown
# Vision — <name>

## In one line

<The Moore positioning statement, and the analogy if one exists.>

## Problem

<Why this exists. Why now. A paragraph, not an essay.>

## Where it fits

<What this sits next to: what it depends on, what depends on it, and who owns
the thing it stops short of. Two or three lines.>

## Who it serves

**<Role>** — <context they're in, how they get the system, what they can
do with it. A short journey, 2–4 sentences.>

**<Role>** — <...>

**One path through it** — <a named person, a real moment, what happens step by
step across the parts.>

## Must satisfy

- <Non-negotiable constraint>

## Success looks like

<Concrete picture of success. Then: the exit criteria — when is this done,
or when should it be stopped.>

## Not for

- <Explicit anti-scope: audience or use case this deliberately doesn't serve>
```

## Checklist before finishing

Report each as `[✓]` / `[✗]`:

- [ ] Every paragraph carries something an expert did not already know — no
      restating, no arguing, no general background explained
- [ ] The one-liner is one sentence (plus the analogy) and works without any
      other context — test: would a new hire understand what this is from that
      line alone?
- [ ] "Where it fits" names the neighbouring systems and the boundary with each
- [ ] One concrete trace shows a named person's path across the parts
- [ ] Every audience listed is real (someone specific, today or planned) —
      no hypothetical users
- [ ] One system genuinely serves every audience listed — if two share no
      artifact, no moment of use, and no lifecycle, that is two systems
- [ ] The document states rather than argues — no case being made to a reader
      who does not need convincing
- [ ] Success criteria are concrete enough that two people would agree
      whether they've been met
- [ ] Exit criteria stated — the vision can fail, not just succeed
- [ ] "Not for" is non-empty
- [ ] No unjustified claim adjectives survive
- [ ] No design decisions leaked in — the vision says *what and why*, never
      *how* (how belongs in the design doc)
