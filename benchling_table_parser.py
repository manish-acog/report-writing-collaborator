from __future__ import annotations

import re
from typing import Any


def _is_markdown_table_separator(line: str) -> bool:
    return bool(re.match(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$", line))


def _split_markdown_table_row(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def _normalize_caption(line: str) -> str:
    caption = line.strip()
    caption = re.sub(r"^#{1,6}\s*", "", caption)
    caption = re.sub(r"^\*\*(.*?)\*\*$", r"\1", caption)
    caption = re.sub(r"^`(.*?)`$", r"\1", caption)
    caption = re.sub(r"\s+", " ", caption)
    return caption.strip(" :-")


def _resolve_caption(lines: list[str], start_index: int) -> str:
    for index in range(start_index - 1, -1, -1):
        candidate = lines[index].strip()
        if not candidate:
            continue
        if candidate.startswith("|") or _is_markdown_table_separator(candidate):
            continue
        if candidate.startswith("!["):
            continue
        normalized = _normalize_caption(candidate)
        if normalized.startswith("File:") or normalized.startswith("- File:"):
            continue
        return normalized or f"Table {start_index + 1}"
    return f"Table {start_index + 1}"


def _normalize_table_shape(headers: list[str], rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    clean_headers = [str(header).strip() for header in headers]
    clean_rows = [[str(cell).strip() for cell in row] for row in rows]

    if clean_headers and all(not header or header.lower() == "none" for header in clean_headers) and clean_rows:
        clean_headers = clean_rows[0]
        clean_rows = clean_rows[1:]

    width = len(clean_headers)
    if width == 0 and clean_rows:
        width = max(len(row) for row in clean_rows)
        clean_headers = [f"Column {index}" for index in range(1, width + 1)]

    fixed_rows: list[list[str]] = []
    for row in clean_rows:
        trimmed_row = row[:width]
        if len(trimmed_row) < width:
            trimmed_row = trimmed_row + ([""] * (width - len(trimmed_row)))
        fixed_rows.append(trimmed_row)

    return clean_headers, fixed_rows


def extract_markdown_tables(
    markdown_text: str,
    *,
    benchling_id: str,
    benchling_url: str | None = None,
) -> list[dict[str, Any]]:
    lines = str(markdown_text or "").replace("\r\n", "\n").split("\n")
    entries: list[dict[str, Any]] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if index + 1 >= len(lines) or "|" not in line or not _is_markdown_table_separator(lines[index + 1]):
            index += 1
            continue

        headers = _split_markdown_table_row(line)
        index += 2

        rows: list[list[str]] = []
        while index < len(lines):
            current = lines[index]
            if not current.strip() or "|" not in current:
                break
            rows.append(_split_markdown_table_row(current))
            index += 1

        headers, rows = _normalize_table_shape(headers, rows)
        if not headers and not rows:
            continue

        provenance_entry: dict[str, str] = {"benchling_id": benchling_id}
        if isinstance(benchling_url, str) and benchling_url.strip():
            provenance_entry["benchling_url"] = benchling_url.strip()

        entries.append(
            {
                "caption": _resolve_caption(lines, index - len(rows) - 2),
                "value": {"headers": headers, "rows": rows},
                "provenance": {
                    "cayuse_sections": [],
                    "benchling_notebooks": [provenance_entry],
                },
            }
        )

    return entries
