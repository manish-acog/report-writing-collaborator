---
name: aganitha-project-setup
description: Set up a project or repository with the Aganitha standard structure — monorepo layout, AGENTS.md/CLAUDE.md, audience-sectioned README, Makefile contract, and the earned-tiers docs stack. Language-agnostic; applies to TypeScript, Python, and mixed repos. Use when creating a new project or repo, adding a package to a monorepo, deciding whether something needs a new repo at all, or when someone asks to scaffold, initialise, or restructure a project. Also use to set up AGENTS.md or CLAUDE.md for an existing repo.
---

# Project Setup

A repo is set up for four outcomes, in this order:

1. **A newcomer finds their way around without a guide** — the map is at the
   front door, and every repo has the same skeleton.
2. **AI is the primary consumer; humans are the beneficiaries** — an agent
   should understand and operate the repo from AGENTS.md and the layout,
   without reading all the code. Predictability *is* the LLM feature.
3. **Automation works across every repo** — `make` is the contract; the same
   verbs do the same things everywhere.
4. **Few repos** — related things live together in a monorepo. A new repo is
   the exception, not the default.

## First question: does this need a new repo at all?

Default answer: **no — it's a package in an existing monorepo.** Create a new
repo only when one of these is true:

- **Different security boundary** — different people may access it (the
  reason `commands` and `agent-skills` are separate).
- **Genuinely independent lifecycle** — it will be versioned, owned, and
  deployed by different people on a different rhythm.
- **Open-sourcing** — it leaves the private boundary entirely.

None true → find the monorepo it belongs in and add a package. When asked to
create a project, ask this question out loud before scaffolding.

## Layout

```
<repo>/
├── README.md                # front door for humans — audience-sectioned
├── AGENTS.md                # front door for agents — map + rules, ~60 lines max
├── CLAUDE.md                # one line: @AGENTS.md
├── Makefile                 # the automation contract (delegates in a monorepo)
├── docs/                    # earned tiers — see below
├── skills-pack.lock.json    # recorded skill installs — committed
├── .claude/skills/          # project-local skills — gitignored, installed via skills-pack
├── .agents/skills/          # same skills, cross-harness — gitignored, installed via skills-pack
└── packages/
    └── <package>/
        ├── README.md
        ├── Makefile
        ├── src/
        │   ├── core/    # the capability — pure logic, no I/O assumptions
        │   ├── cli/     # thin shells over core (only the ones that exist)
        │   ├── api/
        │   └── mcp/
        └── tests/
```

Single-package repo: the root *is* the package — same shape, no `packages/`.

Everything a developer or agent is expected to edit is in the repo — AGENTS.md,
skills, prompts, config. No side channels: if editing it is part of the work,
it's in git.

Language specifics (package.json, tsconfig, pyproject.toml, src layout
details) belong to `aganitha-typescript-conventions` and `aganitha-python-conventions` — this
skill owns the shape that's true regardless of language.

## AGENTS.md — the agent's front door

AGENTS.md is the canonical agent-context file (the cross-tool standard —
Claude, Codex, and others all read it). CLAUDE.md contains exactly one line —
`@AGENTS.md` — so Claude Code imports it; never maintain content in both.

**Budget: ~60 lines.** It is prepended to every request; every line costs
context on every turn. The map, the rules, pointers — nothing else. If it
wants to grow, the overflow belongs in `docs/` with a pointer.

```markdown
# <repo name>

<One line: what this repo is.>

## Map

| Path | What it is |
|---|---|
| packages/core     | <one line> |
| packages/cli      | <one line> |
| docs/             | vision, design, status |

## Rules

- <the few rules that matter in every session: build/test commands,
  things agents get wrong in this repo>
- <a conventions pointer, only when a skill's own triggering isn't enough —
  e.g. "Prose in docs and READMEs follows `aganitha-doc-writing`.">

## Deeper

- Decisions and module contracts: docs/design.md
- Current state and TODO: docs/status.md
```

