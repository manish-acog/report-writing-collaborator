---
name: aganitha-dev-cycle
description: Teach and navigate the Aganitha developer lifecycle — the vision → design-doc → code-review → preflight → ship → system-health cycle that dev-pack delivers. Use when someone is new to an Aganitha project and asks how we work, asks "what's the next step" / "where am I in the cycle" / "walk me through the workflow", or is starting or resuming work and unsure which skill to reach for. Reads the project's current state and routes to the owning skill for each stage. It teaches and points — it does not run the cycle for you.
---

# Dev Cycle

The developer lifecycle, in one breath:

**vision → design-doc → build → code-review → preflight → ship → system-health → (repeat)**

This skill orients you in that cycle and hands you to the skill that owns each
step. It **teaches and routes — it does not run the cycle for you.** Each stage
is a deliberate checkpoint invoked at its moment (preflight gates a commit;
ship gates a merge). A skill that ran them in one sweep would collapse the very
gates the cycle exists to hold. Your job here is to know *where you are* and
*what to reach for next* — then invoke that skill yourself.

Two doctrines underneath it all, both owned by `aganitha-ship`:

- **Main is always consistent** — anyone can pull main and get a working system.
- **Commit without fear** — never hoard finished work; if a commit would break
  main, that's what a short-lived branch is for.

## The spine — the cycle itself

The ordered happy path. Read it top to bottom to learn the flow; each stage
links to the skill that owns it.

| Stage | When it fires | Invoke |
|---|---|---|
| **Vision** | Once, at project birth — why this exists, who it serves, what success is | `aganitha-vision` |
| **Design** | Before anything non-trivial — decisions, options, consequences | `aganitha-design-doc` |
| **Build** | While coding — conventions apply automatically as you write | see *supporting cast* below |
| **Code review** | When a change is written, before committing | `aganitha-code-review` |
| **Preflight** | The gate — code/tests/docs in sync before the commit lands | `aganitha-preflight` |
| **Ship** | Getting the change onto main — straight, or via a short-lived branch | `aganitha-ship` |
| **System health** | Periodically, or after a major feature — audit for drift and weight | `aganitha-system-health` |

Vision is written once and revised only if the mission changes. Everything from
design onward repeats per change. System-health is the loop closing back on
vision: it asks whether what's built still serves it.

## Where am I? — the router

When someone asks "what's next" or you're picking up cold, read the project's
state and route. Detect from cheap signals, don't interrogate:

- files present: `docs/vision.md`, `docs/design.md`, `AGENTS.md`, `Makefile`
- `git status` — uncommitted or untracked work
- `git branch` — current branch and how old it is

**Situational routes — when you're not on the happy path:**

| What the project looks like now | Route to |
|---|---|
| New or empty repo — no `AGENTS.md`, no `Makefile` | `aganitha-project-setup` |
| Joining or resuming cold — need to know the current state | `aganitha-pickup` |
| Pausing or handing off to someone else | `aganitha-handoff` |
| A branch older than about a week | `aganitha-ship` (ship it, split it, or delete it) |
| System feels heavy, or a major feature just landed | `aganitha-system-health` |
| Ready to publish a package | `aganitha-npm-publish` / `aganitha-pypi-publish` |

**On the spine — the linear read:**

| What's true now | You're at | Next |
|---|---|---|
| Real product, no `docs/vision.md` | Birth | `aganitha-vision` |
| About to build something non-trivial, no `design.md` or the decision is unrecorded | Design | `aganitha-design-doc` |
| Code written, not yet reviewed | Build done | `aganitha-code-review` |
| Reviewed, want to commit | The gate | `aganitha-preflight` |
| Preflight green, getting onto main | Ship | `aganitha-ship` |

Answer in the shape: **"You're here → do X → invoke `aganitha-Y`."** Give one
next step, not the whole cycle, unless they asked to be walked through it.

**When a signal is genuinely ambiguous, ask one question — with your
recommended answer first — rather than guessing.** The usual one: *"Is what
you're about to build non-trivial enough to need a design doc? I'd say yes,
because it adds a new public surface — agree?"* This mirrors how `aganitha-vision`
and `aganitha-design-doc` themselves run, so the handoff feels seamless.

## Two ways in

- **Teaching** — someone new asks how the team works. Walk the spine once,
  briefly, then point at the stage they're actually at. Don't dump all seven
  skills' contents; name the flow and let each skill teach itself when invoked.
- **Coaching** — someone mid-project asks "what's next". Skip the lesson; read
  the state, give the one next step. This is the common case.

Both are the same skill — people invoke it at different points in the cycle,
and it stays useful whether it's day one or the third feature.

## Supporting cast — not stages, but part of the workflow

These aren't points on the cycle; they apply across it. Name them when relevant,
don't route the whole cycle through them:

- **Setup, once:** `aganitha-project-setup` (repo shape), `aganitha-makefile`
  (the self-describing Makefile contract).
- **While building:** `aganitha-typescript-conventions` /
  `aganitha-python-conventions` apply automatically as you edit;
  `aganitha-cli-writing` when a change adds or touches a CLI.
- **Publishing:** `aganitha-npm-publish` / `aganitha-pypi-publish`, packages only.
- **Finding your way:** `aganitha-find-skill` answers "is there a skill for X?"
  — this skill answers "what's the next step?"

## The one rule that keeps this skill honest

Detect **state**, name the **skill** — never restate what the skill does. Say
"you're at the gate → run `aganitha-preflight`," never a copy of preflight's
checks. Each stage's skill is the single source for its own content; this skill
is only the map and the router. That's what stops the two from drifting apart.

## Checklist — what a good orientation gives

Report each as `[✓]` / `[✗]`:

- [ ] Named where the project actually is, from real signals (files, git state)
      — not assumed
- [ ] Gave **one** concrete next step, not the whole cycle (unless asked to walk
      the whole thing)
- [ ] Cited the owning skill by name for that step
- [ ] Said briefly *why* that's next, tied to the state observed
- [ ] Asked one recommended-answer-first question where the signal was
      genuinely ambiguous, instead of guessing
- [ ] Did not run any stage's checks here — pointed to the skill that owns them
