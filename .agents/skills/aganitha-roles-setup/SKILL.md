---
name: aganitha-roles-setup
description: Install the portable role-switching system into a project — a set of working "roles" (collaborator, skeptic, mentor, minimalist, architect, implementer, verifier) the AI can take on and hold across turns and sessions until told otherwise. Use when someone wants their project to support switchable AI personas/stances, says "set up roles here", "add role switching", "I want a skeptic/architect/mentor mode", or asks to install the roles system. One-shot per project; pairs with the aganitha-role skill, which does the actual switching.
---

# Roles Setup

Installs a **portable role-switching system** into the current project. A *role*
is a working stance — how the AI behaves while it helps — that persists across
turns and sessions until the user changes or exits it. Definitions are plain
Markdown, so the same files work in any harness that loads `AGENTS.md`/`CLAUDE.md`.

This skill sets a project up **once**. Switching between roles afterward is the
separate `aganitha-role` skill (or the natural-language `Switch role: <name>`
protocol this skill installs).

## Architecture: what's shared vs. what's per-person

Role state is a *working* thing — each person has their own, and it is never
committed. The install splits along that line. Role files live in a hidden
`.roles/` directory (like `.claude/` or `.agents/`, it stays out of the way):

```
<project>/
  AGENTS.md          # committed, SHARED — the "Working roles" protocol + registry block
  .roles/
    none.md          # committed, shared — neutral state (no role active)
    collaborator.md  skeptic.md  mentor.md  minimalist.md
    architect.md     implementer.md  verifier.md   # committed, shared — the definitions
    active.md        # gitignored, PER-PERSON — symlink → current role (default none.md)
  CLAUDE.local.md    # gitignored, PER-PERSON — imports the active role: @.roles/active.md
  .gitignore         # ignores CLAUDE.local.md and .roles/active.md
```

- **Committed & shared:** the role *definitions* (`.roles/*.md`) and the *protocol*
  in `AGENTS.md`. Portable across harnesses.
- **Gitignored & per-person:** `.roles/active.md` (the pointer — the neutral state
  every harness reads) and `CLAUDE.local.md` (Claude Code's *adapter*, which does
  the actual `@.roles/active.md` import). The active role therefore never enters git.

Why `CLAUDE.local.md` rather than putting the import in `AGENTS.md`: `AGENTS.md`
is committed and shared, and Claude Code re-reads project-root `CLAUDE.md` /
`CLAUDE.local.md` from disk (they survive compaction). `CLAUDE.local.md` is the
documented gitignored per-person memory file — the right home for personal state.

The bundled role definitions live in this skill's `assets/roles/` directory; the
`AGENTS.md` block is `assets/protocol.md`. (The skill's own copy stays visible as
`assets/roles/`; only the target directory it installs into is the hidden `.roles/`.)

## Steps

1. **Confirm scope.** Install into the current project root (the git root, or the
   directory holding `AGENTS.md`/`CLAUDE.md`). Confirm that's the intended project
   before writing.

2. **Copy the role definitions (shared).** Create `<project>/.roles/` if absent and
   copy every `*.md` from this skill's `assets/roles/` into it. Don't overwrite a
   role file that already exists and differs — if there's a clash, stop and ask, so
   a project's customised role isn't clobbered.

3. **Create the active pointer (per-person state).** Make `.roles/active.md` a
   symlink to `none.md`: `ln -sf none.md .roles/active.md` (run inside `.roles/`).
   This is the neutral "no role" state. If `active.md` already exists, leave the
   user's current role alone.

4. **Install the protocol block (shared).** Append the contents of this skill's
   `assets/protocol.md` to the project's `AGENTS.md` (create `AGENTS.md` if it
   doesn't exist). The block is delimited by
   `<!-- BEGIN role-switching (managed by aganitha-roles) -->` … `<!-- END … -->`
   — **idempotent:** if that BEGIN marker is already present, replace the existing
   block rather than appending a second one. Note this block does *not* import the
   active role; that's the adapter's job (next step).

5. **Ensure the protocol loads.** Claude Code reads `CLAUDE.md`, not `AGENTS.md`.
   If `CLAUDE.md` doesn't source `AGENTS.md`, add an `@AGENTS.md` line to it
   (create `CLAUDE.md` with just that line if it's missing).

6. **Wire the Claude adapter (per-person).** Ensure `CLAUDE.local.md` at the
   project root contains the line `@.roles/active.md` — create the file with that
   line, or append it if the file exists without it. This is what actually pulls
   the active role into context, and it stays out of git.

7. **Gitignore the per-person files.** Ensure `.gitignore` contains both
   `CLAUDE.local.md` and `.roles/active.md`. Add whichever lines are missing. This
   is what keeps the active role out of version control.

8. **Present the available roles.** Show the user the installed roster with one
   line each (collaborator, skeptic, mentor, minimalist, architect, implementer,
   verifier), and how to switch: `Switch role: <name>` or the `aganitha-role`
   skill. Mention that each role has an opt-in "full character" register they can
   turn on by asking, and that **mentor** is the deliberately sharp one.

9. **Verify.** The `@.roles/active.md` import loads when `CLAUDE.md` / `CLAUDE.local.md`
   is read — at session start, and re-read on compaction. Tell the user that to
   confirm, they switch to a role and check that replies start with that role's
   marker (e.g. `🔍 Skeptic —`); a brand-new session picks up the active role
   automatically from `.roles/active.md`.

## Notes

- **Nothing about the active role is ever committed** — `.roles/active.md` and
  `CLAUDE.local.md` are both gitignored. Switching leaves the git tree clean.
- **Other harnesses (Codex, etc.).** `.roles/active.md` is the harness-neutral
  pointer, and the `AGENTS.md` protocol block already tells any tool how to load
  it. AGENTS.md-only tools have no `@import` and no `CLAUDE.local.md`: they read
  `AGENTS.md` as plain text, follow its "Working roles" block, and
  `read .roles/active.md` themselves — so no `CLAUDE.local.md` and no adapter file
  is needed there. Switching is the same `ln -sf` on `.roles/active.md` (the agent
  runs it, or the user does); the `aganitha-role` skill is just Claude Code's
  convenience wrapper for it. These tools have no auto-import, so the protocol
  block tells them to re-read the pointer before every reply rather than once
  per session — costs one extra file read per turn, but the role can't silently
  drop from context that way. Shared definitions and protocol are identical
  either way. Steps 6–7 (the
  `CLAUDE.local.md` adapter) are Claude Code-specific; skip them for a
  Codex-only project and just keep `.roles/active.md` gitignored.
- **Adding a role later.** Drop a new `<name>.md` into `.roles/` following the shape
  of the existing files (marker, voice, contract, restrictions, full-character),
  and add a line for it to the registry in the `AGENTS.md` block. No code changes.
- **Removing the system.** Delete `.roles/`, the managed block between the
  BEGIN/END markers in `AGENTS.md`, and the `@.roles/active.md` line from
  `CLAUDE.local.md`.
