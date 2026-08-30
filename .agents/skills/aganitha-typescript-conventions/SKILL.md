---
name: aganitha-typescript-conventions
description: Apply Aganitha TypeScript conventions when writing, reviewing, or structuring TypeScript code. Activates automatically when editing .ts or .tsx files, setting up a new TypeScript project, adding dependencies, or designing a new module. Enforces must-have rules silently and flags deviations conversationally before proceeding. Nice-to-have rules are surfaced once per project and remembered if the user overrides them.
---

# TypeScript Conventions

## How This Skill Works

**In existing or external codebases:** read the project's established conventions before applying anything. Follow what is already there. Surface Aganitha preferences as suggestions, not requirements. Apply these rules fully only when writing new Aganitha code from scratch.

**Must-have rules** apply to new Aganitha code. When a request would violate one, flag it conversationally and ask before proceeding. Overrides last the session — the rule is active again next session.

**Nice-to-have rules** are applied by default. Flag a deviation once per project. If the user says skip, remember it and stay quiet.

Never block. Surface the tension, let the developer decide, move on.

---

## Must-Have

### Project Setup

*Applies to new Aganitha projects. In existing projects, use whatever runtime and module system is already established.*

*Repo shape, AGENTS.md, and the docs tiers are owned by the `aganitha-project-setup` skill; the Makefile contract and its self-documenting `help` are owned by `aganitha-makefile`. This section covers only what is TypeScript-specific.*

- **Runtime**: Bun. Use `bun:test` for tests, `bun run` for scripts. The standard Makefile verbs (owned by `aganitha-makefile`) map to it: `install` → `bun install`, `build` → `bun run tsc`, `test` → `bun test`.
- **Monorepo wiring**: workspace root `package.json` has `"workspaces": ["packages/*"]` and `"private": true`; each package's `tsconfig.json` extends a shared `tsconfig.base.json` at the root.
- **Module system**: ESM everywhere. Every project has `"type": "module"` in `package.json`.
- **Type checking**: `bun run tsc --noEmit` for a type-only check; `bun run tsc` to emit declarations and build output.
- **tsconfig minimum**:
  ```json
  {
    "compilerOptions": {
      "target": "ES2022",
      "module": "ESNext",
      "moduleResolution": "Bundler",
      "strict": true,
      "noUncheckedIndexedAccess": true,
      "exactOptionalPropertyTypes": true,
      "declaration": true,
      "sourceMap": true,
      "esModuleInterop": true,
      "forceConsistentCasingInFileNames": true,
      "skipLibCheck": true
    }
  }
  ```
- **Built-in imports**: always use the `node:` prefix — `node:path`, `node:fs`, `node:crypto`.

---

### Naming & File Structure

- **One concept per module**: if you cannot describe a module in one short phrase, it is doing too much.
- **Public surface**: `index.ts` is the only export boundary. Only export what callers need. Everything else is internal.
- **Interface layers stay outside core**: CLI, API, and MCP server files never appear in `src/core/`. Core modules never import from `src/cli/`, `src/api/`, or `src/mcp/`. Core is a library; interfaces are thin shells around it.

---

### Contract-First

Define the type or interface before writing the implementation. The shape of what a function accepts and returns is a decision — make it explicitly, not as a byproduct of writing the body.

```typescript
// Define first
interface SearchResult {
  id: string;
  score: number;
  excerpt: string;
}

// Then implement
function search(query: string): SearchResult[] { ... }
```

If the interface is unclear, that is a signal to think more, not to start coding.

---

### Typing

- **Explicit return types on all public functions.** Internal helpers may omit them if the type is obvious from a single expression.
- **No `any` at public boundaries.** Use `unknown` and narrow it.
- **Pragmatic `as any`** is acceptable only at third-party library boundaries where the types are wrong or missing. Add a comment explaining why.
- **Zod for validation** — only when your code *uses* the structure, not merely when it type-checks it. A layer that assigns a value to a typed variable and passes it on is still passing through, even though the compiler checks the shape at that assignment. If nothing downstream in this module branches on, transforms, or reads a field, do not add a schema. Apply the principle of least knowledge.

---

### Boundary Validation

Validate at system edges. Trust internally.

**Validate:**
- CLI argument parsing
- API request bodies and query params
- Responses from external services and third-party APIs
- Config files read from disk

**Trust (no validation needed):**
- Types passed between internal modules
- Return values from your own functions
- Anything that TypeScript already guarantees at compile time

An intermediate layer that only forwards a value — even typed, even destructured and reassembled — is not a use of that value, and gets no schema of its own. Re-validating or re-narrowing a structure the layer doesn't act on just duplicates the producer's contract in a second place, so the two now have to change together. Let the producer own the shape and the consumer own the validation; the layers between them carry it, they don't re-check it.

Use Zod at the boundary, derive the TypeScript type from the schema:
```typescript
const config_schema = z.object({
  api_url: z.string().url(),
  timeout_ms: z.number().positive(),
});

type Config = z.infer<typeof config_schema>;
```

---

### Law of Demeter

A module should only talk to its immediate dependencies — not to the dependencies of its dependencies.