The map answers "what does each module do" for agent and human alike — one
line per entry a newcomer would wonder about. Keeping it current is part of
adding a package (and `aganitha-preflight`'s docs-sync check will catch drift).

**Conventions pointers are the exception, not the pattern.** A skill with a
good description triggers on its own and needs no line here — most don't have
one and shouldn't. Spend a line only on a convention that applies when nobody
asked for it, where the skill has no moment to trigger on. Every pointer costs
context on every turn, against a 60-line budget.

## README — one front door, routed by audience

The README serves three different readers; give each a short section and a
path deeper, rather than one undifferentiated wall:

```markdown
# <name>

<What this is, in one or two sentences — the vision one-liner/analogy.>

## Using it        ← for consumers of the thing
<Install/access, one basic example. Library: an import; service: the URL/endpoint.>

## Developing it   ← for modifiers
<make install && make test. Map in AGENTS.md; decisions in docs/design.md.>

## Running it      ← for builders/deployers (only if it deploys)
<make run locally; how it's deployed. Docker targets if present.>
```

Keep it to one screen per audience. If a section needs more, it links into
`docs/` — the README routes, it doesn't lecture.

## Makefile — the contract

`make` is the single entry point for every operation, in every repo, so
automation and agents never guess. Every repo has one, and it is
**self-describing** — `make help` (the default goal) lists every target,
because every target carries a `## description`.

The standard verbs, same meaning everywhere: `help`, `install`,
`skills-install` (runs `skills-pack update && skills-pack upgrade`), `build`, `test`, `run`
(services/apps), `clean` / `distclean`, `publish` (published packages),
`docker-build` / `docker-publish` (when a Dockerfile exists). A monorepo root
delegates to packages; content repos carry only the verbs that do real work;
`make install && make run` must work locally with no external services.

**The full Makefile treatment — the self-documenting `help` mechanism, the
verb→toolchain wiring, monorepo delegation, publish targets — is owned by the
`aganitha-makefile` skill.** This skill owns only the Makefile's *place* in the
repo shape; how to write it lives there.

## docs/ — earned tiers, not a mandatory stack

A doc that exists must be worth keeping current. The tiers:

| Doc | Required when | Maintained by |
|---|---|---|
| `README.md` + `AGENTS.md` | Always — every repo | everyone; `aganitha-preflight` checks |
| `vision.md` | The repo is a real system or product | `aganitha-vision` skill; revised only if the mission changes |
| `design.md` | Any non-trivial system | `aganitha-design-doc` skill |
| `status.md` + `CHANGELOG.md` | Anything that evolves | `aganitha-preflight` keeps them honest |
| `mental-model.md` | Only when the concepts are numerous or subtle enough to earn it | `aganitha-design-doc` (Step 2) |
| `llms.txt` | Published libraries only | updated when the public API changes |

**Packages inherit the root docs.** A package gets its own `docs/` only if it
is independently published (then: own README and llms.txt at minimum). Don't
stamp five stub files into every package — a stub that never fills in is
worse than absence, because it teaches readers the docs lie.

## Skills — gitignored, recorded by lock file

Project-local skills live in `.claude/skills/` and `.agents/skills/` (that's
where `skills-pack install` puts them) but are **gitignored** — same pattern
as `node_modules/` or `.venv/`. What's committed is `skills-pack.lock.json`,
which `skills-pack install` writes automatically (pack/skill name, source,
args — not a content hash). A fresh clone runs `skills-pack update &&
skills-pack upgrade` before working, rather than getting skills for free from
`git clone`. Both commands are needed: `upgrade` re-runs every recorded
install, but it resolves against the local registry cache and never fetches
for a repo already cached — only `update` refreshes that cache. Note the lock
file records names, not content hashes, so this is closer to `apt upgrade`
than `npm ci`; two people running it at different times can get different
upstream content. `-g` global installs are for
personal preference, not project conventions.

## Checklist (on creating a project or package)

Report each as `[✓]` / `[✗]`:

- [ ] New-repo question asked — and answered with a reason, not a default
- [ ] Layout matches the skeleton (core + thin interfaces; tests present)
- [ ] AGENTS.md exists, has the map, is under ~60 lines
- [ ] CLAUDE.md is exactly `@AGENTS.md`
- [ ] README has the audience sections that apply
- [ ] `make help` works; standard verbs present and real
- [ ] `make install && make test` succeeds from a fresh clone
- [ ] Docs tier matches what the project has earned — no stub padding
- [ ] `.claude/skills/` and `.agents/skills/` gitignored; `skills-pack.lock.json` committed
- [ ] `make skills-install` present and runs `skills-pack update && skills-pack upgrade`
