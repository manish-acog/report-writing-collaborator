# Design — LibreOffice Path Portability Fix

## Purpose

For whoever ports the LibreOffice fixes made and verified on a separate
Windows checkout back into this repo: `cli/main.py`'s missing
`LIBREOFFICE_PATH` env var wiring, and `document_normalizer.py`'s ephemeral
conversion-profile path. Neither fix is in this checkout yet.

## Why

Running `report-writing-agent` against a Benchling entry plus a PDF failed
on Windows with two real, distinct bugs, not one:

1. Bare `soffice` on Windows doesn't reliably resolve to `soffice.com`
   (the console-subsystem binary) — PowerShell's bare-name resolution
   ignored `PATHEXT` order and launched `soffice.exe`, which pops a
   blocking console instead of running headless.
2. The ephemeral LibreOffice conversion profile was nested under the
   workspace's own staging directory
   (`.workspaces/<id>/.staging-.../debug/conversion_logs/<src>/tmpXXXX/profile/...`).
   LibreOffice's own profile cache nests several levels deeper still,
   pushing the total path length past Windows' 260-char `MAX_PATH` —
   confirmed 286 chars — and LibreOffice crashes (`0xC0000409`) rather
   than erroring cleanly.

Both are already fixed and verified on the Windows checkout. Neither
requires platform-detection code: bug 1's fix is a plain env var whose
Windows-specific value lives in a `.env` file, not in code; bug 2's fix
(root the ephemeral profile in system temp instead of under staging) is
strictly better on every platform, not a Windows-only workaround — Mac and
Linux never hit `MAX_PATH` at this depth, but the ephemeral profile had no
architectural reason to live inside the durable workspace tree there
either.

## Shape

- **`WorkspaceConfig.libreoffice_path`** (`workspace_builder.py`, already
  exists, default `"soffice"`) — unchanged; gains a real way to be set
  from the CLI.
- **`cli/main.py`** — reads a new `LIBREOFFICE_PATH` env var, the same
  pattern already used for `BENCHLING_API_KEY`/`BENCHLING_URL`, passed
  into `WorkspaceConfig.libreoffice_path`. Unset: default `"soffice"`,
  unchanged from today.
- **`src/report_writing_collaborator/agent/.env.example`** — documents
  `LIBREOFFICE_PATH`, with `soffice.com` as the Windows example value.
- **`document_normalizer.py`** — the ephemeral profile directory
  (currently `tempfile.TemporaryDirectory(dir=conversion_dir)`) roots in
  system temp instead (`tempfile.TemporaryDirectory()`, no `dir=`).
  `conversion_dir / "converted.pdf"` — the intentional, permanent debug
  artifact — is untouched; only the ephemeral, cleaned-up-after-use
  profile moves.

## State

None new. The ephemeral profile is, and remains, throwaway state cleaned
up by `TemporaryDirectory`'s own context manager — it just roots somewhere
else.

## Scenarios

**Windows run, `LIBREOFFICE_PATH` unset.** `soffice` still resolves
ambiguously — this fix doesn't make Windows work with zero configuration,
it makes correct configuration possible and effective. Setting
`LIBREOFFICE_PATH=soffice.com` fixes bug 1; the profile-path fix prevents
the `MAX_PATH` crash regardless of whether bug 1's env var is set.

**Mac/Linux run, `LIBREOFFICE_PATH` unset.** `libreoffice_path` still
defaults to `"soffice"`, identical to today. The ephemeral profile lands
in system temp instead of under `debug/conversion_logs/` — invisible
behaviorally: same conversion result, different location for throwaway
state nobody inspects.

**Debugging a stuck conversion.** `conversion_dir / "converted.pdf"` and
any other intentional debug artifacts stay exactly where they are today.
Someone inspecting `debug/conversion_logs/<source_id>/` sees the same
output PDF as before this change.

## Decisions

### `LIBREOFFICE_PATH` is a plain env var, no platform detection

- **Options:** A — detect the OS in code, pick `soffice.com` vs. `soffice`
  automatically. B (chosen) — one env var, user-supplied, default
  unchanged.
- **Chose:** B.
- **Consequences:** no OS-detection code to get wrong (WSL, Wine,
  non-standard installs would all break a hardcoded platform check). The
  Windows-specific knowledge lives in the Windows user's own `.env`,
  exactly like every other environment-specific value already does in
  this project.

### Ephemeral profile roots in system temp unconditionally, not just on Windows

- **Options:** A — branch on `platform.system() == "Windows"`, leave
  Mac/Linux nested under staging. B (chosen) — always root it in system
  temp, every platform.
- **Chose:** B.
- **Consequences:** one code path, not two to test and maintain. Same
  reasoning already applied in `docs/extraction_session_persistence.md`
  ("`sessions.db` sits beside `manifest.json`, not inside the hashed
  workspace tree") — ephemeral machinery state doesn't belong inside the
  durable workspace on any platform; Windows' `MAX_PATH` just made the
  existing structural looseness fatal there first.

### Debug artifact location is untouched

- **Options:** A — move `converted.pdf` alongside the profile into system
  temp too, since it's the same code region. B (chosen) — only the
  ephemeral profile moves.
- **Chose:** B.
- **Consequences:** no change to how a failed conversion gets debugged
  today. Scoped to the actual bug — ephemeral-profile depth — not a
  broader reorganization nobody asked for.

## Not doing

- **Platform-detection or OS-branching code anywhere** — rejected in both
  decisions above.
- **Moving `converted.pdf` or other intentional debug output.**
- **Auto-discovering a LibreOffice install path** (e.g. scanning common
  Windows install locations) — the user supplies `LIBREOFFICE_PATH`; no
  discovery heuristic added.

## Open questions

None blocking — both fixes are already implemented and verified on the
Windows checkout; this is a port, not new design work.

## Implementation

`cli/main.py` reads `LIBREOFFICE_PATH` (`os.environ.get(...) or "soffice"`,
matching the existing `REPORT_AGENT_VISION_MODEL` fallback idiom so a
blank `.env` line doesn't override the default with an empty string) into
`WorkspaceConfig.libreoffice_path`; documented in `.env.example`.
`document_normalizer._pdf_path` roots the ephemeral profile directory in
system temp (`tempfile.TemporaryDirectory()`, no `dir=`); `converted.pdf`
untouched. Baseline on this checkout: `test_document_normalizer.py` was
12/12 passing before this change (no pre-existing failures here, unlike
the Windows checkout's noted 3) and remains 12/12 after.
