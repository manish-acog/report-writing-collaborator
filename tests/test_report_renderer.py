from __future__ import annotations

import json
from pathlib import Path

import pytest

from report_writing_collaborator import ReportRenderError, render

_VALUES = {
    "title": {
        "status": "found",
        "value": "My Report",
        "citations": [{"source_id": "src_a", "section_id": "sec_a", "page": 2}],
    },
    "conclusion": {"status": "not_found"},
}


def _write_template(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def _write_source(
    workspace: Path,
    source_id: str,
    filename: str,
    markdown: str,
    *,
    section_id: str,
    role: str | None = None,
    parent_source_id: str | None = None,
) -> dict[str, object]:
    source_dir = workspace / "sources" / source_id
    normalized_dir = workspace / "normalized" / source_id
    source_dir.mkdir(parents=True)
    normalized_dir.mkdir(parents=True)
    original_path = f"sources/{source_id}/original{Path(filename).suffix}"
    normalized_path = f"normalized/{source_id}/document.md"
    sections_path = f"normalized/{source_id}/document.sections.json"
    (workspace / original_path).write_bytes(b"source")
    (workspace / normalized_path).write_text(markdown, encoding="utf-8")
    (workspace / sections_path).write_text(
        json.dumps(
            {
                "source_id": source_id,
                "sections": [
                    {
                        "section_id": section_id,
                        "start_line": 1,
                        "end_line": len(markdown.splitlines()),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    return {
        "source_id": source_id,
        "source_role": role,
        "original_filename": filename,
        "original_path": original_path,
        "normalized_path": normalized_path,
        "sections_path": sections_path,
        "parent_source_id": parent_source_id,
    }


def _make_workspace(tmp_path: Path, *, protocol_body: str = "Evidence from protocol.") -> Path:
    workspace = tmp_path / "workspace"
    parent = _write_source(
        workspace,
        "src_a",
        "Protocol.pdf",
        f"# Findings\n{protocol_body}\n",
        section_id="sec_a",
        role="protocol",
    )
    child = _write_source(
        workspace,
        "src_b",
        "Appendix.pdf",
        "# Appendix\nAttachment evidence.\n",
        section_id="sec_b",
        parent_source_id="src_a",
    )
    (workspace / "manifest.json").write_text(
        json.dumps({"sources": [parent, child]}),
        encoding="utf-8",
    )
    return workspace


def test_render_substitutes_found_and_not_found_fields(tmp_path: Path) -> None:
    template = _write_template(
        tmp_path, "report.md", "# {{title}}\n\n{{conclusion}}\n\n{{references}}\n"
    )

    result = render(template, _VALUES, _make_workspace(tmp_path))

    assert "# My Report" in result
    assert "Not addressed in the available evidence." in result


def test_render_markdown_references_are_enriched_deduped_and_sorted(tmp_path: Path) -> None:
    template = _write_template(tmp_path, "report.md", "{{title}}{{conclusion}}{{references}}")
    values = {
        **_VALUES,
        "title": {
            **_VALUES["title"],
            "citations": [
                {"source_id": "src_b", "section_id": "sec_b", "page": 3},
                {"source_id": "src_a", "section_id": "sec_a", "page": 2},
                {"source_id": "src_b", "section_id": "sec_b", "page": 3},
            ],
        },
    }

    result = render(template, values, _make_workspace(tmp_path))

    parent = "[Protocol.pdf](sources/src_a/original.pdf) (protocol), p. 2"
    child = "[Appendix.pdf](sources/src_b/original.pdf), attached within Protocol.pdf, p. 3"
    assert result.count(parent) == 1
    assert result.count(child) == 1
    assert result.index(parent) < result.index(child)
    assert "<blockquote><pre># Findings\nEvidence from protocol.</pre></blockquote>" in result
    assert "- src_a" not in result


def test_render_html_references_use_escaped_markup(tmp_path: Path) -> None:
    template = _write_template(
        tmp_path, "report.html", "<h1>{{title}}</h1><div>{{references}}</div>"
    )

    result = render(
        template,
        _VALUES,
        _make_workspace(tmp_path, protocol_body="<script>alert('x')</script>"),
    )

    assert (
        '<ul><li><a href="sources/src_a/original.pdf">Protocol.pdf</a> (protocol), p. 2'
    ) in result
    assert (
        "<blockquote><pre># Findings\n"
        "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;</pre></blockquote>"
    ) in result


def test_render_preview_is_bounded_to_400_characters(tmp_path: Path) -> None:
    template = _write_template(tmp_path, "report.md", "{{title}}{{references}}")

    result = render(
        template, {"title": _VALUES["title"]}, _make_workspace(tmp_path, protocol_body="x" * 450)
    )

    expected_preview = "# Findings\n" + ("x" * 388) + "…"
    assert f"<blockquote><pre>{expected_preview}</pre></blockquote>" in result
    assert ("x" * 389) not in result


def test_render_markdown_escapes_preview_markup(tmp_path: Path) -> None:
    template = _write_template(tmp_path, "report.md", "{{title}}{{references}}")

    result = render(
        template,
        _VALUES,
        _make_workspace(tmp_path, protocol_body="<script>alert('x')</script>"),
    )

    assert "<script>" not in result
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in result


def test_render_citation_without_section_has_no_preview(tmp_path: Path) -> None:
    template = _write_template(tmp_path, "report.md", "{{title}}{{references}}")
    values = {
        "title": {
            "status": "found",
            "value": "Report",
            "citations": [{"source_id": "src_a", "page": 2}],
        }
    }

    result = render(template, values, _make_workspace(tmp_path))

    assert "[Protocol.pdf](sources/src_a/original.pdf) (protocol), p. 2" in result
    assert "<blockquote>" not in result


def test_render_no_citations_uses_fallback_text(tmp_path: Path) -> None:
    md_template = _write_template(tmp_path, "report.md", "{{references}}")
    html_template = _write_template(tmp_path, "report.html", "{{references}}")
    values = {"conclusion": {"status": "not_found"}}
    workspace = _make_workspace(tmp_path)

    assert render(md_template, values, workspace) == "_No cited sources._"
    assert render(html_template, values, workspace) == "<p>No cited sources.</p>"


def test_render_rejects_unknown_source(tmp_path: Path) -> None:
    template = _write_template(tmp_path, "report.md", "{{title}}{{references}}")
    values = {
        "title": {
            "status": "found",
            "value": "Report",
            "citations": [{"source_id": "src_missing"}],
        }
    }

    with pytest.raises(ReportRenderError, match="unknown source_id"):
        render(template, values, _make_workspace(tmp_path))


def test_render_rejects_unknown_section(tmp_path: Path) -> None:
    template = _write_template(tmp_path, "report.md", "{{title}}{{references}}")
    values = {
        "title": {
            "status": "found",
            "value": "Report",
            "citations": [{"source_id": "src_a", "section_id": "sec_missing"}],
        }
    }

    with pytest.raises(ReportRenderError, match="unknown section_id"):
        render(template, values, _make_workspace(tmp_path))


def test_render_rejects_missing_references_placeholder(tmp_path: Path) -> None:
    template = _write_template(tmp_path, "report.md", "{{title}}")

    with pytest.raises(ReportRenderError, match="required"):
        render(template, _VALUES, _make_workspace(tmp_path))


def test_render_rejects_unknown_variable(tmp_path: Path) -> None:
    template = _write_template(tmp_path, "report.md", "{{title}}{{references}}{{nope}}")

    with pytest.raises(ReportRenderError, match="unknown variable 'nope'"):
        render(template, _VALUES, _make_workspace(tmp_path))


def test_render_rejects_missing_template(tmp_path: Path) -> None:
    with pytest.raises(ReportRenderError, match="Cannot read template"):
        render(tmp_path / "does-not-exist.md", _VALUES, _make_workspace(tmp_path))
