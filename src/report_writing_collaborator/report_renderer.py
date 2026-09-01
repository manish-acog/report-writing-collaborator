"""Renders a completed value map into final report text via one template.

Pure function: no model access, no state. See docs/general_report_writing.md,
docs/citation_enrichment.md, docs/citation_granularity.md,
docs/citation_presentation_cleanup.md, and
docs/citation_marker_enforcement.md for the design.
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
_CITATION_MARKER_PATTERN = re.compile(r"\[\[cite:(\d+)\]\]")
_CITATION_MARKER_RUN_PATTERN = re.compile(r"(?:\[\[cite:\d+\]\])+")
_CITATION_MARKER_TOKEN = "cite:"
_REFERENCES_KEY = "references"
_NOT_FOUND_FALLBACK = "Not addressed in the available evidence."
_NO_CITATIONS_MARKDOWN = "_No cited sources._"
_NO_CITATIONS_HTML = "<p>No cited sources.</p>"
_HTML_SUFFIX = ".html"
_MANIFEST_NAME = "manifest.json"

CitationKey = tuple[str, str | None, int | None]


@dataclass(frozen=True, slots=True)
class _Source:
    source_id: str
    source_role: str | None
    original_filename: str
    original_path: str
    parent_source_id: str | None
    citation_url: str | None


@dataclass(frozen=True, slots=True)
class _Reference:
    number: int
    source: _Source
    page: int | None


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

    placeholder_names = _PLACEHOLDER_PATTERN.findall(template)
    if _REFERENCES_KEY not in placeholder_names:
        raise ReportRenderError(
            f"Template is missing the required {{{{{_REFERENCES_KEY}}}}} "
            f"placeholder: {template_path}"
        )

    fields = _ordered_fields(placeholder_names, values, template_path)
    citations = _collect_citations(fields)
    citation_numbers = {
        _citation_key(citation): number for number, citation in enumerate(citations, start=1)
    }
    substitutions = {name: _render_field(name, field, citation_numbers) for name, field in fields}
    substitutions[_REFERENCES_KEY] = _render_references(
        citations,
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


def _ordered_fields(
    placeholder_names: list[str],
    values: Mapping[str, Mapping[str, object]],
    template_path: Path,
) -> list[tuple[str, Mapping[str, object]]]:
    seen: set[str] = set()
    fields: list[tuple[str, Mapping[str, object]]] = []
    for name in placeholder_names:
        if name == _REFERENCES_KEY or name in seen:
            continue
        if name not in values:
            raise ReportRenderError(
                f"Template references unknown variable '{name}': {template_path}"
            )
        seen.add(name)
        fields.append((name, values[name]))

    return fields


def _render_field(
    field_name: str,
    field: Mapping[str, object],
    citation_numbers: Mapping[CitationKey, int],
) -> str:
    if field.get("status") != "found":
        return _NOT_FOUND_FALLBACK

    value = _stringify(field["value"])
    citations = _field_citations(field)

    def citation_link(marker: re.Match[str]) -> str:
        local_index = int(marker.group(1))
        if local_index >= len(citations):
            raise ReportRenderError(
                f"Citation marker index {local_index} is out of range for field '{field_name}'"
            )
        number = citation_numbers[_citation_key(citations[local_index])]
        return f'<sup><a href="#ref-{number}">{number}</a></sup>'

    def replace(run: re.Match[str]) -> str:
        return ",".join(
            citation_link(marker) for marker in _CITATION_MARKER_PATTERN.finditer(run.group(0))
        )

    rendered = _CITATION_MARKER_RUN_PATTERN.sub(replace, value)
    if _CITATION_MARKER_TOKEN in rendered:
        raise ReportRenderError(f"Unresolved citation marker in field '{field_name}'")

    return rendered


def _stringify(value: object) -> str:
    if isinstance(value, str):
        return value

    raise ReportRenderError(f"No stringifier for value type: {type(value).__name__}")


def _render_references(
    citations: list[Mapping[str, object]],
    template_suffix: str,
    workspace_root: Path,
) -> str:
    if not citations:
        return _NO_CITATIONS_HTML if template_suffix == _HTML_SUFFIX else _NO_CITATIONS_MARKDOWN

    sources = _load_sources(workspace_root)
    references = [
        _resolve_reference(citation, number, sources, workspace_root)
        for number, citation in enumerate(citations, start=1)
    ]
    if template_suffix == _HTML_SUFFIX:
        items = "".join(
            f'<li id="ref-{reference.number}">{_format_html(reference, sources)}</li>'
            for reference in references
        )
        return f"<ol>{items}</ol>"

    return "\n".join(
        f'<a id="ref-{reference.number}"></a>\n'
        f"{reference.number}. {_format_markdown(reference, sources)}"
        for reference in references
    )


def _collect_citations(
    fields: list[tuple[str, Mapping[str, object]]],
) -> list[Mapping[str, object]]:
    seen: set[CitationKey] = set()
    citations: list[Mapping[str, object]] = []

    for _, field in fields:
        if field.get("status") != "found":
            continue
        for citation in _field_citations(field):
            key = _citation_key(citation)
            if key in seen:
                continue
            seen.add(key)
            citations.append(citation)

    return citations


def _field_citations(field: Mapping[str, object]) -> list[Mapping[str, object]]:
    # The precise shape is validated upstream by variable_config's schema;
    # Mapping[str, object] cannot express it statically.
    return cast("list[Mapping[str, object]]", field.get("citations", []))


def _citation_key(citation: Mapping[str, object]) -> CitationKey:
    return (
        cast("str", citation["source_id"]),
        cast("str | None", citation.get("section_id")),
        cast("int | None", citation.get("page")),
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
            parent_source_id=_optional_text(raw_source, "parent_source_id", "workspace source"),
            citation_url=_optional_text(raw_source, "citation_url", "workspace source"),
        )
        # Repeated content can produce multiple source instances with one
        # source_id. Citations identify content, so the first occurrence wins.
        sources.setdefault(source.source_id, source)

    return sources


def _resolve_reference(
    citation: Mapping[str, object],
    number: int,
    sources: Mapping[str, _Source],
    workspace_root: Path,
) -> _Reference:
    source_id = cast("str", citation["source_id"])
    source = sources.get(source_id)
    if source is None:
        raise ReportRenderError(f"Citation references unknown source_id: {source_id}")

    _workspace_file(workspace_root, source.original_path, "preserved source")

    return _Reference(
        number=number,
        source=source,
        page=cast("int | None", citation.get("page")),
    )


def _source_href(source: _Source, page: int | None) -> str:
    if source.citation_url:
        return source.citation_url

    href = quote(source.original_path, safe="/")
    if page is not None and source.original_path.casefold().endswith(".pdf"):
        return f"{href}#page={page}"

    return href


def _format_markdown(reference: _Reference, sources: Mapping[str, _Source]) -> str:
    source = reference.source
    name = _escape_markdown(source.original_filename)
    text = f"[{name}]({_source_href(source, reference.page)})"
    if source.source_role:
        text += f" ({_escape_markdown(source.source_role)})"
    if source.parent_source_id:
        text += f", attached within {_escape_markdown(_parent_name(source, sources))}"
    if reference.page is not None:
        text += f", page {reference.page}"

    return text


def _format_html(reference: _Reference, sources: Mapping[str, _Source]) -> str:
    source = reference.source
    href = html.escape(_source_href(source, reference.page), quote=True)
    name = html.escape(source.original_filename)
    text = f'<a href="{href}">{name}</a>'
    if source.source_role:
        text += f" ({html.escape(source.source_role)})"
    if source.parent_source_id:
        text += f", attached within {html.escape(_parent_name(source, sources))}"
    if reference.page is not None:
        text += f", page {reference.page}"

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