**Smell** — reaching through objects:
```typescript
// Bad: processor knows how tax is structured inside Customer
const tax = order.customer.address.region.tax_rate * order.total;
```

**Better** — ask the object:
```typescript
// Good: Order knows its own rules
const tax = order.calculateTax();
```

If you find yourself writing a chain of dots, ask whether the intermediate object should be the one doing the work.

---

### Standard-First Gate

Before writing any non-trivial utility or helper, and before choosing any format, protocol, or config structure:

1. Check Node/Bun built-ins first.
2. Check well-maintained npm packages second.
3. Check whether there is an established standard for the format or protocol (JSON Schema, OpenAPI, MCP, etc.).

If a standard covers ~90% of the need, surface the gap and ask:
> *"There is a standard for this (`X`). It covers your use case except for `Y`. Can we adjust the requirement slightly to use it? Interoperability and avoiding custom code are worth a small requirement change if `Y` is not core to the system."*

If the gap is in core domain logic (from the project's vision or mental model), build it. If it is infrastructure, prefer the standard. Diverge only when better — and only if we're willing to own the difference forever.

---

### Package Naming

*Applies only when publishing to Aganitha registries. For open-source, client, or third-party projects, follow their naming conventions.*

- All published Aganitha packages use the `@aganitha/<moniker>-*` namespace.
- The moniker is derived from the repo or project name. When first generating a `package.json`, say: *"Using `@aganitha/<moniker>-*` as the package prefix for this project. Change if needed."*
- In a monorepo, every package follows the same prefix.

---

### package.json Hygiene

Keep `package.json` in sync with the code at all times. Drift is a bug.

- `dependencies` match actual imports — no unused packages, no missing ones.
- `exports`, `main`, `types` point to files that exist.
- `scripts` stay aligned with the Makefile.
- `name`, `version`, `type` are always set explicitly.
- When code changes add or remove an import, update `package.json` in the same change.

---

### Package Age Check

Before adding a new package or upgrading to a new version:

1. Check the publish date of the package or version.
2. If it is less than **one week old** — flag it before proceeding:
   > *"`<package>@<version>` was published `N` days ago. New packages and versions are a common vector for supply chain attacks. Do you want to wait or proceed anyway?"*

This applies to both new packages and new versions of established packages.

---

### Error Handling

- **Recoverable errors**: return a value. Use `null`, a typed error object, or a union return type.
- **Unexpected / exceptional errors**: throw. Catch at the boundary where you can do something useful.
- Keep it simple. Do not introduce `Result<T, E>` or `Either` types unless the codebase has genuinely complex error-routing needs. Readability over cleverness.

---

### Classes vs Functions

- **Functions by default.** Prefer plain functions and module-level exports.
- **Classes when:**
  - You need subclassing or a plugin/strategy pattern where callers implement specific methods.
  - The object has a meaningful stateful lifecycle (connect, use, disconnect).
- When in doubt, start with a function. Promote to a class only when the pattern becomes real.

---

## Nice-to-Have

### Hyrum's Law

> *Every observable behaviour of your system will eventually be depended on by someone.*

Before exporting a function, type, or constant — ask: *am I ready to support this?*

If the answer is no, keep it internal. Once something is public, changing it is a breaking change regardless of whether it was intended to be part of the API.

---

### Consistent Error Shape

When returning errors across a module boundary, use a consistent structure:

```typescript
interface AppError {
  code: string;      // machine-readable, e.g. "NOT_FOUND", "INVALID_INPUT"
  message: string;   // human-readable
  cause?: unknown;   // original error if wrapping
}
```

Do not mix shapes — some endpoints returning `{ error: string }` and others returning `{ message: string, status: number }` creates integration friction.

---

### `satisfies` Operator

Use `satisfies` when you want to validate that a value conforms to a type without widening the inferred type:

```typescript
// Preserves literal types while checking shape
const routes = {
  home: "/",
  about: "/about",
} satisfies Record<string, string>;

// routes.home is still typed as "/" not string
```

Prefer over explicit type annotation when you need the narrower inference downstream.

---

### Discriminated Unions

Use discriminated unions for type-safe branching instead of boolean flags or string checks:

```typescript
type WorkflowState =
  | { status: "pending" }
  | { status: "running"; started_at: Date }
  | { status: "complete"; result: WorkflowResult }
  | { status: "failed"; error: AppError };
```

Each branch carries exactly the data relevant to that state. No optional fields that are only sometimes populated.

---

### `snake_case` File Names

Prefer `snake_case` for `.ts` file names in new Aganitha projects — it is cross-platform consistent (macOS, Linux) and spell-check friendly. In existing codebases, or when using frameworks that generate `camelCase` or `kebab-case` files (Next.js, Vite, etc.), follow the existing convention. Do not rename files just to enforce this.

---

### Declarative Over Imperative

When a declarative form is genuinely simpler and equally readable, prefer it. Do not apply this mechanically — if the declarative version requires explanation, the imperative version is better.

---

### Convention Over Configuration

Prefer naming conventions and structural patterns over explicit wiring. If the project layout makes something obvious by position, a config entry is noise.

---

### Additive Changes

When extending a public interface, add optional fields. Do not change existing field names, types, or remove fields. Breaking changes require a new interface or a version bump.
