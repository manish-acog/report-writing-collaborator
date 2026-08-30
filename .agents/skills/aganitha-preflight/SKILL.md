---
name: aganitha-preflight
description: Pre-commit gate — verifies that code, tests, docs, Makefile, and README are consistent and in sync before committing. Use this skill whenever someone says "preflight", "is this ready to check in?", "ready to commit?", "pre-commit check", or wants a final gate before pushing. Also run it unprompted when finishing a feature, before offering to commit — agents should treat preflight as the default last step, not wait to be asked. Replaces the older code-readiness skill.
---

# Preflight

The last check before takeoff. The goal is to catch drift — places where code,
tests, docs, and supporting artifacts have fallen out of sync with each other.

**Run this before offering to commit** — the human shouldn't have to remember
to ask. They can also invoke it by name (`aganitha-preflight`) at any time.

**Preflight is the gate.** There is no other automation between the change
and the commit — this skill runs the deterministic checks itself (tests,
secret grep) and applies judgment for everything else: is the README honest,
is status.md current, do the docs still describe this code.

**Adapt to the project.** Not every project uses every artifact checked here.
`[—]` (not applicable) is a valid and correct result for items the project
doesn't have — a project without `status.md` is not failing because it lacks
one; it simply doesn't use that structure. Only flag `[✗]` for things the
project has committed to maintaining.

Work through each section. For each item report:
- `[✓]` done
- `[✗]` needs attention — include the specific location or issue
- `[—]` not applicable to this project

At the end, give a clear verdict: **Ready** or **Not ready**, with a short
list of what needs fixing. **A "Not ready" verdict blocks the commit** until
the listed items are resolved — the gate only works if it has teeth. The human
may override consciously, but the default is: do not commit until ready.

- **Not ready** → offer to fix the fixable items right away and re-run
  preflight, rather than leaving the list as homework.
- **Ready** → propose the commit message: subject says *what* changed
  (imperative, under ~70 chars), body says *why*. It must describe the diff
  that exists, not the change as it was planned.

---

## Shared definition: meaningful changes

Several checks below apply only to **meaningful changes** — feature complete,
new behaviour introduced, design decision made, known issue discovered or
resolved. **Trivial commits** — typo fixes, dependency bumps, comment changes,
reformatting — skip these checks (`[—]`).

Sections 4 (status.md) and 5 (CHANGELOG.md) both reference this single
definition. Keep it here so the two never drift apart.

---

## A note on what this skill executes vs inspects

Most checks are judgment calls the skill *inspects*. A few it *executes*:
running the test suite (section 2) and grepping for secrets (section 7). Run
those first so their results are in hand before reporting the judgment-based
items.

---

## 0. Orient — what is this commit, exactly?

Ground every later check in the actual change, not in memory of it:

- Run `git status` and `git diff` (staged *and* unstaged) — enumerate what
  this commit will really contain.
- **Nothing missing:** new test files, docs edited alongside code, and other
  untracked files that belong to this change are staged. Forgotten untracked
  files are the single most common miss.
- **Nothing extra:** no unrelated edits or drive-by fixes riding along. One
  commit, one purpose — if the diff mixes two changes, recommend splitting
  before continuing.
- Classify the change: meaningful or trivial (shared definition above).
  **Trivial → fast path:** run only sections 2 (tests) and 7 (cleanup),
  report compactly, and skip the rest — a typo fix does not need a
  seven-section audit.

---

## 1. Code review — gate, not a check

This section is a prerequisite gate, not a parallel checklist item. Unlike the
rest of the skill, it halts and branches if review hasn't happened.

- Ask the user: "Was a code review done on these changes?"
  - If yes and all **Must fix** items are resolved → `[✓]`
  - If yes but **Must fix** items remain → `[✗]` list them
  - If not done, or if the user isn't sure → run the `aganitha-code-review` skill now
    before continuing with the rest of this checklist

---

## 2. Tests

- Do tests exist for new or changed code? New behaviour with no tests → `[✗]`.
  Existing code with no behaviour change and existing tests → `[✓]`. No tests
  at all in the project → `[✗]`.
- Do all tests pass? Run `make test`, `bun test` (TypeScript), or
  `uv run pytest` (Python) and check.
- Are there any skipped, commented-out, or placeholder tests that were left in?

---

## 3. Makefile hygiene

Not every repo is a coding system. Content repos (docs, registries,
configuration) carry only the targets that do real work — possibly just a
`test` that validates the content, or no Makefile at all if nothing would →
`[—]`, not `[✗]`. Never demand ceremony targets that do nothing.

