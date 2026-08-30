---
name: aganitha-pypi-publish
description: Wires up a Python package for publishing to Aganitha's internal PyPI registry (pypi.aganitha.ai). Use this skill whenever someone is creating a new internal Python package, wants to make an existing package publishable to the internal registry, or asks about publishing an aganitha-* Python package. Also use when setting up a new Python library or utility that other Aganitha projects will depend on — even if they don't explicitly ask about publishing. Also use when someone hits 401/403 authentication errors or package-not-found (404) errors with aganitha-* packages, or says "internal PyPI", "private registry", "can't install aganitha-" — the fix is atk login, covered here.
---

# Aganitha PyPI Publish Setup

This skill sets up a Python package for publishing to `pypi.aganitha.ai`. Work through the steps in order.

---

## Step 1: Verify registry access

```bash
atk doctor
```

If PyPI registry access shows as not configured, stop here and run
`atk login` first — one LDAP prompt configures npm, PyPI, and Harbor, and it
verifies your credentials actually work against each registry, not just that
a config file exists. Publishing will fail without it.

---

## Step 2: Check and fix the package name

Distribution name must follow exactly: **`aganitha-<kebab-case-name>`**

- `aganitha-data-utils` ✓
- `aganitha-auth-client` ✓
- `aganitha-DataUtils` ✗ (no camelCase)
- `data-utils` ✗ (missing prefix)

The import name (used in Python code) uses underscores: `aganitha_data_utils`. Both names refer to the same package — the registry uses the hyphenated form, Python imports use the underscore form.

---

## Step 3: Wire up pyproject.toml

Use `pyproject.toml` as the single source of truth — no `setup.py`, no `setup.cfg`. Use `hatchling` as the build backend (modern, fast, zero-config for standard layouts).

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "aganitha-your-package"
version = "0.1.0"
description = "What this package does"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "Proprietary" }
dependencies = []

[[tool.uv.index]]
name = "aganitha"
url = "https://pypi.aganitha.ai/simple"

[tool.hatch.build.targets.wheel]
packages = ["src/aganitha_your_package"]

[tool.hatch.build.targets.sdist]
exclude = [
  "tests/",
  "docs/",
  "scripts/",
  ".github/",
  ".venv/",
]
```

**Why each section matters:**

- `[build-system]` — tells uv and pip how to build the package. Without this, packaging tools don't know what to do.
- `[project]` — the package metadata that appears on the registry.
- `[[tool.uv.index]]` — makes `aganitha-*` dependencies in this package resolve from the internal registry during development.
- `[tool.hatch.build.targets.wheel]` — the whitelist of what gets published. Only the source package goes in; tests, scripts, and config stay out.
- `[tool.hatch.build.targets.sdist]` — excludes dev-only directories from the source distribution as well.

**Source layout:** Put your package code under `src/aganitha_your_package/`. This is the recommended layout for libraries — it prevents accidentally importing the uninstalled package during development.

```
your-project/
├── src/
│   └── aganitha_your_package/
│       ├── __init__.py
│       └── ...
├── tests/
├── pyproject.toml
└── README.md
```

---

## Step 4: Add Makefile publish target

The `publish` target depends on `build`, and — like every target — carries a
`## description` so `make help` stays complete (the self-documenting Makefile
rule, owned by `aganitha-makefile`):

```makefile
build: ## Build the distribution
	uv build

publish: build ## Publish to the Aganitha PyPI registry
	uv publish --publish-url https://pypi.aganitha.ai/
```

If no `Makefile` exists yet, create one following `aganitha-makefile` — the
standard verbs wired to uv, with the self-documenting `help` as the default
goal:

```makefile
.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	uv sync

build: ## Build the distribution
	uv build

test: ## Run all tests
	uv run pytest

publish: build ## Publish to the Aganitha PyPI registry
	uv publish --publish-url https://pypi.aganitha.ai/
```

`uv publish` picks up credentials from `~/.netrc` automatically.

---

## Step 5: Add llms.txt

`llms.txt` is the file an LLM (or a developer in a hurry) reads to *use*
your package without reading its source. The test: could an LLM read this
file alone and correctly write code that calls your API? Put it at the
project root, next to README.md.

```
# aganitha-<package-name>

> <One sentence: what this package does.>

## Install

uv add aganitha-<package-name>

## Key Concepts

- <Concept>: <one-line definition — only concepts needed to use the API>

## API

<function/class>(<typed signature>) -> <return type>
  <One-line description. Import from aganitha_<package_name>.>

## Examples

<One or two complete, runnable examples covering the main use cases.>
```

No vision, no design decisions, no internal architecture — none of that
helps a caller use the API. Update it in the same change whenever the
public API changes (`aganitha-preflight` checks this).

---

## Step 6: Pre-publish checklist

- [ ] Package name is `aganitha-<kebab-case>`
- [ ] `src/aganitha_your_package/__init__.py` exists
- [ ] `README.md` exists and describes what the package does
- [ ] `llms.txt` exists and reflects the current public API
- [ ] `version` in `pyproject.toml` is set (start at `0.1.0`)
- [ ] `uv build` succeeds and produces files in `dist/`
- [ ] `atk doctor` shows PyPI registry access configured

---

## Publishing

```bash
# Bump version before every publish
uvx hatch version patch   # bug fixes
uvx hatch version minor   # new features, backwards compatible
uvx hatch version major   # breaking changes

# Build and publish
make publish
```

`uvx hatch version` updates `version` in `pyproject.toml` in place — the Python equivalent of `npm version`. Unlike npm, it does not create a git commit automatically; commit and tag manually if needed.

`make publish` runs `uv build` then `uv publish`. Always bump the version first — the registry will reject a publish if the version already exists.

---

## Installing your package in another project

Once published, other projects add it as a dependency in their `pyproject.toml`:

```toml
[project]
dependencies = [
  "aganitha-your-package>=0.1.0",
]

[[tool.uv.index]]
name = "aganitha"
url = "https://pypi.aganitha.ai/simple"
```

Then `uv sync` will find it on the internal registry.

---

## Common issues

**401 Unauthorized during publish** — your credentials are wrong or expired. Run `atk login` again — it verifies against the real registry, so you'll know immediately if it's fixed.

**404 / upload endpoint not found** — try appending `/legacy/` to the publish URL:
```bash
uv publish --publish-url https://pypi.aganitha.ai/legacy/
```
Some PyPI-compatible servers expect this path for uploads.

**"File already exists"** — you're trying to publish a version that's already on the registry. Bump the version in `pyproject.toml` and rebuild.

**Package not found after publishing** — there can be a short delay before the package appears in search. Try `uv pip install aganitha-your-package --refresh` to bypass the cache.

**Import fails after install** — confirm the `packages` path in `[tool.hatch.build.targets.wheel]` matches your actual directory name (underscores, not hyphens).
