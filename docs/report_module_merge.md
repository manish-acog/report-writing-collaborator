# Design — Merge `report_writing_agent` into `report_writing_collaborator`

## Purpose

Second and final step of the naming cleanup: fold `report_writing_agent`
into `report_writing_collaborator`, so the repo ends with two packages —
`canonical_workspace` (independent) and `report_writing_collaborator` (the
actual report-writing system: rendering, agent, orchestrator, CLI, skills)
— matching the project's own name instead of two oddly-related siblings.
For whoever moves the files.

## Why

`report_writing_agent` undersold its own contents — an `LlmAgent`, an
orchestrator that runs multiple agent calls (not itself "an agent"), a CLI,
and skills. `report_writing_collaborator`, meanwhile, was the *less*
prominent name of the two despite being the one that matches what this
project is actually named after. One package, correctly named, with a real
internal boundary between its ADK-free and ADK-dependent parts, fixes both
problems at once.

## Shape

```
report_writing_collaborator/
├── __init__.py
├── exceptions.py            # unchanged — VariableConfigError, ReportRenderError
├── report_renderer.py       # unchanged, stays top-level — no ADK import, ever
├── variable_config.py       # unchanged, stays top-level
├── agent/                   # everything ADK-dependent, nested and contained
│   ├── __init__.py          # exposes root_agent, same as today
│   ├── agent.py             # file name unchanged — minimizes ADK discovery risk
│   ├── report_orchestrator.py
│   ├── .env.example
│   └── skills/              # sibling of agent.py — required by its
│                             # __file__-relative SKILLS_DIR, must move together
│       ├── evidence-grounding/
│       ├── general-report-writing/
│       └── workspace-summary/
└── cli/
    ├── __init__.py
    └── main.py
```

`report_renderer.py`/`variable_config.py` stay at the top level, not nested
in their own subdirectory — the property that matters is "nothing in them
imports ADK," not "they live in a same-named folder as `agent/`." Adding a
`rendering/` directory just for symmetry would be structure for its own
sake.

## State

None new.

## Scenarios

**`cli/main.py`'s lazy import.** Today: `from report_writing_agent import
report_orchestrator`. After: `from report_writing_collaborator.agent import
report_orchestrator` — same lazy-import placement, same reasoning (`--help`/
`--version` shouldn't pay ADK's `root_agent` construction cost), new path.

**Running `adk web`.** Today, pointed at `src/report_writing_collaborator/agent/`.
After, pointed at `src/report_writing_collaborator/agent/` specifically —
not the whole `report_writing_collaborator/` package, since that also
contains `cli/` and top-level rendering files that aren't agent
directories. Expected to work the same way ADK's discovery already skips
non-agent subdirectories, but this should be verified once implemented,
not assumed.

**Installing the console script.** `[project.scripts]` entry point moves
from `report_writing_agent.cli.main:app` to
`report_writing_collaborator.cli.main:app`.

## Decisions

### Keep `agent.py`'s file name, only move its directory

- **Options:** A — rename the file to reduce the "agent/agent.py"
  repetition. B (chosen) — keep the file named `agent.py`, change only
  which directory it's nested under.
- **Chose:** B.
- **Consequences:** ADK's discovery convention is untouched — only the
  parent directory `adk web` needs to be pointed at changes, not the file
  it's looking for inside it. Smaller, safer change.

### `skills/` moves as a sibling of `agent.py`, not to the package root

- **Options:** A — put `skills/` at `report_writing_collaborator/skills/`,
  matching the top-level `cli/`. B (chosen) — `report_writing_collaborator/agent/skills/`.
- **Chose:** B.
- **Consequences:** `agent.py`'s `SKILLS_DIR = Path(__file__).parent /
  "skills"` is `__file__`-relative, not configured — it has to stay a
  sibling of `agent.py` wherever `agent.py` ends up, or skill discovery
  breaks silently.

### No new custom exceptions for the orchestrator, no scope creep

- **Options:** A — give `report_orchestrator` its own exception types while
  moving it, since this touches the same area. B (chosen) — move the file
  as-is; it still raises plain `RuntimeError` exactly as it does today.
- **Chose:** B.
- **Consequences:** this doc is a move, not a redesign of error handling
  nobody asked to change.

## Not doing

- **Renaming the CLI command itself** (`report-writing-agent`) — flagged as
  an open question below, not decided here by default.
- **A `rendering/` subdirectory for `report_renderer.py`/`variable_config.py`**
  — no property requires it; adding one would be structure without a reason.

## Open questions

**Should the installed CLI command name change too?** Resolved: no. Kept
as `report-writing-agent` — avoids breaking existing invocations for a
cosmetic-only inconsistency.

## Next

Move `agent.py`, `report_orchestrator.py`, `.env.example`, `skills/` into
`report_writing_collaborator/agent/`. Move `cli/` into
`report_writing_collaborator/cli/`. Update `cli/main.py`'s lazy import.
Update `pyproject.toml`: drop `report_writing_agent` from `module-name`,
update `[project.scripts]`'s entry point path. Update every test importing
`report_writing_agent.*`. Update `README.md`'s credential path and `adk
web` instructions if reintroduced. Verify `adk web` discovery from the new
location. Full preflight after.

## Implementation

Implemented as specified. `scripts/smoke_test_report.py` also imported the
moved `report_orchestrator` — not just `cli/main.py` — so it got the same
import update. `tests/conftest.py`'s docstring and comment updated to
reflect the new path. Verified `adk web` discovery is not assumed:
instantiated ADK's own `AgentLoader` against
`src/report_writing_collaborator/agent`, confirming single-agent-directory
detection and `root_agent` loading both work unchanged. Verified with a
built wheel installed into a clean venv outside the checkout.
