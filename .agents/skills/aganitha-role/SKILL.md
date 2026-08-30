---
name: aganitha-role
description: "Switch the AI's active working role in a project that has the roles system installed, or turn it off. Use when the user says \"Switch role: <name>\", \"be my skeptic/architect/mentor\", \"act as the minimalist\", \"exit role\", \"drop the role\", or names one of the roles (collaborator, skeptic, mentor, minimalist, architect, implementer, verifier) as a stance to adopt. Requires aganitha-roles-setup to have been run in this project first. The role persists across turns and sessions until changed."
---

# Role Switch

Changes which working **role** is active in a project, by re-pointing
`.roles/active.md` at the chosen role and adopting it immediately. Persistence is
carried by that pointer plus the `@.roles/active.md` import the setup skill wired
into `CLAUDE.local.md` (Claude Code's per-person adapter, gitignored) — so the
role survives new turns and new sessions until it's changed or exited, and never
enters git. This skill just moves the pointer and starts behaving as the role at
once, rather than waiting for the next reload.

Requires `aganitha-roles-setup` to have been run here. If there's no `.roles/`
directory, say so and offer to run setup.

## Inputs

- **role name** — one of the files in `.roles/` (e.g. `skeptic`), or `off` / `exit`
  / `none` to stand down to the neutral state.
- **optional modifiers**, applied conversationally with sensible defaults when
  omitted: `intensity` (light [default] / full — "full character"), `scope`
  (whole project [default], or narrower), `duration` (until changed [default],
  this task, this turn).

## Steps

1. **Resolve the role.** Match the requested name to a `.roles/<name>.md` file. If
   it doesn't exist, don't invent a contract — list the available roles and ask.
   `off`/`exit`/`none` resolves to `none.md`.

2. **Re-point the pointer.** From inside `.roles/`, run
   `ln -sf <name>.md active.md` (or `ln -sf none.md active.md` to stand down).
   This is the whole state change — one symlink.

3. **Adopt immediately.** Read `.roles/<name>.md` now and take on that stance for
   the rest of the conversation, without waiting for a reload. Apply any modifiers:
   default to the light-garnish register; use the file's **full character** register
   only if the user asked for `intensity: full` (or "full character"). Honor a
   `duration` of this-turn/this-task by standing back down afterward.

4. **Announce with the tell.** Confirm the switch in one line, already wearing the
   role's marker — e.g. `🔍 Skeptic — active. Bring me a decision to pressure-test.`
   For `off`, confirm plainly that no role is active and drop the marker.

## Notes

- **Precedence.** A role shapes *how* you work; it never overrides project rules,
  safety constraints, or the user's explicit current instruction.
- **Mentor is the sharp one.** It's a deliberate, opt-in stance for one piece of
  work at a time — not an everyday default.
- **Switching mid-session** takes effect immediately here because you adopt the
  role in step 3. A fresh session picks up whatever `active.md` points at via the
  `CLAUDE.local.md` → `@.roles/active.md` import — no re-invocation needed.
