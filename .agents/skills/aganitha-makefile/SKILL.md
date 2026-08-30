---
name: aganitha-makefile
description: >
  Write and maintain a Makefile as a project's self-describing automation
  contract. Use when creating a Makefile, adding or changing a make target,
  making `make help` list every target, wiring the standard Aganitha verbs
  (install/build/test/run/publish) to a toolchain, or setting up monorepo
  delegation. The rule this skill enforces everywhere: every target carries a
  `## description`, so `make help` is always complete and accurate. Owns the
  Makefile shape that aganitha-project-setup, the language-convention skills,
  and the publish skills all defer to.
---

# Makefile

`make` is the single public entry point for every operation in a repo, in
every repo, so automation and agents never have to guess how to build, test,
or run it. `package.json` scripts and `uv run` commands are invoked *by* make,
not used as the interface.

**The one rule that makes this work: every Makefile is self-describing.**
`make help` — the default goal — lists every target and what it does, pulled
straight from the targets themselves. A target with no description is invisible
to `make help`, which means it's invisible to the next person and the next
agent. There is no separate list of targets to keep in sync, because the
Makefile *is* the list.

## The self-documenting mechanism

Two halves, and they only work together:

1. **Every target carries a `## description`** on its own line.
2. **`help` is the default goal** and greps those descriptions out.

```makefile
.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	...

test: ## Run all tests
	...
```

`make` with no argument now prints the target list. Add a target without a
`## description` and it silently drops out of `make help` — so the description
isn't optional decoration, it's how the target becomes real. When you add or
rename a target, the help output updates itself; you never maintain a second
copy.

## Standard verbs — same meaning everywhere

These names mean the same thing in every Aganitha repo, so automation and
agents can rely on them without reading the file:

| Target | Meaning | Required |
|---|---|---|
| `help` | List targets with descriptions (the default goal) | Always |
| `install` | Install all dependencies | Always |
| `skills-install` | Run `skills-pack update; skills-pack upgrade` (restore skills from `skills-pack.lock.json`) — `;` not `&&`, so a registry refresh that can't reach every repo still lets the upgrade run from cache | Always — standalone, not a dependency of `install` |
| `build` | Compile / type-check | Always |
| `test` | Run all tests | Always |
| `run` | Run locally | Services and apps |
| `clean` / `distclean` | Remove artifacts / + dependencies | Always |
| `publish` | Publish to the Aganitha registry | Published packages |
| `docker-build` / `docker-publish` | Build / push the image | When a Dockerfile exists |

This is the required baseline, not a whitelist — add whatever project-specific
verbs earn their keep (`lint`, `format`, `validate`, `status`, `seed`), as long
as each carries a real `## description` and does something real. A target that
does nothing is worse than its absence: it teaches readers the Makefile lies.

## Wiring the verbs to a toolchain

The standard verb is the stable name; what it runs is language-specific. The
language-convention skills own the details — this is the index.

**TypeScript / Bun** (see `aganitha-typescript-conventions`):

```makefile
install: ## Install all dependencies
	bun install

build: ## Type-check and emit
	bun run tsc

test: ## Run all tests
	bun test
```

**Python / uv** (see `aganitha-python-conventions`):

```makefile
install: ## Install all dependencies
	uv sync --all-groups

test: ## Run all tests
	uv run pytest

lint: ## Lint and type-check
	uv run ruff format --check . && uv run ruff check . && uv run ty check src/

format: ## Format code
	uv run ruff format .
```

Prefer `uv run <cmd>` over activating a virtualenv; prefer `bun run` over a
bare `node`. In CI or Docker where the tool isn't on PATH, use whatever the
environment provides.

## Publish targets

`publish` always depends on `build`, so a stale or missing build can never be
shipped. The publish command itself is registry-specific — the setup and
credentials live in `aganitha-npm-publish` / `aganitha-pypi-publish`; this is
the target shape.

**npm** — note `npm publish`, not `bun publish` (bun's publish is unreliable
against HTTP Basic Auth registries):

```makefile
publish: build ## Publish to the Aganitha npm registry
	npm publish
```

**PyPI**:

```makefile
build: ## Build the distribution
	uv build

publish: build ## Publish to the Aganitha PyPI registry
	uv publish --publish-url https://pypi.aganitha.ai/
```

## Monorepo delegation

In a monorepo, the root Makefile delegates to the packages: `make test` at the
root runs every package's tests. Each package has its own Makefile with the
same standard verbs. The root's targets still carry `## description`s — `make
help` at the root describes the repo-level operations, and `make help` in a
package describes that package's.

```makefile
test: ## Run every package's tests
	@for pkg in packages/*/; do $(MAKE) -C $$pkg test; done
```

## Non-code and content repos

Not every repo is a coding system. Content repos (docs, registries,
configuration) carry only the verbs that do real work — often just `help` and a
`test` that validates the content — or no Makefile at all if nothing would run.
Never add ceremony targets that do nothing just to complete the standard set;
`[—]` (not applicable) is the correct answer for a verb this repo has no real
work for.

## Local-first

`make install && make run` must work on a laptop with no external services.
Development uses local resources (SQLite, local files); production swaps them
(PostgreSQL) behind the same interface. If `make run` needs a cloud service to
start, the seam is in the wrong place — that's a design finding, not a Makefile
one.

## Checklist

Report each as `[✓]` / `[✗]` / `[—]`:

- [ ] `make` with no argument prints the target list (`.DEFAULT_GOAL := help`)
- [ ] `help` target present, using the grep/awk self-documenting form
- [ ] **Every** target carries a `## description` — run `make help` and confirm
      no target is missing from the output
- [ ] Standard verbs present and real for what this repo is (code vs content)
- [ ] Each verb wired to the project's actual toolchain (bun / uv), not a stale command
- [ ] `publish` depends on `build` (published packages only)
- [ ] Monorepo root delegates to packages; each package has its own Makefile
- [ ] No target that does nothing real
- [ ] `make install && make run` works locally with no external services
