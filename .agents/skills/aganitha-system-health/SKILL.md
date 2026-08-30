---
name: aganitha-system-health
description: Periodic whole-system audit for vision alignment, drift, dead code, simplification opportunities, and consistency. Explicitly invoked — not context-triggered. Run after a major feature lands, before a release, or whenever the system feels like it has accumulated weight. Reads the full system, surfaces issues in priority order, fixes what it can, and leaves status.md and the AGENTS.md map accurate.
---

# System Health

A periodic checkpoint for the whole system. Not a pre-commit gate. Not a code review. A deliberate audit that asks: does the system reflect our current understanding, and is it as simple as it could be?

**When to run:**
- After a major feature lands
- Before a release
- Whenever the system feels heavy — too many special cases, too many layers, too much code for what it does
- Periodically (monthly or each sprint) as maintenance

**Posture:** simplification-biased. Complexity has a cost. Every line of code is a liability. The goal is a system that is exactly as complex as the problem requires — no more.

---

## Step 1 — Orient

Read the system's context before touching anything:

- `docs/vision.md` — what is this system for? What does success look like?
- `AGENTS.md` — the map: what does the repo claim it contains?
- `docs/design.md` — what decisions have been made and why?
- `docs/mental-model.md` (if the project has one) — core concepts and invariants
- `docs/status.md` — what is the current state?

Then read the codebase structure: list packages, modules, and entry points. Read recent `git log` — last 2–4 weeks of commits — to understand what has changed.

Do not start diagnosing until you have oriented. Symptoms are only meaningful in context.

---

## Step 2 — Drift Audit

Check whether the docs, design, and code are consistent with each other. Drift is the gap between what is written and what is true.

**System vs vision — the first question:**
- Does what's built still serve `vision.md`? Building the wrong thing
  efficiently is a drift no other check below will catch.
- The success criteria: measurably closer, stalled, or quietly abandoned?
- Has an exit criterion fired? Say so plainly — that is a finding, not a
  failure of the audit.
- If the *mission* changed rather than the system, don't patch docs — route
  to a deliberate vision revision (the `aganitha-vision` skill).

**Docs vs docs:**
- Does `design.md` reflect `mental-model.md` (where one exists)? Are the core concepts still the same?
- Does `status.md` reflect the current state of the system, or is it from a previous phase?
- Are there decisions in `design.md` whose recorded consequences are no longer accurate?

**Docs vs code:**
- Does the module structure match the Shape section of `design.md`?
- Are there modules, concepts, or layers in the code that are not mentioned in `design.md` or `mental-model.md`?
- Are there modules in `design.md` that no longer exist in the code?
- Does the public surface (exports from `index.ts` / `__init__.py`) match the contracts `design.md`'s Shape section says are exposed?
- Is the "Not doing" section of `design.md` still accurate, or have some of those things been done?
- **AGENTS.md map:** does every entry match the actual layout, is every
  module a newcomer would wonder about present, and is the file still
  within its ~60-line budget? A stale map actively misleads every agent
  session — treat map drift as HIGH.
- **Docs tier vs reality, both directions:** a non-trivial system missing a
  doc it has earned (no `design.md`), and stub padding — doc files that
  exist but were never filled in. Empty stubs teach readers the docs lie;
  fill them or remove them.
- **Half-migrated skills convention:** `.claude/skills/`/`.agents/skills/`
  present but not gitignored (stale, pre-`skills-pack.lock.json` convention),
  or gitignored with no `skills-pack.lock.json` committed (skills installed
  locally but never recorded — the next clone gets nothing). Either is a
  drift finding, not a style nit — a fresh clone silently ends up with no
  skills.

**Report drift clearly:**

```
Drift found:
  [HIGH] design.md describes a CacheLayer — no such module exists in code
  [HIGH] BatchProcessor is in code but not mentioned in design.md
  [MED]  status.md says "authentication is pending" — auth module is complete
  [LOW]  mental-model.md references "jobs" — code uses "tasks" throughout
```

Fix documentation drift in the same pass. Update `design.md`, `mental-model.md`, `status.md` to match reality. If a structural decision changed, add a new ADR entry with `Status: Supersedes <previous>`.

---

## Step 3 — Dead Code and Changed Assumptions

Find code that exists for assumptions that are no longer true.

**What to look for:**
- Code that handles a case no longer possible given the current design
- Abstraction layers whose only consumer is dead
- Feature flags, toggles, or conditional branches for features that shipped or were cut
- Compatibility shims for an integration that was removed
- Fallback paths for a failure mode the system no longer encounters
- Data transformations for a format no longer used

**Chesterton's Fence:** before removing anything, understand why it was there. Check git history and commit messages for the code in question. If the reason is not clear, ask:
> *"This code handles X. I cannot find a current path that needs it. Do you know if X is still possible in the system?"*

If the assumption is clearly gone, remove the code. If uncertain, flag it:

```
Dead code candidates:
  [REMOVE] src/core/csv_fallback.ts — CSV import was removed in commit abc123
  [REMOVE] legacy_auth_adapter.ts — third-party auth replaced 3 months ago
  [FLAG]   src/core/retry_queue.ts — unclear if async retry path is still reachable
```

Do not remove flagged items without confirmation.

**Stale branches are dead code too.** Run `git branch -a`. Merged branches →
delete. Unmerged branches older than a week → the `aganitha-ship` doctrine applies:
ship it, split it, or delete it — flag which one fits. This audit is the
only place branch hygiene gets checked periodically; don't skip it.

---