- For code projects: standard targets present — `install`, `build`, `test`
  (the full verb contract is `aganitha-makefile`'s; this is the check)
- `run` applies to services and applications; it is optional for libraries
- **Self-describing:** run `make help` and confirm it lists every target — a
  target with no `## description` is invisible to `make help` and fails this
  check
- Each present target actually works — no broken references to removed scripts
  or files
- No stale targets left over from features that no longer exist
- If a target is listed, it should do something real

---

## 4. status.md — present-tense state

`docs/status.md` describes where the project **is right now**. It is
overwritten, not appended — it always reflects current state, never history.
(History lives in CHANGELOG.md, section 5. The two are deliberately separate:
status is what *is*, CHANGELOG is why it *became* so.)

For meaningful changes (see shared definition):

- Does it describe what was just completed in this change?
- Is the TODO section current — items done removed, new items added?
- Are known issues and blockers up to date?

If `status.md` is stale and this is a meaningful change → `[✗]`. Trivial
commit → `[—]`. Otherwise → `[✓]`.

---

## 5. Docs sync

The most common source of drift. Check each that exists:

- **Inline comments** — do they describe what the code *does now*, not what it
  used to do?
- **Docstrings / JSDoc** — do function signatures and descriptions still match
  the implementation?
- **design.md** — does it reflect the current architecture? If this change
  introduced a structural decision or deviated from a prior design choice,
  `design.md` must be updated in the same commit. Unacknowledged drift is the
  problem, not the drift itself.
- **llms.txt** — published libraries only. If this change added, removed, or
  changed public API (exported functions, types, or CLI commands), update
  `llms.txt` in the same commit. Skip for services, applications, and internal
  tools that are not published as packages.
- **CHANGELOG.md** — past-tense history, append-only (the counterpart to
  status.md's present-tense state). Required for meaningful changes; trivial
  commits skip it. Each entry captures the one thing a `git log` message can't
  hold well: the rejected alternative. The `Rejected` field is the point —
  it's what `git log` can't capture and what future-you (or Claude reading
  this codebase cold) will most want to know. Don't delete that field because
  it feels redundant; it is the reason this entry outlives the commit message.
  Format:

  ```
  ## 2026-06-24
  **What:**
  **Why:**
  **Rejected:**
  ```

  Meaningful change with no entry → `[✗]`. Trivial commit → `[—]`.

---

## 6. README — think like a user

Read the README as someone who has never seen this project:

- Does it explain what the project does in one or two sentences?
- Do the install and run instructions still work?
- Are environment variables or config documented? If the project uses a `.env`
  file, does a `.env.example` exist?
- For a library: are there usage examples, and do they still reflect the
  current API?
- For a service: can someone get it running locally from the README alone?

---

## 7. Cleanup

- No debug statements left in (`console.log`, `print`, `debugger`,
  `pdb.set_trace()`)
- No commented-out code blocks
- No `.env` or credential files staged for commit
- No secrets hardcoded in source files — look for string literals assigned to
  names like `api_key`, `secret`, `password`, `token`
  (`grep -rn "api_key\s*=\s*['\"]" src/` is a better pattern than a broad
  keyword search, which produces too many false positives on variable names
  like `getPassword()` or `tokenize()`). Secrets belong in environment
  variables, not in code.
- Build artifacts and dependency directories are gitignored (`dist/`,
  `node_modules/`, `.venv/`, `__pycache__/`)
- Lock file is committed (`bun.lock` for TypeScript, `uv.lock` for Python) —
  reproducible installs matter

---

## Output format

```
## Preflight

### Change
- [✓] 5 files staged — all belong to this change; no unrelated edits
- [✗] tests/pricing/discount.test.ts is untracked — belongs to this change, not staged
- Classified: meaningful (new behaviour)

### Code review
- [✓] Code review complete — all Must fix items resolved

### Tests
- [✓] make test passes
- [✗] New function `calculateDiscount` (src/pricing/discount.ts) has no tests

### Makefile
- [✓] install, build, test present and working
- [—] run not present — library project, not required
- [✗] `deploy-staging` target references a script that no longer exists

### status.md
- [✓] Updated — reflects current changes and TODO

### Docs
- [✓] Inline comments accurate
- [—] No design.md in this project
- [✗] README install step references Node — project uses bun
- [✓] CHANGELOG entry added (what / why / rejected)

### README / user view
- [✓] Purpose clear, quickstart works
- [✗] No .env.example — three required env vars are undocumented

### Cleanup
- [✓] No debug statements
- [✓] No commented-out code
- [✓] .env is gitignored

---
**Not ready.** Fix before committing:
1. Stage tests/pricing/discount.test.ts
2. Add tests for `calculateDiscount`
3. Remove or fix `deploy-staging` Makefile target
4. Update README install step (bun, not Node)
5. Add .env.example with the three required vars

Want me to fix these and re-run preflight?
```
