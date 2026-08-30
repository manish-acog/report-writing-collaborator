"""Renders a completed value map into final report text via one template.

Pure function: no model access, no state. See
docs/general_report_writing.md for the design.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

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


def render(template_path: Path, values: Mapping[str, Mapping[str, object]]) -> str:
    """Substitutes every `{{variable}}` placeholder in template_path.

    Args:
        template_path: A `.md` or `.html` template using `{{variable}}`
            placeholders, plus the reserved `{{references}}` placeholder.
        values: One entry per template variable, each
            `{"status": "found", "value": ..., "citations": [...]}` or
            `{"status": "not_found"}` -- the shape variable_config's output
            schema produces.

    Returns:
        The rendered report text.

    Raises:
        ReportRenderError: the template is missing, doesn't declare
            `{{references}}`, or references a variable not in values.
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
    substitutions[_REFERENCES_KEY] = _render_references(values, template_path.suffix)

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
) -> str:
    citations = _collect_citations(values)
    if not citations:
        return _NO_CITATIONS_HTML if template_suffix == _HTML_SUFFIX else _NO_CITATIONS_MARKDOWN

    formatted = [_format_citation(citation) for citation in citations]
    if template_suffix == _HTML_SUFFIX:
        items = "".join(f"<li>{text}</li>" for text in formatted)
        return f"<ul>{items}</ul>"

    return "\n".join(f"- {text}" for text in formatted)


def _collect_citations(
    values: Mapping[str, Mapping[str, object]],
) -> list[Mapping[str, object]]:
    seen: set[tuple[str, int | None]] = set()
    citations: list[Mapping[str, object]] = []

    for field in values.values():
        if field.get("status") != "found":
            continue
        # citations' precise shape is validated upstream by variable_config's
        # output schema; Mapping[str, object] can't express it statically.
        raw_citations = cast("list[Mapping[str, object]]", field.get("citations", []))
        for citation in raw_citations:
            key = (cast("str", citation["source_id"]), cast("int | None", citation.get("page")))
            if key in seen:
                continue
            seen.add(key)
            citations.append(citation)

    return sorted(
        citations, key=lambda citation: (citation["source_id"], citation.get("page") or 0)
    )


def _format_citation(citation: Mapping[str, object]) -> str:
    page = citation.get("page")
    source_id = citation["source_id"]
    return f"{source_id}, p. {page}" if page is not None else str(source_id)
