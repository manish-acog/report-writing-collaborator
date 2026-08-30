---
name: aganitha-cli-writing
description: Apply Aganitha CLI conventions when building a command-line interface in TypeScript or Python. Activates when creating a new CLI, adding commands to an existing CLI, or designing CLI output and error handling. Covers structure, output formatting, help text with examples, flags, configuration, and AI-friendly design. TypeScript uses Commander; Python uses Typer.
---

# CLI Writing

A CLI is a thin shell over core logic: command handlers parse input, call core functions, and format output — business logic lives in `src/core/`, never in handlers. One CLI per project, git-like subcommands, designed for humans and AI agents alike. Reference: [clig.dev](https://clig.dev).

**In existing CLIs:** follow the structure, parser, and output conventions already there. Apply these rules to new CLIs and to new commands in CLIs that already follow them. If a request conflicts with a rule, surface the tension, let the developer decide, and move on — never block.

## Structure

Subcommand structure: `<cli> <group> <command> [flags]`

```
mycli
  auth        login | logout | status
  data        import | export | list
  dev         seed | reset | inspect
```

- Every project gets a `dev` group for developer operations (seed, reset, inspect, debug).
- Groups are nouns. No catch-all shortcuts or prefix abbreviations — they block future commands without breaking existing scripts.

**TypeScript** — entry point `src/cli/index.ts`, parse with **Commander**:

```json
{ "bin": { "mycli": "./src/cli/index.ts" } }
```

**Python** — entry point `src/<package>/cli/main.py`, parse with **Typer**:

```toml
[project.scripts]
mycli = "<package>.cli.main:app"
```

```python
app = typer.Typer(no_args_is_help=True)
app.add_typer(auth.app, name="auth")   # each group is its own Typer in its own module
```

Both: add a `make run` target (`bun run src/cli/index.ts` / `uv run mycli`), with a `## description` like every target — see `aganitha-makefile`.

## Help: Every Command Shows Examples

Help must work at every level — `mycli --help`, `mycli auth --help`, `mycli auth login --help` — and **every command's help includes an `Examples:` section** with real, copy-pasteable invocations. Users and AI agents read examples, not flag descriptions; a command without examples in its help is incomplete.

```
Usage: mycli auth login [options]

Authenticate with the Aganitha registry.

Options:
  --token-file <path>   Path to file containing token [$AGANITHA_TOKEN]
  -h, --help            Display help

Examples:
  $ mycli auth login --token-file ~/.aganitha/token
  $ AGANITHA_TOKEN=abc mycli auth login
```

**Commander** has no built-in examples support — attach them with `addHelpText`:

```typescript
program
  .command("login")
  .description("Authenticate with the Aganitha registry.")
  .option("--token-file <path>", "Path to file containing token [$AGANITHA_TOKEN]")
  .addHelpText("after", `
Examples:
  $ mycli auth login --token-file ~/.aganitha/token
  $ AGANITHA_TOKEN=abc mycli auth login`)
  .action(handle_login);
```

**Typer** renders the command docstring as help, but re-wraps paragraphs — protect the examples block with `\b` (the Click no-rewrap marker) or put it in `epilog`:

```python
@app.command()
def login(token_file: Path = typer.Option(..., help="Path to file containing token [$AGANITHA_TOKEN]")) -> None:
    """Authenticate with the Aganitha registry.

    \b
    Examples:
      mycli auth login --token-file ~/.aganitha/token
      AGANITHA_TOKEN=abc mycli auth login
    """
```

**Root help shows syntax, once it's grown past a handful of commands.** Commander's and Typer's default root `--help` both render a bare name + one-liner table (or, in Python's stdlib `argparse`, an even terser `{cmd1,cmd2,...}` brace list) — no indication of which commands take a required argument versus an optional one. Fine for a CLI with 3-4 commands; once a CLI has more than ~5-6 subcommands, or a mix of commands taking mandatory vs. optional args, override the root help with an explicit `Commands:` block showing each subcommand's own signature:

```
Usage: mycli <command> [options]

Commands:
  login <token>       Authenticate with the Aganitha registry.
  status [project]     Show sync status. Without a project, shows all.
  logout               Clear stored credentials.

Global options:
  -h, --help
  -v, --version
```

**Commander** — override at the root program with `addHelpText`:

```typescript
program.addHelpText("beforeAll", `
Commands:
  login <token>       Authenticate with the Aganitha registry.
  status [project]     Show sync status. Without a project, shows all.
  logout               Clear stored credentials.`);
```

**Typer** — set `epilog` (or a custom `rich_help_panel`) on the root callback rather than relying on the auto-generated command list.

**Verify before finishing:** actually run `--help` at the root, at one group, and at one leaf command, and confirm the examples render as separate lines. Help frameworks silently re-wrap or swallow formatting; running it is the only check that counts.

When a command requiring arguments is called with none, print brief usage (not full help) to stderr and exit `2`. Do not prompt.

## Output

Two modes, always both supported:

| Mode | Behaviour |
|---|---|
| *(default)* | Human-readable, coloured only if stdout is a TTY |
| `--json` | Machine-readable JSON to stdout, no colour |

