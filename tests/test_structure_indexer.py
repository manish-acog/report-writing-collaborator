from __future__ import annotations

from typing import TYPE_CHECKING

import pymupdf
import pytest

from report_writing_collaborator import (
    DocumentNormalizer,
    FileHashes,
    NormalizedDocument,
    PageHeaderFooter,
    PageMapping,
    SourceSpec,
    StructureIndexer,
    StructureIndexingError,
    Tooling,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_markdown(workspace: Path, source_id: str, text: str) -> str:
    normalized_dir = workspace / "normalized" / source_id
    normalized_dir.mkdir(parents=True)
    (normalized_dir / "document.md").write_text(text, encoding="utf-8")

    return f"normalized/{source_id}/document.md"


def _normalized_document(
    *,
    source_id: str = "src_test00000000",
    normalized_path: str,
    page_map: tuple[PageMapping, ...] = (),
    header_footer: tuple[PageHeaderFooter, ...] = (),
) -> NormalizedDocument:
    return NormalizedDocument(
        source_id=source_id,
        source_instance_id="source_01",
        source_type="pdf",
        original_path=f"sources/{source_id}/original.pdf",
        normalized_path=normalized_path,
        assets=(),
        embedded_files=(),
        links=(),
        page_map=page_map,
        header_footer=header_footer,
        metadata={},
        hashes=FileHashes(source_sha256="0" * 64, normalized_sha256="0" * 64),
        tooling=Tooling(
            normalizer="test", normalizer_version="0", converter=None, converter_version=None
        ),
        warnings=(),
    )


def test_nested_hierarchy_uses_nested_extent(tmp_path: Path) -> None:
    text = "# Title\nintro\n\n## Sub A\ncontent a\n\n## Sub B\ncontent b\n"
    normalized_path = _write_markdown(tmp_path, "src_a", text)
    document = _normalized_document(source_id="src_a", normalized_path=normalized_path)

    structure = StructureIndexer(tmp_path).index_structure(document)

    by_title = {section.title: section for section in structure.sections}
    assert set(by_title) == {"Title", "Sub A", "Sub B"}
    title = by_title["Title"]
    sub_a = by_title["Sub A"]
    sub_b = by_title["Sub B"]

    assert title.parent_section_id is None
    assert title.start_line == 1
    assert title.end_line == 8
    assert sub_a.parent_section_id == title.section_id
    assert sub_a.heading_path == ("Title", "Sub A")
    assert sub_a.start_line == 4
    assert sub_a.end_line == 6
    assert sub_b.parent_section_id == title.section_id
    assert sub_b.end_line == 8
    assert structure.hashes.structure_sha256


def test_duplicate_sibling_titles_get_distinct_ids(tmp_path: Path) -> None:
    text = "# Test System\n## Observations\nfirst\n## Observations\nsecond\n"
    normalized_path = _write_markdown(tmp_path, "src_b", text)
    document = _normalized_document(source_id="src_b", normalized_path=normalized_path)

    structure = StructureIndexer(tmp_path).index_structure(document)

    observations = [s for s in structure.sections if s.title == "Observations"]
    assert len(observations) == 2
    assert observations[0].section_id != observations[1].section_id

    # Determinism: re-indexing the same content yields identical IDs.
    again = StructureIndexer(tmp_path).index_structure(document)
    assert [s.section_id for s in structure.sections] == [s.section_id for s in again.sections]


def test_identical_headings_across_sources_get_distinct_ids(tmp_path: Path) -> None:
    text = "# Test System\n## Observations\nsame text\n"
    path_x = _write_markdown(tmp_path, "src_x", text)
    path_y = _write_markdown(tmp_path, "src_y", text)
    indexer = StructureIndexer(tmp_path)

    structure_x = indexer.index_structure(
        _normalized_document(source_id="src_x", normalized_path=path_x)
    )
    structure_y = indexer.index_structure(
        _normalized_document(source_id="src_y", normalized_path=path_y)
    )

    ids_x = {s.section_id for s in structure_x.sections}
    ids_y = {s.section_id for s in structure_y.sections}
    assert ids_x.isdisjoint(ids_y)


def test_bold_and_plain_titles_share_identity_space(tmp_path: Path) -> None:
    text = "# Root\n## **Foo**\nfirst\n## Foo\nsecond\n"
    normalized_path = _write_markdown(tmp_path, "src_c", text)
    document = _normalized_document(source_id="src_c", normalized_path=normalized_path)

    structure = StructureIndexer(tmp_path).index_structure(document)

    foos = [s for s in structure.sections if s.title == "Foo"]
    assert len(foos) == 2
    assert foos[0].section_id != foos[1].section_id


def test_fenced_code_block_lines_are_not_headings(tmp_path: Path) -> None:
    text = "# Real Heading\n```\n# not a heading\n```\nbody\n"
    normalized_path = _write_markdown(tmp_path, "src_d", text)
    document = _normalized_document(source_id="src_d", normalized_path=normalized_path)

    structure = StructureIndexer(tmp_path).index_structure(document)

    assert [s.title for s in structure.sections] == ["Real Heading"]


def test_source_pages_intersect_section_line_range(tmp_path: Path) -> None:
    text = "# Title\nline2\n## Sub\nline4\nline5\n"
    normalized_path = _write_markdown(tmp_path, "src_e", text)
    page_map = (
        PageMapping(page_number=1, start_line=1, end_line=2),
        PageMapping(page_number=2, start_line=3, end_line=5),
    )
    document = _normalized_document(
        source_id="src_e", normalized_path=normalized_path, page_map=page_map
    )

    structure = StructureIndexer(tmp_path).index_structure(document)

    by_title = {section.title: section for section in structure.sections}
    assert by_title["Title"].source_pages == (1, 2)
    assert by_title["Sub"].source_pages == (2,)


def test_document_with_no_headings_has_empty_sections(tmp_path: Path) -> None:
    normalized_path = _write_markdown(tmp_path, "src_f", "just a paragraph, no headings.\n")
    document = _normalized_document(source_id="src_f", normalized_path=normalized_path)

    structure = StructureIndexer(tmp_path).index_structure(document)

    assert structure.sections == ()
    assert structure.hashes.structure_sha256


def test_missing_markdown_file_is_typed(tmp_path: Path) -> None:
    document = _normalized_document(normalized_path="normalized/src_missing/document.md")

    with pytest.raises(StructureIndexingError, match="Cannot read"):
        StructureIndexer(tmp_path).index_structure(document)


def test_path_escaping_workspace_root_is_rejected(tmp_path: Path) -> None:
    document = _normalized_document(normalized_path="../outside.md")

    with pytest.raises(StructureIndexingError, match="escapes workspace root"):
        StructureIndexer(tmp_path).index_structure(document)


def test_index_structure_after_document_normalizer(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    document = pymupdf.open()
    page = document.new_page()
    # A font-size differential (not a literal "#") is what triggers
    # PyMuPDF4LLM's own heading detection.
    page.insert_textbox(pymupdf.Rect(72, 150, 500, 200), "Chapter One", fontsize=18)
    page.insert_textbox(pymupdf.Rect(72, 220, 500, 600), "Body text.", fontsize=12)
    document.save(source)
    document.close()

    workspace = tmp_path / "workspace"
    normalized = DocumentNormalizer(workspace).normalize_document(SourceSpec(source, "source_01"))

    structure = StructureIndexer(workspace).index_structure(normalized)

    assert structure.source_id == normalized.source_id
    assert [s.title for s in structure.sections] == ["Chapter One"]
    assert structure.sections[0].source_pages == (1,)
