---
name: aganitha-python-conventions
description: Apply Aganitha Python conventions when writing, reviewing, or structuring Python code. Activates automatically when editing .py files, setting up a new Python project, adding dependencies, or designing a new module. Enforces must-have rules silently and flags deviations conversationally before proceeding. Nice-to-have rules are surfaced once per project and remembered if the user overrides them. Adapted from trailofbits/modern-python.
---

# Python Conventions

## How This Skill Works

**In existing or external codebases:** read the project's established conventions before applying anything. Follow what is already there — pip, poetry, conda, pytest.ini, flat layout, whatever is in place. Surface Aganitha preferences as suggestions, not requirements. Apply these rules fully only when writing new Aganitha code from scratch.

**Must-have rules** apply to new Aganitha code. When a request would violate one, flag it conversationally and ask before proceeding. Overrides last the session — the rule is active again next session.

**Nice-to-have rules** are applied by default. Flag a deviation once per project. If the user says skip, remember it and stay quiet.

Never block. Surface the tension, let the developer decide, move on.

---

## Must-Have

### Toolchain

*Applies to new Aganitha projects. In existing projects, use whatever toolchain is already in place — pip, poetry, conda, mypy. Introduce uv/ruff/ty incrementally if the team agrees, not as a hard requirement.*

| Use | Not |
|---|---|
| `uv` | pip, virtualenv, poetry, pyenv |
| `ruff` | black, flake8, isort, pyupgrade |
| `ty` | mypy, pyright |
| `pytest` | unittest |
| `uv run <cmd>` | `source .venv/bin/activate` |
| `uv add <pkg>` | editing pyproject.toml manually |
| `[dependency-groups]` | `[project.optional-dependencies]` for dev tools |

Prefer `uv run` over activating a virtualenv manually — but in CI systems, Docker, or cloud environments where uv is not available, use whatever activation method the environment provides.

---

### Project Setup

*Applies to new Aganitha projects. In existing projects with a different layout (flat, setup.cfg, requirements.txt), follow the existing structure and migrate only when the team agrees.*

*Repo shape, AGENTS.md, and the docs tiers are owned by the `aganitha-project-setup` skill; the Makefile contract and its self-documenting `help` are owned by `aganitha-makefile`. This section covers only what is Python-specific.*

- Always use the `src/` layout: code under `src/<package>/`, tests under `tests/`, `uv.lock` committed.
- Interface layers (`cli/`, `api/`, `mcp/`) never import from each other — only from `core/`. Core never imports from interface layers.

**Minimum `pyproject.toml`:**

```toml
[project]
name = "aganitha-<moniker>"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[dependency-groups]
dev = ["ruff", "ty", "pytest", "pytest-cov"]  # drop pytest-cov if coverage tracking is not needed

[build-system]
requires = ["uv_build"]
build-backend = "uv_build"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = [
  "E",    # pycodestyle errors
  "W",    # pycodestyle warnings
  "F",    # pyflakes — undefined names, unused imports
  "I",    # isort
  "B",    # flake8-bugbear — likely bugs and design issues
  "C4",   # flake8-comprehensions — simpler comprehensions
  "UP",   # pyupgrade — modern Python syntax
  "SIM",  # flake8-simplify
  "TCH",  # type-checking import organisation
  "RUF",  # ruff-specific rules
]
ignore = ["E501"]  # line length handled by formatter

[tool.pytest.ini_options]
addopts = ["--cov=src"]

[tool.ty.environment]
python-version = "3.11"

[tool.ty.rules]
possibly-unresolved-reference = "error"
unused-ignore-comment = "warn"
```

**Python Makefile wiring** — how the standard verbs (owned by
`aganitha-makefile`) map to the uv toolchain: `install` → `uv sync
--all-groups`, `test` → `uv run pytest`, `publish` → `uv publish --index
aganitha`. Two Python-specific targets on top, each self-documenting per the
Makefile rule:

```makefile
lint: ## Lint and type-check
	uv run ruff format --check . && uv run ruff check . && uv run ty check src/

format: ## Format code
	uv run ruff format .
```

---

### Package Naming

*Applies only when publishing to Aganitha's private PyPI registry. For open-source, client, or third-party projects, follow their naming conventions.*

