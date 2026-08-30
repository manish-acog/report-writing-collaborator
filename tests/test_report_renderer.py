from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from report_writing_collaborator import ReportRenderError, render

if TYPE_CHECKING:
    from pathlib import Path

_VALUES = {
    "title": {
        "status": "found",
        "value": "My Report",
        "citations": [{"source_id": "src_b", "page": 2}, {"source_id": "src_a"}],
    },
    "conclusion": {"status": "not_found"},
}


def _write_template(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_render_substitutes_found_and_not_found_fields(tmp_path: Path) -> None:
    template = _write_template(
        tmp_path, "report.md", "# {{title}}\n\n{{conclusion}}\n\n{{references}}\n"
    )

    result = render(template, _VALUES)

    assert "# My Report" in result
    assert "Not addressed in the available evidence." in result


def test_render_markdown_references_are_deduped_and_sorted(tmp_path: Path) -> None:
    template = _write_template(tmp_path, "report.md", "{{title}}{{conclusion}}{{references}}")
    values = {
        **_VALUES,
        "title": {
            **_VALUES["title"],
            "citations": [
                {"source_id": "src_b", "page": 2},
                {"source_id": "src_a"},
                {"source_id": "src_b", "page": 2},
            ],
        },
    }

    result = render(template, values)

    assert result.count("src_b, p. 2") == 1
    assert result.index("src_a") < result.index("src_b")


def test_render_html_references_use_list_markup(tmp_path: Path) -> None:
    template = _write_template(
        tmp_path, "report.html", "<h1>{{title}}</h1><div>{{references}}</div>"
    )

    result = render(template, _VALUES)

    assert "<ul><li>src_a</li><li>src_b, p. 2</li></ul>" in result


def test_render_no_citations_uses_fallback_text(tmp_path: Path) -> None:
    md_template = _write_template(tmp_path, "report.md", "{{references}}")
    html_template = _write_template(tmp_path, "report.html", "{{references}}")
    values = {"conclusion": {"status": "not_found"}}

    assert render(md_template, values) == "_No cited sources._"
    assert render(html_template, values) == "<p>No cited sources.</p>"


def test_render_rejects_missing_references_placeholder(tmp_path: Path) -> None:
    template = _write_template(tmp_path, "report.md", "{{title}}")

    with pytest.raises(ReportRenderError, match="required"):
        render(template, _VALUES)


def test_render_rejects_unknown_variable(tmp_path: Path) -> None:
    template = _write_template(tmp_path, "report.md", "{{title}}{{references}}{{nope}}")

    with pytest.raises(ReportRenderError, match="unknown variable 'nope'"):
        render(template, _VALUES)


def test_render_rejects_missing_template(tmp_path: Path) -> None:
    with pytest.raises(ReportRenderError, match="Cannot read template"):
        render(tmp_path / "does-not-exist.md", _VALUES)
