---
name: aganitha-ship
description: "Get finished work onto main — choosing between committing directly to main and working on a short-lived branch, and when on a branch, creating the PR, squash-merging as soon as it's done, and cleaning up. Use this skill when someone says \"ship\", \"ship it\", \"merge this\", \"create a PR\", \"should I branch for this?\", or is starting multi-day work and deciding where to commit. Encodes the org doctrine: main is always consistent, commit without fear, never let a PR or branch sit."
---

# Ship

Getting work onto main, without fear and without ceremony. Two doctrines
drive everything here:

- **Main is always consistent.** Anyone can pull main at any moment and get
  a working system.
- **Commit without fear.** Nobody should hoard uncommitted work until it's
  "finished and tested." If committing would break main's consistency, the
  answer is a branch — never a dirty working tree held back for days.

## Choosing the path

Ask one question about the work ahead: **can each commit leave main
consistent?**

| Situation | Path |
|---|---|
| Small change, reaches consistency in one sitting | **Straight to main.** Run `aganitha-preflight`, commit, push. |
| Multi-day work; intermediate states would leave main broken or half-migrated | **Branch.** Commit freely there; PR + squash-merge the moment it's done. |
| Testing a fundamental extension that may be abandoned | **Branch.** Same mechanics; deleting it is a fine outcome. |

When someone is starting work and unsure, apply the table and say which path
and why — don't make them ask twice.

## The gate placement — the rule that makes branches fearless

**`aganitha-preflight` gates main, not every commit.**

- On **main**, every commit is by definition landing on main → preflight
  runs before each one.
- On a **branch**, commit as often as you like with zero ceremony — "end of
  day", "wip: half-done" are all fine. Push the branch too (a branch that
  only exists locally is a laptop failure away from gone). The gate runs
  **once**, when the work is ready to merge.

This is why branching and fearless commits are the same policy, not a
trade-off.

## Shipping a branch

When the work is done:

1. **Gate:** run `aganitha-preflight` on the branch's full result (which itself gates
   on `aganitha-code-review`). Not ready → fix first; the merge waits for the gate,
   never the other way around.
2. **Sync:** rebase on (or merge in) latest `main` and re-run the tests —
   the gate checked your code against the main *you branched from*, not
   the main of today.
3. **PR:** `gh pr create` — title says what, body says why (the preflight
   commit-message proposal is usually exactly this). The PR is the record
   of the change, even with no second reviewer.
4. **Merge immediately:** `gh pr merge --squash --delete-branch`. The author
   merges as soon as the gate passes — review already happened via the
   `aganitha-code-review` skill; there is no waiting-for-approval state. A PR that
   sits is the failure mode this skill exists to prevent.
5. **Squash lands one coherent commit on main** — proper message, WIP
   checkpoints stay private to the branch history. Main's log reads as a
   sequence of finished, consistent changes.
6. **Confirm:** back on main, pull, verify the merge landed and tests pass.

## Hygiene rules

- **Branches are short-lived** — days, not weeks. A branch older than a week
  is a smell: ship it, split it, or delete it.
- **One branch per effort.** Don't stack branches on branches.
- **Never leave a merged or abandoned branch behind** — `--delete-branch` on
  merge; delete abandoned ones explicitly (the doctrine's "don't leave
  branches unmerged" has teeth only if deletion is routine).
- **Branch names:** short kebab-case topic (`registry-verification`,
  `packs-mechanism`). No enforced scheme beyond that.
- **Restructuring the whole project?** Consider a new repo/name instead of a
  long-lived rework branch — modular, published code can be reused from
  either place.

## Checklist (reported when shipping a branch)

Report each as `[✓]` / `[✗]`:

- [ ] Preflight passed on the final state (includes code review)
- [ ] Branch synced with latest main; tests re-run after sync
- [ ] PR created with a real what/why description
- [ ] Squash-merged — one coherent commit on main
- [ ] Branch deleted (remote and local)
- [ ] Main pulled and verified after merge
