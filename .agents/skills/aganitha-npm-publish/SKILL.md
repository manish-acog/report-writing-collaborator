---
name: aganitha-npm-publish
description: Wires up a TypeScript or JavaScript package for publishing to Aganitha's internal npm registry (npm.aganitha.ai). Use this skill whenever someone is creating a new internal npm package, wants to make an existing package publishable to the internal registry, or asks about publishing to @aganitha scope. Also use when setting up a new TypeScript library, SDK, or utility that other Aganitha projects will depend on — even if they don't explicitly ask about publishing. Also use when someone hits 401/403 authentication errors or package-not-found (404) errors with @aganitha packages, or says "internal registry", "private npm", "can't install @aganitha" — the fix is atk login, covered here.
---

# Aganitha NPM Publish Setup

This skill sets up a TypeScript/JavaScript package for publishing to `npm.aganitha.ai`. Work through the steps in order — each one builds on the previous.

---

## Step 1: Verify registry access

```bash
atk doctor
```

If npm registry access shows as not configured, stop here and run
`atk login` first — one LDAP prompt configures npm, PyPI, and Harbor, and it
verifies your credentials actually work against each registry, not just that
a config file exists. Publishing will fail without it.

---

## Step 2: Check and fix the package name

The name must follow exactly: **`@aganitha/<kebab-case-name>`**

- `@aganitha/data-utils` ✓
- `@aganitha/auth-client` ✓
- `@aganitha/DataUtils` ✗ (no camelCase)
- `aganitha-data-utils` ✗ (missing scope)
- `data-utils` ✗ (no scope at all)

Check the `name` field in `package.json` and correct it if needed. The kebab-case name should describe what the package does, not who made it.

---

## Step 3: Wire up package.json

Update `package.json` with these fields. Read the existing file first and merge carefully — don't overwrite unrelated fields.

```json
{
  "name": "@aganitha/your-package-name",
  "version": "0.1.0",
  "private": false,
  "publishConfig": {
    "access": "public",
    "registry": "https://npm.aganitha.ai/"
  },
  "files": [
    "dist",
    "README.md",
    "llms.txt"
  ],
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": {
    ".": {
      "import": "./dist/index.js",
      "types": "./dist/index.d.ts"
    }
  },
  "scripts": {
    "prepublishOnly": "bun run build"
  }
}
```

**Why each field matters:**

- `"private": false` — explicitly permits publishing. If this is missing and `"private": true` is set anywhere, npm will refuse to publish.
- `"publishConfig"` — routes `npm publish` to the internal registry regardless of global config.
- `"files"` — whitelist of what actually gets published. Only `dist/`, `README.md`, and `llms.txt` go to the registry; source files, tests, config, and secrets stay out. This is a whitelist, not a blacklist — if it's not listed here, it doesn't ship.
- `"prepublishOnly"` — builds the package before every publish, so stale or missing `dist/` can never be accidentally published.

Adjust `main`, `types`, and `exports` to match your build tool's actual output. If you output CommonJS too, add `"require": "./dist/index.cjs"` inside `exports["."]`.

---

## Step 4: Add Makefile publish target

Add a `publish` target to your `Makefile`. It depends on `build` so the package
is always compiled fresh, and — like every target — carries a `## description`
so `make help` stays complete (the self-documenting Makefile rule, owned by
`aganitha-makefile`):

```makefile
publish: build ## Publish to the Aganitha npm registry
	npm publish
```

If no `Makefile` exists yet, create one following `aganitha-makefile` — the
standard verbs wired to Bun, with the self-documenting `help` as the default
goal:

```makefile
.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	bun install

build: ## Type-check and emit dist/
	bun run build

test: ## Run all tests
	bun test

publish: build ## Publish to the Aganitha npm registry
	npm publish
```

Note: we use `bun` for everything except `npm publish`. `bun publish` does not work reliably with HTTP Basic Auth registries.

Also ensure `package.json` has a `build` script that produces `dist/` — the Makefile's `build` target calls it:

```json
"scripts": {
  "build": "tsc",
  "prepublishOnly": "bun run build"
}
```

Replace `tsc` with whatever your build tool is (`tsup`, `vite build`, etc.).

---

## Step 5: Add llms.txt

`llms.txt` is the file an LLM (or a developer in a hurry) reads to *use*
your package without reading its source. The test: could an LLM read this
file alone and correctly write code that calls your API? Put it at the
package root — it ships with the package via `files` above.

```
# @aganitha/<package-name>

> <One sentence: what this package does.>

## Install

bun add @aganitha/<package-name>

## Key Concepts

- <Concept>: <one-line definition — only concepts needed to use the API>

## API

<function/class>(<typed signature>): <return type>
  <One-line description.>

## Examples

<One or two complete, runnable examples covering the main use cases.>
```

No vision, no design decisions, no internal architecture — none of that
helps a caller use the API. Update it in the same change whenever the
public API changes (`aganitha-preflight` checks this).

---

## Step 6: Pre-publish checklist

Before publishing for the first time, verify:

- [ ] Package name is `@aganitha/<kebab-case>`
- [ ] `dist/` is produced by `bun run build` — run it and confirm `ls dist/` shows output
- [ ] `README.md` exists and describes what the package does
- [ ] `llms.txt` exists and reflects the current public API
- [ ] `version` in `package.json` is set (start at `0.1.0` for a new package)
- [ ] `atk doctor` shows npm registry access configured
- [ ] No project-level `.npmrc` with credentials exists in the repo — check with `cat .npmrc 2>/dev/null`. If one exists, add `.npmrc` to `.gitignore` immediately. Credentials belong in `~/.npmrc` only.

---

## Publishing

```bash
# Bump version before every publish
npm version patch    # bug fixes
npm version minor    # new features, backwards compatible
npm version major    # breaking changes

# Build and publish
make publish
```

`npm version` does three things automatically: updates `version` in `package.json`, commits that change, and creates a git tag (`v0.1.1`). Make sure your working tree is clean before running it, and push the tag afterward:
```bash
git push --follow-tags
```

`make publish` runs `build` then `npm publish`. The `prepublishOnly` script in `package.json` adds a second safety net — the build always runs.

---

## Common issues

**"This package has been marked as private"** — remove `"private": true` from `package.json` (or set it to `false`).

**Publishing to public npmjs.com instead of internal registry** — `publishConfig.registry` in `package.json` is missing or wrong. That field is what routes `npm publish` to the right place.

**`dist/` is empty or missing** — `bun run build` failed or was never run. Fix the build first; `prepublishOnly` will catch this on future publishes.

**401 Unauthorized during publish** — your credentials are wrong or expired. Run `atk login` again — it verifies against the real registry, so you'll know immediately if it's fixed.
