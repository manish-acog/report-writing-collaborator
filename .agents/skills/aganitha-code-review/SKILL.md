---
name: aganitha-code-review
description: Review code changes before committing or checking in. Use this skill whenever the user asks for a code review, says "review this", "check my code", "review my changes", "before I commit", or finishes implementing a feature and wants a quality pass. Runs two passes — architecture/design coherence and code quality. Default scope is the current diff or PR; widens to the full codebase automatically when changes touch core layers or cross boundaries.
---

# Code Review

Two passes. First the big picture, then the detail.

**Default behaviour:** report findings, do not apply fixes. If the user wants fixes applied, they will ask.

---

## Scope decision

Start with the diff (or the files the user points at). Widen to the full codebase for the architecture pass if any of these are true:
- Changes touch core/domain layer, ports, or interfaces
- The change is a refactor, not a feature addition
- Changes affect multiple layers or modules
- Something feels structurally off even in a small diff

If you widen scope, say so briefly: "Widening to full codebase for architecture pass — changes touch the service layer."

---

## Pass 1 — Architecture & Design

Structural problems compound over time. Look inward first, then at the edges —
most reviews stop at the first and miss the second, and the edges are where
production incidents actually start.

### Inside the boundaries

- **Leaky abstractions** — implementation details bleeding across layer boundaries; callers knowing too much about internals
- **Needless re-validation** — an intermediate layer re-validating, re-typing, or re-narrowing a structure it only forwards (doesn't branch on, transform, or read a field of). Passing through a typed value is not a use of it — type-checking at the assignment doesn't count. This duplicates the producer's contract in a second place, coupling that layer to changes on both ends. Validation belongs where the data is produced and where it's actually used, not in between.
- **Improper boundaries** — layers doing each other's work; wrong dependency direction (inner layer depending on outer)
- **Structural replication** — not just duplicate lines, but duplicate concepts, responsibilities, or logic paths in different places
- **Broken mental model** — names, structures, or concepts that no longer reflect what the code actually does; things that would confuse a new reader
- **Cohesion** — things that change together should live together. Flag logic that conceptually belongs in one place but is scattered across files, or a module split so finely that understanding one operation requires tracing through several files.

### At the edges — where the diff meets something it doesn't control

Only where the diff actually touches one of these — do not invent a hypothetical
external system to review against.

- **Untrusted input** — anything arriving from a user, a file, an upload, or a
  request body. Is it validated before use, or does invalid shape reach logic
  that assumes it's clean?
- **An external call** — another service, a database, a filesystem, a queue.
  What happens when it's slow, returns an error, returns something the wrong
  shape, or times out? Does the caller notice, or does the failure disappear?
- **A trust or auth boundary** — does the code check that the caller is allowed
  to do this, or does it only check that the request is well-formed? Well-formed
  and authorized are different questions.
- **A secret or credential** — where does it come from, and could this change
  cause it to be logged, returned in a response, or committed?

The question at every one of these is the same: what does this code assume
about the world outside it, and what happens the moment that assumption is
wrong?

---

## Pass 2 — Code

Scope: diff only. Three groups.

### Waste — code that shouldn't be there

- **Code smells** — DRY violations, magic values, overly complex conditionals, dead code, unnecessary indirection

- **Hacks and workarounds** — code that patches around a root cause instead of fixing it: special-casing one bad input because upstream sends wrong data, silencing an error instead of handling it, a shim compensating for a broken API. These compound — each hack makes the next more likely. Flag them; the fix belongs at the source.

### Shape — whether the abstraction fits what's actually known

- **Abstraction & function size** — functions doing too much; logic that should be named and extracted; repeated patterns that deserve a shared abstraction. The bar: if you can't describe what a function does in one short phrase, it's doing too much. But don't extract speculatively — only when the pattern is real and the name is obvious.

- **Minimal knowledge** — each function or module should know only what it needs to. Watch for: functions receiving objects but only using one field; logic that reaches across layers to get data; callers that have to understand a function's internals to use it correctly. A chain of dots is the tell:

  ```typescript
  // Smell — processor knows how tax is structured inside Customer
  const tax = order.customer.address.region.taxRate * order.total

  // Better — Order knows its own rules
  const tax = order.calculateTax()
  ```

- **Premature decisions** — the rule is: defer when you genuinely don't know yet, commit when you do. Two failure modes to catch:

  - *Over-engineered too early* (LLM tendency): wrapping a simple value in an object, adding an interface before there's a second implementation, introducing abstraction layers before the pattern is clear. If the shape isn't known yet, the code should be as flat and concrete as possible.

    ```typescript
    // Smell — interface and class for something that only ever has one form
    interface StorageBackend { read(key: string): Promise<string> }
    class LocalStorageBackend implements StorageBackend { ... }

    // Better — until a second backend actually exists, just use fs directly
    ```

  - *Under-committed when the shape is known* (human tendency): hardcoding something that is clearly configurable, leaving a structure loose or vague when the decision has already been made. If you know the shape, say so in the code.

    ```typescript
    // Smell — the base URL is a known config value, not a magic string
    const url = "https://api.internal.co/v2/reports"  // copy-pasted in 4 places

    // Better
    const url = `${config.get("API_BASE_URL")}/v2/reports`
    ```

- **Pure functions** — flag functions that could be pure but aren't: mutating a passed-in object, reading or writing shared state, triggering I/O inside logic that doesn't need to. Pure functions are easier to test, reason about, and move around. If a function can be pure at no real cost, it should be.

- **Separation of concerns for evolvability** — the goal is not reuse for others, but reuse as your own code evolves. When a requirement changes, you should be able to replace one part without rewriting others. Watch for: a single function or module mixing concerns that change at different rates; a library reaching into application logic it shouldn't know about; code so tangled that changing one thing forces touching five others. The test: if the CSV format changes, should the classification logic need to change too? If yes, they're tangled.

  ```typescript
  // Smell — format change and rule change both touch the same function
  function processCSV(filePath: string): Summary {
    return parse(filePath).reduce((acc, [name, amount]) => {
      if (parseFloat(amount) > 1000) acc.highValue.push(name)
      else acc.normal.push(name)
      return acc
    }, { highValue: [], normal: [] })
  }

  // Better — each piece can change without touching the other
  function parseCSV(filePath: string): Row[]   { ... }
  function classifyRows(rows: Row[]): Summary  { ... }
  ```

### Surface — what a reader encounters

- **Readability** — would a teammate understand this in 30 seconds? Four naming checks that commonly slip through:

  - *Avoid abbreviations* — `user` not `usr`, `response` not `resp`. Exceptions: universally understood acronyms (URL, ID, HTTP).
  - *Naming consistency* — variable names should mirror their type. If the type is `SnapshotHistory`, the variable is `snapshot_history`, not `history`. Partial names create silent ambiguity.
  - *Call things what they are* — `retry_count` not `retries` (sounds like the action) and not `attempts` (a synonym that obscures). The name should be the thing, not a paraphrase.
  - *Name functions for what they return, not what they do* — `buffer_with_cells(...)` not `render_buffer(...)`. Imperative names describe process; declarative names describe result. Prefer declarative.

  Also: structure that matches the mental model. No clever tricks that require re-reading.

- **UI hygiene** *(only if UI code is present)* — dead CSS selectors, structure mixed with styling, hardcoded layout values

- **Docs drift** — flag mismatches between the code and design docs, comments, or docstrings. Don't fix them (code may still be in flux) — just call them out so they can be addressed when the code stabilizes

---

## Output format

### Architecture & Design
Group findings as **Must address**, **Should address**, or **Note**.

`file or module` — What the problem is. Why it matters structurally.

### Code
Group findings as **Must fix**, **Should fix**, or **Consider**.

`file:line` — What it is. What to do.

### Docs out of sync
- `docs/design.md` — section X no longer reflects how Y works
- *(flag only — no action needed until code stabilizes)*

### Top priorities
The 3 most important things to fix before committing, in order.

---

## Example findings

**Architecture — Must address**
`src/core/config.ts` — The core module imports from `src/adapters/env.ts` to read environment variables. Core is depending on an adapter — the dependency is pointing the wrong way. Core should not know how config is sourced. Inject the resolved config values at startup; let the adapter read the environment and hand values in, not the other way around.

**Architecture — Should address**
`src/api/routes.ts` — Route handlers call `db.query()` directly, bypassing the service layer. The API layer is making data access decisions that belong in services. When the schema changes, route files change too — they shouldn't need to. Move query logic into services; routes call services.

**Architecture — Must address (edge)**
`src/integrations/billing-client.ts:18` — The new call to the billing API has no timeout and no error handling; a non-2xx response propagates as an unhandled rejection. When the billing service is slow, this hangs the request that called it. Set a timeout, and turn a failed call into a typed error the caller can act on.

**Code — Should fix**
`src/payments/handler.ts:42` — `handlePayment` validates, charges, and sends a confirmation email in one function. These three concerns change independently — a new payment provider shouldn't require touching email logic. Split into `validatePayment`, `chargePayment`, `sendConfirmation`.

---

## Tone

Be direct. One finding per issue. Say what to do, not just what's wrong. Skip anything minor enough that a reasonable engineer would leave it as-is.
