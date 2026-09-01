from __future__ import annotations

import glob
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pymupdf
import pytest

from canonical_workspace import (
    DocumentNormalizer,
    ElnSource,
    FileSource,
    WorkspaceBuildError,
    WorkspaceConfig,
    build_workspace,
)
from report_writing_collaborator import render

if TYPE_CHECKING:
    from pathlib import Path


def _make_pdf(path: Path, title: str) -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(72, 150, 500, 200), title, fontsize=18)
    page.insert_textbox(pymupdf.Rect(72, 220, 500, 600), "Body text.", fontsize=12)
    document.save(path)
    document.close()


def _make_pdf_with_attachments(
    path: Path,
    title: str,
    attachments: list[tuple[str, bytes]],
) -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(72, 150, 500, 200), title, fontsize=18)

    for name, content in attachments:
        document.embfile_add(name, content, filename=name)

    document.save(path)
    document.close()


def _staging_dirs(publish_root: Path, workspace_id: str) -> list[str]:
    return glob.glob(str(publish_root / workspace_id / ".staging-*"))


def test_build_workspace_single_source(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    _make_pdf(source, "Report Title")
    config = WorkspaceConfig(publish_root=tmp_path / "published")

    manifest = build_workspace(
        [FileSource(path=source, source_instance_id="source_01", source_role="protocol")],
        config,
    )

    assert manifest.workspace_id.startswith("ws_")
    assert manifest.workspace_version == 1
    assert manifest.previous_version is None
    assert manifest.workspace_state == "published"
    assert len(manifest.sources) == 1
    assert manifest.sources[0].source_role == "protocol"
    assert manifest.sources[0].parent_source_id is None
    assert manifest.sources[0].original_filename == "sample.pdf"

    published_dir = config.publish_root / manifest.workspace_id / "1"
    assert (published_dir / "manifest.json").is_file()
    assert (published_dir / manifest.sources[0].sections_path).is_file()
    assert (published_dir / manifest.sources[0].normalized_path).is_file()
    assert not _staging_dirs(config.publish_root, manifest.workspace_id)

    on_disk = json.loads((published_dir / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["workspace_id"] == manifest.workspace_id
    assert on_disk["sources"][0]["source_id"] == manifest.sources[0].source_id
    assert on_disk["sources"][0]["original_filename"] == "sample.pdf"


def test_build_workspace_multiple_sources_have_distinct_section_ids(tmp_path: Path) -> None:
    source_a = tmp_path / "a.pdf"
    source_b = tmp_path / "b.pdf"
    _make_pdf(source_a, "Shared Title")
    _make_pdf(source_b, "Shared Title")
    config = WorkspaceConfig(publish_root=tmp_path / "published")

    manifest = build_workspace(
        [
            FileSource(path=source_a, source_instance_id="source_01"),
            FileSource(path=source_b, source_instance_id="source_02"),
        ],
        config,
    )

    assert len(manifest.sources) == 2
    assert manifest.sources[0].source_id != manifest.sources[1].source_id
    published_dir = config.publish_root / manifest.workspace_id / "1"
    section_files = [
        json.loads((published_dir / source.sections_path).read_text(encoding="utf-8"))
        for source in manifest.sources
    ]
    section_ids_a = {s["section_id"] for s in section_files[0]["sections"]}
    section_ids_b = {s["section_id"] for s in section_files[1]["sections"]}
    assert section_ids_a.isdisjoint(section_ids_b)


def test_duplicate_source_instance_id_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    _make_pdf(source, "Title")
    config = WorkspaceConfig(publish_root=tmp_path / "published")

    with pytest.raises(WorkspaceBuildError, match="Duplicate source_instance_id"):
        build_workspace(
            [
                FileSource(path=source, source_instance_id="source_01"),
                FileSource(path=source, source_instance_id="source_01"),
            ],
            config,
        )


def test_empty_sources_is_rejected(tmp_path: Path) -> None:
    config = WorkspaceConfig(publish_root=tmp_path / "published")

    with pytest.raises(WorkspaceBuildError, match="At least one source"):
        build_workspace([], config)


def test_new_version_chains_to_previous(tmp_path: Path) -> None:
    source_v1 = tmp_path / "v1.pdf"
    source_v2 = tmp_path / "v2.pdf"
    _make_pdf(source_v1, "Version One")
    _make_pdf(source_v2, "Version Two")
    config = WorkspaceConfig(publish_root=tmp_path / "published")

    manifest_v1 = build_workspace(
        [FileSource(path=source_v1, source_instance_id="source_01")], config
    )
    manifest_v2 = build_workspace(
        [FileSource(path=source_v2, source_instance_id="source_01")],
        WorkspaceConfig(
            publish_root=config.publish_root,
            workspace_id=manifest_v1.workspace_id,
            previous_version=manifest_v1.workspace_version,
        ),
    )

    assert manifest_v2.workspace_id == manifest_v1.workspace_id
    assert manifest_v2.workspace_version == 2
    assert manifest_v2.previous_version == 1
    workspace_dir = config.publish_root / manifest_v1.workspace_id
    assert (workspace_dir / "1" / "manifest.json").is_file()
    assert (workspace_dir / "2" / "manifest.json").is_file()


def test_previous_version_must_exist(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    _make_pdf(source, "Title")
    config = WorkspaceConfig(
        publish_root=tmp_path / "published",
        workspace_id="ws_does-not-exist",
        previous_version=1,
    )

    with pytest.raises(WorkspaceBuildError, match="not found"):
        build_workspace([FileSource(path=source, source_instance_id="source_01")], config)


def test_previous_version_requires_workspace_id(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    _make_pdf(source, "Title")
    config = WorkspaceConfig(publish_root=tmp_path / "published", previous_version=1)

    with pytest.raises(WorkspaceBuildError, match="requires workspace_id"):
        build_workspace([FileSource(path=source, source_instance_id="source_01")], config)


def test_reusing_workspace_id_without_previous_version_fails_fast(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    _make_pdf(source, "Title")
    config = WorkspaceConfig(publish_root=tmp_path / "published")
    manifest = build_workspace([FileSource(path=source, source_instance_id="source_01")], config)

    with pytest.raises(WorkspaceBuildError, match="already exists"):
        build_workspace(
            [FileSource(path=source, source_instance_id="source_01")],
            WorkspaceConfig(publish_root=config.publish_root, workspace_id=manifest.workspace_id),
        )


def test_failed_build_preserves_staging_for_inspection(tmp_path: Path) -> None:
    good_source = tmp_path / "good.pdf"
    bad_source = tmp_path / "bad.txt"
    _make_pdf(good_source, "Title")
    bad_source.write_text("unsupported", encoding="utf-8")
    config = WorkspaceConfig(publish_root=tmp_path / "published")

    with pytest.raises(WorkspaceBuildError, match="staging preserved"):
        build_workspace(
            [
                FileSource(path=good_source, source_instance_id="source_01"),
                FileSource(path=bad_source, source_instance_id="source_02"),
            ],
            config,
        )

    workspace_dirs = list((config.publish_root).glob("ws_*"))
    assert len(workspace_dirs) == 1
    staging_dirs = _staging_dirs(config.publish_root, workspace_dirs[0].name)
    assert len(staging_dirs) == 1
    assert not (workspace_dirs[0] / "1").exists()


def test_parent_source_id_is_recorded(tmp_path: Path) -> None:
    parent = tmp_path / "parent.pdf"
    child = tmp_path / "child.pdf"
    _make_pdf(parent, "Parent")
    _make_pdf(child, "Child")
    config = WorkspaceConfig(publish_root=tmp_path / "published")

    manifest = build_workspace(
        [FileSource(path=parent, source_instance_id="source_01")],
        config,
    )
    parent_source_id = manifest.sources[0].source_id

    manifest_with_child = build_workspace(
        [
            FileSource(path=parent, source_instance_id="source_01"),
            FileSource(
                path=child,
                source_instance_id="source_02",
                parent_source_id=parent_source_id,
            ),
        ],
        WorkspaceConfig(publish_root=tmp_path / "published_two"),
    )

    child_entry = next(
        s for s in manifest_with_child.sources if s.source_instance_id == "source_02"
    )
    assert child_entry.parent_source_id == parent_source_id


def test_missing_parent_source_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "child.pdf"
    _make_pdf(source, "Child")

    with pytest.raises(WorkspaceBuildError) as caught:
        build_workspace(
            [
                FileSource(
                    path=source,
                    source_instance_id="source_01",
                    parent_source_id="src_missing",
                )
            ],
            WorkspaceConfig(publish_root=tmp_path / "published"),
        )

    assert caught.value.__cause__ is not None
    assert "missing parent: src_missing" in str(caught.value.__cause__)


def test_mixed_source_workspace_dispatches_both_normalizers(tmp_path: Path) -> None:
    pdf_source = tmp_path / "protocol.pdf"
    _make_pdf(pdf_source, "Protocol")
    entry = {
        "id": "etr_1",
        "displayId": "EXP001",
        "name": "Notebook Entry",
        "webURL": "https://x.benchling.com/x/notebook/entries/etr_1",
        "days": [{"date": "2026-01-01", "notes": [{"type": "text", "text": "Ran assay."}]}],
    }
    config = WorkspaceConfig(
        publish_root=tmp_path / "published",
        benchling_api_key="key",
        benchling_url="https://x.benchling.com",
    )

    with (
        patch(
            "canonical_workspace.eln_normalizer.fetch_entry_by_identifier",
            return_value=entry,
        ),
        patch(
            "canonical_workspace.eln_normalizer.fetch_external_file_links_for_entry",
            return_value={},
        ),
        patch(
            "canonical_workspace.eln_normalizer.download_external_files_for_entry",
            return_value={},
        ),
    ):
        manifest = build_workspace(
            [
                FileSource(path=pdf_source, source_instance_id="source_01", source_role="protocol"),
                ElnSource(entry_id="etr_1", source_instance_id="source_02", source_role="notebook"),
            ],
            config,
        )

    source_types = {s.source_instance_id: s.source_type for s in manifest.sources}
    assert source_types == {"source_01": "pdf", "source_02": "eln"}
    published_dir = config.publish_root / manifest.workspace_id / "1"
    for source in manifest.sources:
        assert (published_dir / source.normalized_path).is_file()

    citation_urls = {s.source_instance_id: s.citation_url for s in manifest.sources}
    assert citation_urls == {
        "source_01": None,
        "source_02": "https://x.benchling.com/x/notebook/entries/etr_1",
    }


def test_eln_source_without_credentials_fails_fast(tmp_path: Path) -> None:
    config = WorkspaceConfig(publish_root=tmp_path / "published")

    with pytest.raises(WorkspaceBuildError, match="benchling_api_key"):
        build_workspace(
            [ElnSource(entry_id="etr_1", source_instance_id="source_01")],
            config,
        )


def test_promotes_supported_attachment_and_keeps_unsupported_asset(tmp_path: Path) -> None:
    child = tmp_path / "child.pdf"
    _make_pdf(child, "Child")
    parent = tmp_path / "parent.pdf"
    _make_pdf_with_attachments(
        parent,
        "Parent",
        [("evidence.pdf", child.read_bytes()), ("notes.txt", b"raw notes")],
    )
    config = WorkspaceConfig(publish_root=tmp_path / "published")

    manifest = build_workspace(
        [FileSource(path=parent, source_instance_id="source_01")],
        config,
    )

    assert len(manifest.sources) == 2
    parent_source, child_source = manifest.sources
    assert child_source.parent_source_id == parent_source.source_id
    assert child_source.source_role is None
    assert child_source.source_type == "pdf"
    assert parent_source.original_filename == "parent.pdf"
    assert child_source.original_filename == "evidence.pdf"
    assert len(manifest.assets) == 1
    assert manifest.assets[0].source_id == parent_source.source_id
    assert manifest.assets[0].path.endswith(".txt")
    manifest_json = json.loads(
        (config.publish_root / manifest.workspace_id / "1" / "manifest.json").read_text()
    )
    assert "embedded_files" not in manifest_json

    repeated = build_workspace(
        [FileSource(path=parent, source_instance_id="source_01")],
        WorkspaceConfig(publish_root=tmp_path / "published_again"),
    )
    assert repeated.sources[1].source_instance_id == child_source.source_instance_id


def test_renders_promoted_attachment_citation(tmp_path: Path) -> None:
    child = tmp_path / "child.pdf"
    _make_pdf(child, "Attached Evidence")
    parent = tmp_path / "parent.pdf"
    _make_pdf_with_attachments(parent, "Parent", [("evidence.pdf", child.read_bytes())])
    config = WorkspaceConfig(publish_root=tmp_path / "published")
    manifest = build_workspace(
        [FileSource(path=parent, source_instance_id="source_01")],
        config,
    )
    parent_source, child_source = manifest.sources
    workspace = config.publish_root / manifest.workspace_id / "1"
    sections = json.loads((workspace / child_source.sections_path).read_text(encoding="utf-8"))
    section_id = sections["sections"][0]["section_id"]
    template = tmp_path / "report.md"
    template.write_text("{{finding}}\n\n{{references}}\n", encoding="utf-8")

    result = render(
        template,
        {
            "finding": {
                "status": "found",
                "value": "Attached evidence",
                "citations": [
                    {
                        "source_id": child_source.source_id,
                        "section_id": section_id,
                        "page": 1,
                    }
                ],
            }
        },
        workspace,
    )

    assert (
        f"[evidence.pdf]({child_source.original_path}#page=1), "
        f"attached within {parent_source.original_filename}, page 1"
    ) in result
    assert "<blockquote>" not in result


def test_expands_nested_supported_attachments(tmp_path: Path) -> None:
    grandchild = tmp_path / "grandchild.pdf"
    _make_pdf(grandchild, "Grandchild")
    child = tmp_path / "child.pdf"
    _make_pdf_with_attachments(
        child,
        "Child",
        [("grandchild.pdf", grandchild.read_bytes())],
    )
    parent = tmp_path / "parent.pdf"
    _make_pdf_with_attachments(parent, "Parent", [("child.pdf", child.read_bytes())])
    config = WorkspaceConfig(publish_root=tmp_path / "published")

    manifest = build_workspace(
        [FileSource(path=parent, source_instance_id="source_01")],
        config,
    )

    assert len(manifest.sources) == 3
    parent_source, child_source, grandchild_source = manifest.sources
    assert child_source.parent_source_id == parent_source.source_id
    assert grandchild_source.parent_source_id == child_source.source_id


def test_reuses_normalization_for_repeated_top_level_content(tmp_path: Path) -> None:
    source_a = tmp_path / "a.pdf"
    _make_pdf(source_a, "Repeated")
    source_b = tmp_path / "b.pdf"
    source_b.write_bytes(source_a.read_bytes())
    normalize_document = DocumentNormalizer.normalize_document
    calls = 0

    def track_normalization(normalizer, source):
        nonlocal calls
        calls += 1
        return normalize_document(normalizer, source)

    with patch.object(
        DocumentNormalizer,
        "normalize_document",
        autospec=True,
        side_effect=track_normalization,
    ):
        manifest = build_workspace(
            [
                FileSource(path=source_a, source_instance_id="source_01"),
                FileSource(path=source_b, source_instance_id="source_02"),
            ],
            WorkspaceConfig(publish_root=tmp_path / "published"),
        )

    assert manifest.sources[0].source_id == manifest.sources[1].source_id
    assert calls == 1


def test_reuses_normalization_for_repeated_attachment_content(tmp_path: Path) -> None:
    child = tmp_path / "child.pdf"
    _make_pdf(child, "Child")
    child_bytes = child.read_bytes()
    parent = tmp_path / "parent.pdf"
    _make_pdf_with_attachments(
        parent,
        "Parent",
        [("evidence-a.pdf", child_bytes), ("evidence-b.pdf", child_bytes)],
    )
    config = WorkspaceConfig(publish_root=tmp_path / "published")
    normalize_document = DocumentNormalizer.normalize_document
    calls = 0

    def track_normalization(normalizer, source):
        nonlocal calls
        calls += 1
        return normalize_document(normalizer, source)

    with patch.object(
        DocumentNormalizer,
        "normalize_document",
        autospec=True,
        side_effect=track_normalization,
    ):
        manifest = build_workspace(
            [FileSource(path=parent, source_instance_id="source_01")],
            config,
        )

    child_sources = manifest.sources[1:]
    assert len(child_sources) == 2
    assert child_sources[0].source_id == child_sources[1].source_id
    assert child_sources[0].source_instance_id != child_sources[1].source_instance_id
    assert calls == 2


def test_eln_mixed_attachments_promote_documents_only(tmp_path: Path) -> None:
    attachment_pdf = tmp_path / "attachment.pdf"
    _make_pdf(attachment_pdf, "Attached Evidence")
    entry = {
        "id": "etr_1",
        "displayId": "EXP001",
        "name": "Notebook Entry",
        "days": [
            {
                "date": "2026-01-01",
                "notes": [
                    {
                        "type": "external_file",
                        "externalFileId": "file_pdf",
                        "name": "Evidence",
                    },
                    {
                        "type": "image",
                        "externalFileId": "file_png",
                        "imageId": "file_png",
                        "text": "Microscopy",
                    },
                ],
            }
        ],
    }

    def fake_download(_entry, *, api_key, benchling_url, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / "evidence.pdf"
        pdf_path.write_bytes(attachment_pdf.read_bytes())
        image_path = output_dir / "microscopy.png"
        image_path.write_bytes(b"\x89PNG")
        return {"file_pdf": pdf_path, "file_png": image_path}

    config = WorkspaceConfig(
        publish_root=tmp_path / "published",
        benchling_api_key="key",
        benchling_url="https://x.benchling.com",
    )
    with (
        patch(
            "canonical_workspace.eln_normalizer.fetch_entry_by_identifier",
            return_value=entry,
        ),
        patch(
            "canonical_workspace.eln_normalizer.fetch_external_file_links_for_entry",
            return_value={},
        ),
        patch(
            "canonical_workspace.eln_normalizer.download_external_files_for_entry",
            side_effect=fake_download,
        ),
    ):
        manifest = build_workspace(
            [ElnSource(entry_id="etr_1", source_instance_id="source_01")],
            config,
        )

    assert [source.source_type for source in manifest.sources] == ["eln", "pdf"]
    assert manifest.sources[1].parent_source_id == manifest.sources[0].source_id
    assert manifest.sources[0].original_filename == "Notebook Entry"
    assert manifest.sources[1].original_filename == "evidence.pdf"
    assert len(manifest.assets) == 1
    assert manifest.assets[0].path.endswith("microscopy.png")
