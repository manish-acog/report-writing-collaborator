from __future__ import annotations

import glob
import json
from typing import TYPE_CHECKING

import pymupdf
import pytest

from report_writing_collaborator import (
    WorkspaceBuildError,
    WorkspaceConfig,
    WorkspaceSource,
    build_workspace,
)

if TYPE_CHECKING:
    from pathlib import Path


def _make_pdf(path: Path, title: str) -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(72, 150, 500, 200), title, fontsize=18)
    page.insert_textbox(pymupdf.Rect(72, 220, 500, 600), "Body text.", fontsize=12)
    document.save(path)
    document.close()


def _staging_dirs(publish_root: Path, workspace_id: str) -> list[str]:
    return glob.glob(str(publish_root / workspace_id / ".staging-*"))


def test_build_workspace_single_source(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    _make_pdf(source, "Report Title")
    config = WorkspaceConfig(publish_root=tmp_path / "published")

    manifest = build_workspace(
        [WorkspaceSource(path=source, source_instance_id="source_01", source_role="protocol")],
        config,
    )

    assert manifest.workspace_id.startswith("ws_")
    assert manifest.workspace_version == 1
    assert manifest.previous_version is None
    assert manifest.workspace_state == "published"
    assert len(manifest.sources) == 1
    assert manifest.sources[0].source_role == "protocol"
    assert manifest.sources[0].parent_source_id is None

    published_dir = config.publish_root / manifest.workspace_id / "1"
    assert (published_dir / "manifest.json").is_file()
    assert (published_dir / manifest.sources[0].sections_path).is_file()
    assert (published_dir / manifest.sources[0].normalized_path).is_file()
    assert not _staging_dirs(config.publish_root, manifest.workspace_id)

    on_disk = json.loads((published_dir / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["workspace_id"] == manifest.workspace_id
    assert on_disk["sources"][0]["source_id"] == manifest.sources[0].source_id


def test_build_workspace_multiple_sources_have_distinct_section_ids(tmp_path: Path) -> None:
    source_a = tmp_path / "a.pdf"
    source_b = tmp_path / "b.pdf"
    _make_pdf(source_a, "Shared Title")
    _make_pdf(source_b, "Shared Title")
    config = WorkspaceConfig(publish_root=tmp_path / "published")

    manifest = build_workspace(
        [
            WorkspaceSource(path=source_a, source_instance_id="source_01"),
            WorkspaceSource(path=source_b, source_instance_id="source_02"),
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
                WorkspaceSource(path=source, source_instance_id="source_01"),
                WorkspaceSource(path=source, source_instance_id="source_01"),
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
        [WorkspaceSource(path=source_v1, source_instance_id="source_01")], config
    )
    manifest_v2 = build_workspace(
        [WorkspaceSource(path=source_v2, source_instance_id="source_01")],
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
        build_workspace([WorkspaceSource(path=source, source_instance_id="source_01")], config)


def test_previous_version_requires_workspace_id(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    _make_pdf(source, "Title")
    config = WorkspaceConfig(publish_root=tmp_path / "published", previous_version=1)

    with pytest.raises(WorkspaceBuildError, match="requires workspace_id"):
        build_workspace([WorkspaceSource(path=source, source_instance_id="source_01")], config)


def test_reusing_workspace_id_without_previous_version_fails_fast(tmp_path: Path) -> None:
    source = tmp_path / "sample.pdf"
    _make_pdf(source, "Title")
    config = WorkspaceConfig(publish_root=tmp_path / "published")
    manifest = build_workspace(
        [WorkspaceSource(path=source, source_instance_id="source_01")], config
    )

    with pytest.raises(WorkspaceBuildError, match="already exists"):
        build_workspace(
            [WorkspaceSource(path=source, source_instance_id="source_01")],
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
                WorkspaceSource(path=good_source, source_instance_id="source_01"),
                WorkspaceSource(path=bad_source, source_instance_id="source_02"),
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
        [WorkspaceSource(path=parent, source_instance_id="source_01")],
        config,
    )
    parent_source_id = manifest.sources[0].source_id

    manifest_with_child = build_workspace(
        [
            WorkspaceSource(path=parent, source_instance_id="source_01"),
            WorkspaceSource(
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