- **Streams:** results → stdout; errors, warnings, progress, debug → stderr, in both modes.
- **Colour:** strip automatically when piped (`isTTY` / `isatty()`) or when `NO_COLOR` is set; also honour `--no-color`.
- **`--json` shape**, identical across all commands:
  ```json
  { "ok": true, "data": { ... } }
  { "ok": false, "error": { "code": "NOT_FOUND", "message": "..." } }
  ```
- **State changes:** when a command modifies something, say what changed — `✓ Created project @aganitha/my-project`, `✗ Failed to publish — version 1.0.1 already exists`.
- **Responsiveness:** print something within 100ms; show progress for anything longer so the CLI never looks frozen.

In Typer, make `--json` a global option on the root callback and stash it in `ctx.obj`; subcommands read it from `ctx`:

```python
@app.callback()
def main(ctx: typer.Context, json_output: bool = typer.Option(False, "--json")) -> None:
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output
```

## Flags

Use the standard names — do not invent synonyms:

| Flag | Short | Meaning |
|---|---|---|
| `--help` | `-h` | Show help |
| `--version` | | Show version (`mycli/0.3.1`, wired to the package version) |
| `--json` | | Machine-readable output |
| `--quiet` | `-q` | Suppress non-essential output |
| `--dry-run` | | Preview without executing |
| `--no-color` | | Disable colour |
| `--no-input` | | Disable all prompts — fail if input is missing |
| `--output` | `-o` | Output file path |
| `--debug` | `-d` | Verbose debug output to stderr |

- **No secrets in flags** — they leak into `ps` and shell history. Take tokens via environment variables or `--token-file`, never `--token abc123`.
- **`-` means stdin/stdout** wherever a command takes or produces a file: `mycli data import -`.
- Document environment-variable equivalents in help: `--token-file <path>   ... [$AGANITHA_TOKEN]`.

## Non-Interactive by Default

These CLIs are called by scripts and AI agents. If a required argument or flag is missing, do not prompt — print `Error: --token-file is required` to stderr, print the usage line, exit `2`. Support `--no-input` as an explicit contract that prompting is disabled.

Exception: explicitly interactive developer setup flows (`mycli init`, first-run config) may prompt. Keep prompting commands clearly separate from scriptable ones.

**Stdin reading is not prompting.** When a command accepts `stdin` (via `-` or when a file path is omitted), read from `stdin` even if the input source is a TTY — the user may type directly and press Ctrl+D to signal EOF. Do not check `process.stdin.isTTY` / `sys.stdin.isatty()` to block or throw; that breaks piped and interactive use alike.

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Runtime error (operation failed) |
| `2` | Usage error (wrong arguments, missing flags) |

Scripts and agents branch on these — always exit with the right one. In Typer, `raise typer.Exit(code=2)`.

## Configuration Precedence

Highest wins: **CLI flags → environment variables → project config (`.env`, `app.yaml`) → user config (`~/.config/<tool>/config.yaml`) → defaults.**

## Errors

Expected errors: plain language plus a suggested action, to stderr:

```
Error: Cannot write to output.json
  The file may be read-only. Try: chmod +w output.json
```

Unexpected errors (bugs): short message to stderr, exit `1`, full stack trace only under `--debug`. In Python, catch at the top level in `main.py`.

## Thin Shell Over Core

A command handler does three things — validate input, call core, format output:

```typescript
// src/cli/commands/data_import.ts
import { importData } from "../../core/data_import.js";

export async function handle_data_import(file: string, opts: ImportOptions) {
  if (!file) {
    process.stderr.write("Error: file argument is required\n");
    process.exit(2);
  }
  const result = await importData(file, opts);          // core does the work
  if (opts.json) {
    console.log(JSON.stringify({ ok: true, data: result }));
  } else {
    console.log(`✓ Imported ${result.count} records`);
  }
}
```

Python is identical in shape: the Typer command function validates, calls `<package>.core.*`, prints. If a handler grows an `if`-tree of business rules, that logic belongs in core.

## Nice-to-Have

- **Suggest next steps** after multi-step operations: `✓ Project initialised.` then `Next: mycli auth login · mycli dev seed`.
- **`--dry-run`** on anything that deletes, overwrites, or modifies persistent state.
- **Additive changes only:** add flags and commands; never rename or change the behaviour of existing ones — scripts depend on them. Warn before removing.

## Checklist Before Finishing

Run through this against the actual built CLI, not from memory:

- [ ] `--help` works at every level, and **every command's help shows an `Examples:` section** (verified by running it)
- [ ] Once past ~5-6 subcommands, root `--help` shows each one's own signature (`<required>` / `[optional]`), not just the framework's default name + one-liner table
- [ ] Missing required argument → error on stderr + usage line + exit `2` (no prompt)
- [ ] `--json` supported everywhere, emitting `{ "ok": ... }` on stdout
- [ ] Errors and progress go to stderr; results go to stdout
- [ ] Colour disabled when piped or `NO_COLOR` is set
- [ ] No secrets accepted via flags
- [ ] No business logic in command handlers