## Step 4 — Simplification Pass

Look for complexity that is not justified by a concrete requirement.

**What to look for:**

*Over-abstraction:*
- Abstractions with only one implementation and no realistic prospect of a second
- Interfaces or base classes that exist "for flexibility" with no concrete future use
- Layers of indirection that add navigation without adding clarity

*Under-used generality:*
- Generic utilities that are called from exactly one place
- Configuration options that are never varied in practice
- Parameterized code where the parameter is always the same value

*Structural complexity:*
- Modules with more than one clear responsibility
- Functions that could be split without losing clarity
- Functions that could be merged without losing clarity (too many tiny pieces)

*Defensive code without a threat:*
- Validation of data that comes from a trusted internal source
- Error handling for errors that cannot happen given the current design
- Null checks on values guaranteed non-null by the type system

**Apply the Rule of Three:** if something is done once, inline it. If twice, consider it. If three times, abstract it. Do not abstract speculatively.

Report each finding with its location and a concrete proposed change. Fix simple cases directly. Flag complex refactors for discussion.

---

## Step 5 — Requirement Opportunities

This is the most valuable and most neglected part of a health check.

Sometimes complexity in the code is not a code problem — it is a requirements mismatch. A small change in what the system is required to do can eliminate a large amount of code. (This is the post-hoc twin of `aganitha-design-doc`'s bend-the-requirement lens — the same question, asked of code that already exists.)

Look for:
- A translation layer that exists only to handle one edge case — would relaxing or removing that edge case allow deletion of the whole layer?
- A compatibility mode used by a small minority of callers — what if we migrated those callers instead of maintaining the compatibility?
- A complex flow that only exists because the system supports a feature that few or no users are using
- An abstraction maintained for a future that has not arrived and may not

When you find one, surface it clearly and frame it as a trade-off, not a mandate:

```
Requirement opportunity:
  The DataSource abstraction (src/core/data_source.ts) exists to support
  both PostgreSQL and SQLite. SQLite is only used in local development —
  production has always been PostgreSQL.

  If we standardized on PostgreSQL and used Docker for local dev,
  we could remove the abstraction entirely (~400 lines) and simplify
  five downstream modules.

  Trade-off: local dev setup becomes slightly heavier. Developer experience
  currently works without Docker.

  Worth discussing before the next release?
```

Do not act on requirement opportunities without confirmation. They are observations, not decisions.

---

## Step 6 — Modularity Check

Verify that the system's layer boundaries are clean and that each module has a clear single responsibility.

**Interface layer discipline (TypeScript / Python):**
- Do `cli/`, `api/`, `mcp/` modules import only from `core/`?
- Does `core/` import from any interface layer? (It must not.)
- Do interface layers import from each other? (They must not.)

**Single responsibility:**
- Can each module be described in one short phrase?
- If not: is it doing too much? Split or restructure.

**Law of Demeter:**
- Are there chains of attribute or property access that reach through multiple objects?
- If yes: should the intermediate object be doing the work instead?

**Public surface hygiene:**
- Does `index.ts` / `__init__.py` export only what external callers need?
- Are there internal implementation details in the public surface?

Report violations and fix them. Layer violations are always worth fixing — they accumulate into architectural debt.

---

## Step 7 — Update and Sync

After the audit and fixes:

**Update `status.md`** to reflect current reality. A good `status.md` after a health check should answer:
- What is the current state of each major component?
- What is working, what is in progress, what is known-broken?
- What are the next planned changes?
- Any known limitations or constraints worth documenting?

**Verify docs are consistent:** re-read `design.md`, `mental-model.md` (if present), `status.md`, and the `AGENTS.md` map against the current code and each other. If you changed any code in this health check, update `design.md` in the same pass if any structural decisions changed.

**Check `llms.txt`:** if the public API surface changed — functions added, removed, or renamed in `index.ts` / `__init__.py` — update `llms.txt` to reflect the current API. It is consumed by LLMs and developers using this package; stale API docs are worse than none.

**Final report** — checklist summary first, then the details:

```
System Health — <date>

Summary:
  [✓] Vision — still serves it; success criteria progressing
  [✗] Drift — 2 HIGH findings (below)
  [✗] Dead code — 1 removal, 1 flagged for confirmation
  [✓] Branches — none stale
  [✓] Simplification — 1 small fix applied
  [—] Requirement opportunities — none this pass
  [✓] Modularity — boundaries clean
  [✓] Docs synced — status.md and AGENTS.md map updated

Fixed:
  - Removed dead csv_fallback module (assumption gone since Jan)
  - Removed legacy_auth_adapter (replaced by current auth)
  - Merged three tiny utility functions into one
  - Fixed layer violation: api/handlers.ts was importing from cli/formatter.ts
  - Updated design.md: added ADR for task/job rename decision
  - Updated status.md: auth is complete, cache layer removed

Requires discussion:
  - DataSource abstraction may be removable (see Requirement Opportunities above)
  - retry_queue.ts purpose unclear — is async retry still reachable?

No action needed:
  - Public surface: looks intentional and matches design.md
  - Module boundaries: clean
  - Toolchain and dependencies: current
```

---

## What Good Looks Like

After a health check:

- Every module can be described in one phrase
- `design.md` describes what is actually built
- `status.md` reflects the current state
- There is no code for assumptions that have changed
- The layer boundaries are clean — no layer violations
- The public surface contains only what external callers need
- The simplest version of the system that solves the problem is the version that exists

The test: could a new developer read the docs and understand the code without being surprised by what they find?