- All published Aganitha packages use the `aganitha-<moniker>` naming convention on `pypi.aganitha.ai`.
- The moniker is derived from the repo or project name. When first generating a `pyproject.toml`, say: *"Using `aganitha-<moniker>` as the package name for this project. Change if needed."*

---

### Naming & File Structure

- **File and directory names**: `snake_case` — already Python standard.
- **One concept per module**: if you cannot describe a module in one short phrase, it is doing too much.
- **Public surface**: `__init__.py` is the only export boundary. Only expose what callers need. Use `__all__` to declare it explicitly.
- **Interface layers stay outside core**: `cli/`, `api/`, and `mcp/` modules never appear in `core/`. Core modules never import from interface layers.

```python
# src/mypackage/__init__.py
__all__ = ["search", "SearchResult"]

from mypackage.core.search import search, SearchResult
```

---

### Contract-First

Define types and protocols before writing the implementation. The shape of what a function accepts and returns is a decision — make it explicitly.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class SearchResult:
    id: str
    score: float
    excerpt: str

def search(query: str) -> list[SearchResult]: ...
```

Use `Protocol` for structural interfaces (the Python equivalent of TypeScript interfaces):

```python
from typing import Protocol

class DataSource(Protocol):
    def fetch(self, query: str) -> list[dict]: ...
```

If the interface is unclear, that is a signal to think more, not to start coding.

---

### Type Annotations

- **Required on all public functions** — parameters and return types.
- **Required on all class attributes** — use `dataclass` or explicit annotations.
- Internal helpers may omit annotations if the type is obvious from a single expression.
- Use `ty` for checking: `uv run ty check src/`
- No `Any` at public boundaries. Use `object` or a `Protocol` and narrow it.
- Pragmatic `cast()` is acceptable only at third-party library boundaries where types are wrong or missing. Add a comment explaining why.

```python
# Public function — annotate everything
def process(items: list[str], limit: int = 100) -> dict[str, int]:
    ...

# Dataclass — all fields annotated
@dataclass
class Config:
    api_url: str
    timeout_ms: int = 5000
```

---

### Boundary Validation

Validate at system edges. Trust internally.

**Validate:**
- CLI argument parsing
- API request bodies
- Responses from external services
- Config files read from disk

**Trust (no validation needed):**
- Data passed between internal modules
- Return values from your own functions
- Anything type-checked at call time

An intermediate layer that only forwards a value — even typed, even destructured and reassembled — is not a use of that value, and gets no schema of its own. Re-validating or re-narrowing a structure the layer doesn't act on just duplicates the producer's contract in a second place, so the two now have to change together. Let the producer own the shape and the consumer own the validation; the layers between them carry it, they don't re-check it.

Use **Pydantic** for validation at boundaries — only when your code *uses* the structure, not merely when it type-checks it. A layer that annotates a value with a type and passes it on is still passing through, even though the type checker checks the shape at that annotation. If nothing downstream in this module branches on, transforms, or reads a field, do not add a schema. Apply the principle of least knowledge.

```python
from pydantic import BaseModel, HttpUrl

class Config(BaseModel):
    api_url: HttpUrl
    timeout_ms: int

# At the boundary — parse and validate once
config = Config.model_validate(raw_dict)

