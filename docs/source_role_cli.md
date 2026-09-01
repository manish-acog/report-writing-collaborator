# Design — `--file-role` / `--benchling-role`

## Purpose

For whoever wires `source_role` into `cli/main.py`. `FileSource.source_role`
and `ElnSource.source_role` already exist end-to-end — `workspace-summary`
already reads them, `report_renderer` already renders them into citations —
but the CLI never sets them. Every source built through `report-writing-agent`
today has `source_role: None`, unconditionally.

## Why

`source_role` and `source_type` answer different questions.
`source_type` (`"pdf"`, `"eln"`, ...) is free — `workspace-summary` reads it
straight from `manifest.json`, no CLI wiring needed — and it already tells
the model *how* a source arrived. It stops being enough the moment there's
more than one source of the same type: two PDFs (`protocol.pdf`, `sop.pdf`)
or two Benchling entries (a primary dosing-records entry, a separate
necropsy-findings entry) are indistinguishable by type alone. `source_role`
exists specifically to carry *what a source means for this report*,
independent of how it was fetched — the CLI just has no way to set it today.

## Shape

- **`--file-role`** (new, repeatable) — paired by position with `--file`,
  within that list only.
- **`--benchling-role`** (new, repeatable) — paired by position with
  `--benchling-entry-id`, within that list only.
- **`cli/main.py._file_sources` / `_eln_sources`** — gain a `roles: list[str]`
  parameter; pass `source_role=roles[index] if index < len(roles) else None`
  when constructing each `FileSource`/`ElnSource`.

Nothing downstream changes — `FileSource.source_role`, `ElnSource.source_role`,
`ManifestSource.source_role`, `workspace-summary`'s structural pass, and
`report_renderer`'s citation rendering all already exist and already work;
this doc only closes the CLI's own gap.

## State

None new.

## Scenarios

**One file, one Benchling entry (the common case).** Neither flag is given.
`source_type` alone already disambiguates (`pdf` vs. `eln`) — role would be
redundant here, and stays `None`, exactly like today.

**Two Benchling entries with different jobs.**
```
report-writing-agent --file protocol.pdf \
  --benchling-entry-id etr_dosing_grpA \
  --benchling-entry-id etr_necropsy_data \
  --benchling-role dosing_records \
  --benchling-role necropsy_findings
```
`manifest.json` records `source_role: "dosing_records"` and
`source_role: "necropsy_findings"` for the two entries. `workspace-summary`
reads this directly instead of inferring purpose from content; a citation
to either renders `(dosing_records)`/`(necropsy_findings)`, the same
mechanism that already renders `(protocol)` for a role-tagged file today.

**Fewer roles than sources.** `--file protocol.pdf --file sop.pdf --file-role protocol`
— only the first file gets a role; the second gets `None`. Role stays
optional per source, never required for all.

## Decisions

### Two flags, paired by position within their own list — not one merged flag, not inline syntax

- **Options:** A — one `--source-role` list, paired by combined position
  across `--file` and `--benchling-entry-id` in command-line order. B —
  inline `path:role` / `entry_id:role` syntax. C (chosen) — separate
  `--file-role`/`--benchling-role`, each paired only within its own list.
- **Chose:** C.
- **Consequences:** A is rejected — merging two independently-ordered lists
  into one combined position count is exactly the kind of off-by-one a user
  won't notice until the wrong citation gets the wrong role. B is rejected —
  colons collide with Windows drive letters (`C:\...`), a landmine this
  project already paid down once this session (`docs/libreoffice_path_fix.md`).
  C mirrors how `_file_sources`/`_eln_sources` already enumerate
  independently today — no new pairing concept, just one more parallel list
  per existing list.

### No default role for Benchling entries

- **Options:** A — default unset Benchling entries to a fixed role like
  `"notebook"`. B (chosen) — no default; unset stays `None`, identically
  for files and Benchling entries.
- **Chose:** B.
- **Consequences:** a fixed default role would only restate what
  `source_type: "eln"` already says for free — new field, no new
  information. `source_role`'s value is disambiguating *within* a type;
  a Benchling-specific default undermines that by making the common,
  unambiguous case (one entry) carry a label that means nothing beyond
  what type already conveys.

## Not doing

- **Validating role values against a fixed vocabulary** — free-text, same
  as every other CLI string input here; no enum to maintain.
- **Making a role required** — stays fully optional for both source kinds,
  same as today's unset behavior.

## Open questions

None blocking.

## Implementation

`--file-role`/`--benchling-role` added to `main()`, `list[str] | None`,
repeatable, `show_default=False`. Threaded through `_CliOptions`,
`_file_sources(paths, roles)`, `_eln_sources(entry_ids, roles)` --
`source_role=roles[index - 1] if index - 1 < len(roles) else None`, paired
by position within each flag's own list. Tests:
`test_file_sources_pairs_roles_by_position`,
`test_file_sources_leaves_remainder_unset_when_fewer_roles`,
`test_file_sources_defaults_to_no_roles`,
`test_eln_sources_pairs_roles_by_position`,
`test_eln_sources_leaves_remainder_unset_when_fewer_roles`, and an
end-to-end `test_cli_wires_file_and_benchling_roles_by_position`.
Existing CLI tests (no roles given) unaffected.
