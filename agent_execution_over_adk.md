# Design — Agent Execution on Google ADK

## Purpose

Defines the simplest wiring for the report-writing agent to read a
published canonical workspace on Google ADK. Scope is the agent and its
tools/skills only — not report assembly or output rendering, which is
separate work, same way `document_input_preparation.md` is separate from
this. Read by whoever implements or reviews the agent wiring. Supersedes
this doc's own earlier draft, which built custom session persistence,
per-field orchestration, and a Workflow graph before any of it was
needed — cut per the same simplicity pass applied here.

## Why

The agent reads a prepared, immutable workspace and, guided by a skill,
produces evidence-grounded output. Every input-side decision already
exists (`document_input_preparation.md`). The only thing left to design
here is: how does an ADK agent see the workspace, with the least
machinery possible.

## Shape

```text
Workspace mount (read-only)
    ↓
glob / grep / read  — plain FunctionTools
    ↓
LlmAgent  ←  Skill(s) registered (agentskills.io) — agent picks via load_skill
    ↓
whatever the skill asked for
```

- **Workspace mount** — the published `<workspace_id>/<workspace_version>/`
  directory. Exposes nothing; a filesystem the tools read.
- **Tools** — `glob`, `grep`, `read`. Plain Python functions, auto-wrapped
  by ADK into `FunctionTool`s. No shell, no MCP, no ADK Artifacts.
- **Skill** — an `agentskills.io`-spec directory. Carries everything
  domain-specific: what to look for, how, any template, what a finished
  answer looks like. The agent code never needs to know what's inside.
- **LlmAgent** — model via `LiteLlm(...)`, `tools=[glob, grep, read]`,
  `SkillToolset(skills=[...])` registered with whatever skills are
  relevant to the calling context. Which one activates is the model's
  own `load_skill` call, guided by each skill's description — ADK's
  native behavior. We don't write routing logic; we write skills good
  enough that the native mechanism picks right.

## State

Nothing custom. ADK's own `Session` (`InMemorySessionService`, the
default) holds state and the event history — already ADK's audit log,
already logged, nothing to build. No sealing, no custom
`SessionService`, no bespoke "TaskRun" wrapper.

If a task ever needs to survive a process restart, that's the one signal
to add persistence — swap in a `DatabaseSessionService` then, not before.

The workspace itself: immutable, external, referenced by
`workspace_id`/`workspace_version`, never mutated.

## Scenarios

**1. Rigid UX button.** Workspace already published. Backend registers
whatever skill(s) are relevant to this button — often just one — and
builds `LlmAgent(tools=[glob, grep, read], skills=[...])`. The agent
still activates it via its own `load_skill` call; we never bypass that
with app-level routing.

**2. Chat-driven.** Same wiring, a broader registered set. The model's
`load_skill` judgment, guided by skill descriptions, does the same job
it does in Scenario 1 — just choosing among more options.

**3. Extending.** A new report type is a new `agentskills.io` directory
with its own instructions. No agent code changes.

## Decisions

### Tool surface

- **Options:** A (simplest) — plain functions (`glob`/`grep`/`read`), no
  shell. B — a sandboxed shell with an allowlist. C — expose the same
  tools over MCP.
- **Chose:** A.
- **Consequences:** no shell to escape from — no metacharacter/PATH
  injection surface exists because there's no shell interpreting a
  string. MCP (B) stays available later if a non-ADK consumer needs the
  same tools; not needed now.

### Skill selection

- **Options:** A — calling app pre-registers exactly one skill per task,
  deciding for the model. B (simplest, native default) — register
  whatever skills are relevant (one or several), the model chooses via
  `load_skill`, exactly how `SkillToolset` is designed to work.
- **Chose:** B.
- **Consequences:** no selection logic to build or maintain on our side
  — reverses this doc's own earlier choice of A. Skill description
  quality becomes the entire lever for correct selection: a vague or
  overlapping description risks the wrong skill firing. The fix for that
  is a better-written skill, not a routing layer.

### Session persistence

- **Options:** A (simplest) — ADK's default `InMemorySessionService`,
  zero custom code. B — a custom `SessionService` with durable storage
  and sealing, built ahead of a proven need.
- **Chose:** A.
- **Consequences:** nothing survives a process restart today — accepted,
  because nothing currently needs it to. Reverses an earlier draft of
  this doc that picked SQLite + a custom subclass before any real
  restart-survival requirement existed.

### Workspace assets

- **Options:** A (simplest) — Analysis-type tools, if/when needed, read
  the mount directly. B — route through ADK's Artifact service.
- **Chose:** A.
- **Consequences:** no second identity/versioning scheme for bytes
  `WorkspaceBuilder` already made immutable and hashed.

### Orchestration

- **Options:** A (simplest) — one `LlmAgent`, one call, whatever the
  skill's instructions produce. B — split work across grouped or
  per-field sub-calls. C — a graph-based `Workflow`.
- **Chose:** A.
- **Consequences:** no fan-out, no join, no graph to maintain. If a
  skill's task later proves too large for one call, B is the next lever
  (a few independent bounded calls via plain async) — C isn't justified
  by anything named yet.

## Not doing

- **Custom `SessionService` / sealing / a "TaskRun" abstraction** — ADK's
  default is enough until something real needs otherwise.
- **Incremental Working State mutation tools** — a skill's instructions
  and the model's own reasoning carry this; no bespoke tool category.
- **ADK Artifacts for workspace content.**
- **Independent verifier agent, `Workflow` graph engine, per-field or
  grouped fan-out** — none justified by a current requirement.
- **MCP exposure of the tool surface.**
- **Output schema, report template, rendering** — separate, future work,
  symmetric to how input handling is its own doc.

## Open questions

- Output handling has no doc yet.

## Next

Write one real skill for the first report type. Wire one `LlmAgent` with
`glob`/`grep`/`read` and that skill. Run it against one real workspace
from `examples/pdfs/`. Don't build anything else until that's been tried.