# Internally — trust the type
def connect(config: Config) -> Connection: ...
```

---

### Law of Demeter

A module should only talk to its immediate dependencies — not to the dependencies of its dependencies.

**Smell** — reaching through objects:
```python
# Bad: processor knows how tax is structured inside Customer
tax = order.customer.address.region.tax_rate * order.total
```

**Better** — ask the object:
```python
# Good: Order knows its own rules
tax = order.calculate_tax()
```

If you find yourself chaining attribute access, ask whether the intermediate object should be doing the work.

---

### Standard-First Gate

Before writing any non-trivial utility or helper, and before choosing any format, protocol, or config structure:

1. Check Python stdlib first.
2. Check well-maintained PyPI packages second.
3. Check whether there is an established standard for the format or protocol.

If a standard covers ~90% of the need, surface the gap and ask:
> *"There is a standard for this (`X`). It covers your use case except for `Y`. Can we adjust the requirement slightly to use it? Interoperability and avoiding custom code are worth a small requirement change if `Y` is not core to the system."*

If the gap is in core domain logic, build it. If it is infrastructure, prefer the standard. Diverge only when better — and only if we're willing to own the difference forever.

---

### pyproject.toml Hygiene

Keep `pyproject.toml` in sync with the code at all times. Drift is a bug.

- `dependencies` match actual imports — no unused packages, no missing ones.
- `[dependency-groups]` separates dev/test/lint tools from runtime deps.
- `name`, `version`, `requires-python` are always set explicitly.
- `uv.lock` is always committed — reproducible installs matter.
- When code changes add or remove an import, update `pyproject.toml` in the same change.

---

### Package Age Check

Before adding a new package or upgrading to a new version:

1. Check the publish date on PyPI.
2. If it is less than **one week old** — flag it before proceeding:
   > *"`<package>==<version>` was published `N` days ago. New packages and versions are a common vector for supply chain attacks. Do you want to wait or proceed anyway?"*

This applies to both new packages and new versions of established packages.

---

### Error Handling

- **Recoverable errors**: return a value. Use `None`, a typed result dataclass, or raise a domain-specific exception the caller is expected to handle.
- **Unexpected / exceptional errors**: raise. Catch at the boundary where you can do something useful.
- Define domain exceptions in `core/exceptions.py` — do not reuse built-in exceptions for domain concepts.
- Keep it simple. Do not introduce `Result`/`Either` types unless the codebase has genuinely complex error-routing needs.

```python
# Domain exception — callers know to handle this
class CandidateNotFound(Exception):
    def __init__(self, candidate_id: str) -> None:
        self.candidate_id = candidate_id
        super().__init__(f"Candidate not found: {candidate_id}")
```

---

### Classes vs Functions

- **Functions by default.** Prefer plain functions and module-level exports.
- **Dataclasses for structured data.** Use `@dataclass(frozen=True)` for value objects.
- **Classes when:**
  - You need subclassing or a plugin/strategy pattern where callers implement specific methods.
  - The object has a meaningful stateful lifecycle (connect, use, disconnect).
  - Use `Protocol` to define the interface before writing the implementation.
- When in doubt, start with a function. Promote to a class only when the pattern becomes real.

```python
# Value object — frozen dataclass
@dataclass(frozen=True)
class Molecule:
    smiles: str
    molecular_weight: float

# Strategy pattern — Protocol + implementations
class Scorer(Protocol):
    def score(self, molecule: Molecule) -> float: ...

class DockingScorer:
    def score(self, molecule: Molecule) -> float: ...
```

---

### Prefer stdlib Patterns

- Use `pathlib.Path` over `os.path` — not `os.path.join(...)`, use `Path(...) / ...`.
- Use `dataclasses` over raw dicts for structured data passed between functions.
- Use `contextlib` for context managers rather than manual `try/finally`.
- Use `logging` over `print` for anything beyond scripts.

---

## Nice-to-Have

### Hyrum's Law

> *Every observable behaviour of your system will eventually be depended on by someone.*

Before adding something to `__all__` or the public `__init__.py` — ask: *am I ready to support this?*

If no, keep it internal. Once something is public, changing it is a breaking change.

---

### Consistent Error Shape

When raising exceptions across a module boundary, use a consistent base class:

```python
class AganithaError(Exception):
    """Base for all domain errors in this package."""
    code: str
    message: str
```

Do not mix bare `Exception` with domain exceptions at the same boundary.

---

### Declarative Over Imperative

When a declarative form is genuinely simpler and equally readable, prefer it. List comprehensions, generator expressions, and `dataclasses` over manual loops and dicts — when it does not require explanation.

---

### Convention Over Configuration

Prefer naming conventions and structural patterns over explicit wiring. If the package layout makes something obvious by position, a config entry is noise.

---

### Additive Changes

When extending a public interface, add optional parameters with defaults. Do not change existing parameter names, types, or remove them. Breaking changes require a new function or a version bump.

---

### Property-Based Testing

For pure functions with complex invariants, use `hypothesis` alongside `pytest`:

```python
from hypothesis import given, strategies as st

@given(st.text())
def test_roundtrip(s: str) -> None:
    assert decode(encode(s)) == s
```
