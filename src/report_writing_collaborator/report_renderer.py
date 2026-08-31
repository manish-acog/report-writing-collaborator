"""Renders a completed value map into final report text via one template.

Pure function: no model access, no state. See docs/general_report_writing.md
and docs/citation_enrichment.md for the design.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast
from urllib.parse import quote

from report_writing_collaborator.exceptions import ReportRenderError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

_PLACEHOLDER_PATTERN = re.compile(r"\{\{(\w+)\}\}")
_REFERENCES_KEY = "references"
_NOT_FOUND_FALLBACK = "Not addressed in the available evidence."
_NO_CITATIONS_MARKDOWN = "_No cited sources._"
_NO_CITATIONS_HTML = "<p>No cited sources.</p>"
_HTML_SUFFIX = ".html"
_MANIFEST_NAME = "manifest.json"
_EXCERPT_MAX_CHARS = 400
_ELLIPSIS = "…"


@dataclass(frozen=True, slots=True)
class _Source:
    source_id: str
    source_role: str | None
    original_filename: str
    original_path: str
    normalized_path: str
    sections_path: str
    parent_source_id: str | None


@dataclass(frozen=True, slots=True)
class _Reference:
    source: _Source
    page: int | None
    preview: str | None


def render(
    template_path: Path,
    values: Mapping[str, Mapping[str, object]],
    workspace_root: Path,
) -> str:
    """Substitutes every `{{variable}}` placeholder in template_path.

    Args:
        template_path: A `.md` or `.html` template using `{{variable}}`
            placeholders, plus the reserved `{{references}}` placeholder.
        values: One entry per template variable, each
            `{"status": "found", "value": ..., "citations": [...]}` or
            `{"status": "not_found"}` -- the shape variable_config's output
            schema produces.
        workspace_root: Published workspace containing the citation evidence.

    Returns:
        The rendered report text.

    Raises:
        ReportRenderError: the template or citation evidence is unreadable,
            the template omits `{{references}}`, or a reference is invalid.
    """
    try:
        template = template_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ReportRenderError(f"Cannot read template: {template_path}") from error

    placeholders = set(_PLACEHOLDER_PATTERN.findall(template))
    if _REFERENCES_KEY not in placeholders:
        raise ReportRenderError(
            f"Template is missing the required {{{{{_REFERENCES_KEY}}}}} "
            f"placeholder: {template_path}"
        )

    substitutions = {name: _render_field(field) for name, field in values.items()}
    substitutions[_REFERENCES_KEY] = _render_references(
        values,
        template_path.suffix,
        workspace_root,
    )

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in substitutions:
            raise ReportRenderError(
                f"Template references unknown variable '{name}': {template_path}"
            )
        return substitutions[name]

    return _PLACEHOLDER_PATTERN.sub(replace, template)


def _render_field(field: Mapping[str, object]) -> str:
    if field.get("status") != "found":
        return _NOT_FOUND_FALLBACK

    return _stringify(field["value"])


def _stringify(value: object) -> str:
    if isinstance(value, str):
        return value

    raise ReportRenderError(f"No stringifier for value type: {type(value).__name__}")


def _render_references(
    values: Mapping[str, Mapping[str, object]],
    template_suffix: str,
    workspace_root: Path,
) -> str:
    citations = _collect_citations(values)
    if not citations:
        return _NO_CITATIONS_HTML if template_suffix == _HTML_SUFFIX else _NO_CITATIONS_MARKDOWN

    sources = _load_sources(workspace_root)
    references = [_resolve_reference(citation, sources, workspace_root) for citation in citations]
    if template_suffix == _HTML_SUFFIX:
        items = "".join(f"<li>{_format_html(reference, sources)}</li>" for reference in references)
        return f"<ul>{items}</ul>"

    return "\n".join(f"- {_format_markdown(reference, sources)}" for reference in references)


def _collect_citations(
    values: Mapping[str, Mapping[str, object]],
) -> list[Mapping[str, object]]:
    seen: set[tuple[str, str | None, int | None]] = set()
    citations: list[Mapping[str, object]] = []

    for field in values.values():
        if field.get("status") != "found":
            continue
        # The precise shape is validated upstream by variable_config's schema;
        # Mapping[str, object] cannot express it statically.
        raw_citations = cast("list[Mapping[str, object]]", field.get("citations", []))
        for citation in raw_citations:
            key = (
                cast("str", citation["source_id"]),
                cast("str | None", citation.get("section_id")),
                cast("int | None", citation.get("page")),
            )
            if key in seen:
                continue
            seen.add(key)
            citations.append(citation)

    return sorted(
        citations,
        key=lambda citation: (
            citation["source_id"],
            citation.get("section_id") or "",
            citation.get("page") or 0,
        ),
    )


def _load_sources(workspace_root: Path) -> dict[str, _Source]:
    raw_manifest = _read_json(workspace_root / _MANIFEST_NAME, "workspace manifest")
    raw_sources = raw_manifest.get("sources") if isinstance(raw_manifest, dict) else None
    if not isinstance(raw_sources, list):
        raise ReportRenderError("Workspace manifest has no sources list")

    sources: dict[str, _Source] = {}
    for raw_source in raw_sources:
        if not isinstance(raw_source, dict):
            raise ReportRenderError("Workspace manifest contains an invalid source")

        source = _Source(
            source_id=_required_text(raw_source, "source_id", "workspace source"),
            source_role=_optional_text(raw_source, "source_role", "workspace source"),
            original_filename=_required_text(raw_source, "original_filename", "workspace source"),
            original_path=_required_text(raw_source, "original_path", "workspace source"),
            normalized_path=_required_text(raw_source, "normalized_path", "workspace source"),
            sections_path=_required_text(raw_source, "sections_path", "workspace source"),
            parent_source_id=_optional_text(raw_source, "parent_source_id", "workspace source"),
        )
        # Repeated content can produce multiple source instances with one
        # source_id. Citations identify content, so the first occurrence wins.
        sources.setdefault(source.source_id, source)

    return sources


def _resolve_reference(
    citation: Mapping[str, object],
    sources: Mapping[str, _Source],
    workspace_root: Path,
) -> _Reference:
    source_id = cast("str", citation["source_id"])
    source = sources.get(source_id)
    if source is None:
        raise ReportRenderError(f"Citation references unknown source_id: {source_id}")

    _workspace_file(workspace_root, source.original_path, "preserved source")
    section_id = cast("str | None", citation.get("section_id"))
    preview = _read_preview(workspace_root, source, section_id) if section_id is not None else None

    return _Reference(
        source=source,
        page=cast("int | None", citation.get("page")),
        preview=preview,
    )


def _read_preview(workspace_root: Path, source: _Source, section_id: str) -> str:
    sections_path = _workspace_file(workspace_root, source.sections_path, "section index")
    raw_index = _read_json(sections_path, "section index")
    raw_sections = raw_index.get("sections") if isinstance(raw_index, dict) else None
    if not isinstance(raw_sections, list):
        raise ReportRenderError(f"Section index has no sections list: {sections_path}")

    section = next(
        (
            value
            for value in raw_sections
            if isinstance(value, dict) and value.get("section_id") == section_id
        ),
        None,
    )
    if section is None:
        raise ReportRenderError(
            f"Citation references unknown section_id '{section_id}' for {source.source_id}"
        )

    start_line = section.get("start_line")
    end_line = section.get("end_line")
    if (
        not isinstance(start_line, int)
        or isinstance(start_line, bool)
        or not isinstance(end_line, int)
        or isinstance(end_line, bool)
        or start_line < 1
        or end_line < start_line
    ):
        raise ReportRenderError(f"Section '{section_id}' has invalid line bounds")

    markdown_path = _workspace_file(workspace_root, source.normalized_path, "normalized source")
    try:
        lines = markdown_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ReportRenderError(f"Cannot read normalized source: {markdown_path}") from error
    if end_line > len(lines):
        raise ReportRenderError(f"Section '{section_id}' extends beyond its normalized source")

    excerpt = "\n".join(lines[start_line - 1 : end_line])
    if len(excerpt) <= _EXCERPT_MAX_CHARS:
        return excerpt

    return excerpt[: _EXCERPT_MAX_CHARS - len(_ELLIPSIS)] + _ELLIPSIS


def _format_markdown(reference: _Reference, sources: Mapping[str, _Source]) -> str:
    source = reference.source
    name = _escape_markdown(source.original_filename)
    path = quote(source.original_path, safe="/")
    text = f"[{name}]({path})"
    if source.source_role:
        text += f" ({_escape_markdown(source.source_role)})"
    if source.parent_source_id:
        text += f", attached within {_escape_markdown(_parent_name(source, sources))}"
    if reference.page is not None:
        text += f", p. {reference.page}"
    if reference.preview is None:
        return text

    preview = f"<blockquote><pre>{html.escape(reference.preview)}</pre></blockquote>"
    return f"{text}\n{preview}"


def _format_html(reference: _Reference, sources: Mapping[str, _Source]) -> str:
    source = reference.source
    path = html.escape(quote(source.original_path, safe="/"), quote=True)
    name = html.escape(source.original_filename)
    text = f'<a href="{path}">{name}</a>'
    if source.source_role:
        text += f" ({html.escape(source.source_role)})"
    if source.parent_source_id:
        text += f", attached within {html.escape(_parent_name(source, sources))}"
    if reference.page is not None:
        text += f", p. {reference.page}"
    if reference.preview is not None:
        text += f"<blockquote><pre>{html.escape(reference.preview)}</pre></blockquote>"

    return text


def _parent_name(source: _Source, sources: Mapping[str, _Source]) -> str:
    parent = sources.get(source.parent_source_id or "")
    if parent is None:
        raise ReportRenderError(
            f"Source '{source.source_id}' references unknown parent_source_id: "
            f"{source.parent_source_id}"
        )

    return parent.original_filename


def _workspace_file(workspace_root: Path, relative_path: str, label: str) -> Path:
    root = workspace_root.resolve()
    path = (root / relative_path).resolve()
    if path != root and root not in path.parents:
        raise ReportRenderError(f"{label.capitalize()} path escapes workspace: {relative_path}")
    if not path.is_file():
        raise ReportRenderError(f"Cannot read {label}: {path}")

    return path


def _read_json(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ReportRenderError(f"Cannot read {label}: {path}") from error
    except json.JSONDecodeError as error:
        raise ReportRenderError(f"Invalid JSON in {label}: {path}") from error


def _required_text(data: Mapping[str, object], key: str, label: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReportRenderError(f"{label.capitalize()} has invalid {key}")

    return value


def _optional_text(data: Mapping[str, object], key: str, label: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ReportRenderError(f"{label.capitalize()} has invalid {key}")

    return value


def _escape_markdown(value: str) -> str:
    escaped = html.escape(value)
    for character in ("\\", "`", "*", "_", "[", "]"):
        escaped = escaped.replace(character, f"\\{character}")

    return escaped
