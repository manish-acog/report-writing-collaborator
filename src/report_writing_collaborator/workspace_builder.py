from __future__ import annotations

import dataclasses
import json
import os
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from report_writing_collaborator.document_normalizer import DocumentNormalizer, SourceSpec
from report_writing_collaborator.exceptions import WorkspaceBuildError
from report_writing_collaborator.structure_indexer import StructureIndexer

if TYPE_CHECKING:
    from pathlib import Path

    from _typeshed import DataclassInstance

    from report_writing_collaborator.structure_indexer import DocumentStructure

_MANIFEST_NAME = "manifest.json"
_SECTIONS_NAME = "document.sections.json"
_STAGING_PREFIX = ".staging-"
_PUBLISHED_STATE = "published"
_WORKSPACE_ID_PREFIX = "ws_"


@dataclass(frozen=True, slots=True)
class WorkspaceSource:
    path: Path
    source_instance_id: str
    source_role: str | None = None
    parent_source_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceConfig:
    publish_root: Path
    libreoffice_path: str | Path = "soffice"
    workspace_id: str | None = None
    previous_version: int | None = None


@dataclass(frozen=True, slots=True)
class ManifestSource:
    source_id: str
    source_instance_id: str
    source_role: str | None
    source_type: str
    original_path: str
    normalized_path: str
    sections_path: str
    parent_source_id: str | None


@dataclass(frozen=True, slots=True)
class ManifestAsset:
    source_id: str
    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ManifestEmbeddedFile:
    source_id: str
    path: str
    original_name: str
    sha256: str


@dataclass(frozen=True, slots=True)
class WorkspaceManifest:
    workspace_id: str
    workspace_version: int
    previous_version: int | None
    workspace_state: str
    sources: tuple[ManifestSource, ...]
    assets: tuple[ManifestAsset, ...]
    embedded_files: tuple[ManifestEmbeddedFile, ...]
    derived_artifacts: tuple[dict[str, str], ...]


def build_workspace(
    sources: list[WorkspaceSource],
    config: WorkspaceConfig,
) -> WorkspaceManifest:
    if not sources:
        raise WorkspaceBuildError("At least one source is required")

    _check_unique_instance_ids(sources)
    workspace_id, workspace_version, previous_version = _resolve_lineage(config)

    workspace_dir = config.publish_root / workspace_id
    staging_dir = workspace_dir / f"{_STAGING_PREFIX}{workspace_version}-{uuid.uuid4().hex[:8]}"

    try:
        staging_dir.mkdir(parents=True)
    except OSError as error:
        raise WorkspaceBuildError(f"Cannot create staging directory: {staging_dir}") from error

    try:
        manifest = _build_in_staging(
            sources,
            staging_dir,
            config,
            workspace_id=workspace_id,
            workspace_version=workspace_version,
            previous_version=previous_version,
        )
    except Exception as error:
        # Staging is intentionally left in place (not a plausible published
        # workspace by name or location) so a failed attempt stays inspectable.
        raise WorkspaceBuildError(
            f"Workspace build failed; staging preserved for inspection: {staging_dir}"
        ) from error

    published_dir = workspace_dir / str(workspace_version)
    try:
        os.rename(staging_dir, published_dir)
    except OSError as error:
        raise WorkspaceBuildError(
            f"Cannot publish workspace; staging preserved for inspection: {staging_dir}"
        ) from error

    return manifest


def _build_in_staging(
    sources: list[WorkspaceSource],
    staging_dir: Path,
    config: WorkspaceConfig,
    *,
    workspace_id: str,
    workspace_version: int,
    previous_version: int | None,
) -> WorkspaceManifest:
    normalizer = DocumentNormalizer(staging_dir, libreoffice_path=config.libreoffice_path)
    indexer = StructureIndexer(staging_dir)

    manifest_sources: list[ManifestSource] = []
    manifest_assets: list[ManifestAsset] = []
    manifest_embedded_files: list[ManifestEmbeddedFile] = []

    for source in sources:
        normalized = normalizer.normalize_document(
            SourceSpec(path=source.path, source_instance_id=source.source_instance_id)
        )
        structure = indexer.index_structure(normalized)
        sections_path = _write_sections(staging_dir, normalized.source_id, structure)

        manifest_sources.append(
            ManifestSource(
                source_id=normalized.source_id,
                source_instance_id=normalized.source_instance_id,
                source_role=source.source_role,
                source_type=normalized.source_type,
                original_path=normalized.original_path,
                normalized_path=normalized.normalized_path,
                sections_path=sections_path,
                parent_source_id=source.parent_source_id,
            )
        )
        manifest_assets.extend(
            ManifestAsset(source_id=normalized.source_id, path=asset.path, sha256=asset.sha256)
            for asset in normalized.assets
        )
        manifest_embedded_files.extend(
            ManifestEmbeddedFile(
                source_id=normalized.source_id,
                path=embedded_file.path,
                original_name=embedded_file.original_name,
                sha256=embedded_file.sha256,
            )
            for embedded_file in normalized.embedded_files
        )

    manifest = WorkspaceManifest(
        workspace_id=workspace_id,
        workspace_version=workspace_version,
        previous_version=previous_version,
        workspace_state=_PUBLISHED_STATE,
        sources=tuple(manifest_sources),
        assets=tuple(manifest_assets),
        embedded_files=tuple(manifest_embedded_files),
        derived_artifacts=(),
    )
    _write_manifest(staging_dir, manifest)
    _validate_manifest(staging_dir, manifest)

    return manifest


def _check_unique_instance_ids(sources: list[WorkspaceSource]) -> None:
    seen: set[str] = set()

    for source in sources:
        if source.source_instance_id in seen:
            raise WorkspaceBuildError(f"Duplicate source_instance_id: {source.source_instance_id}")
        seen.add(source.source_instance_id)


def _resolve_lineage(config: WorkspaceConfig) -> tuple[str, int, int | None]:
    if config.previous_version is not None and config.workspace_id is None:
        raise WorkspaceBuildError("previous_version requires workspace_id")

    if config.previous_version is not None:
        _check_previous_version_published(config)

    workspace_id = config.workspace_id or f"{_WORKSPACE_ID_PREFIX}{uuid.uuid4()}"
    workspace_version = (config.previous_version or 0) + 1
    _check_version_not_published(config.publish_root, workspace_id, workspace_version)

    return workspace_id, workspace_version, config.previous_version


def _check_version_not_published(
    publish_root: Path,
    workspace_id: str,
    workspace_version: int,
) -> None:
    version_dir = publish_root / workspace_id / str(workspace_version)
    if version_dir.exists():
        raise WorkspaceBuildError(
            f"Workspace version {workspace_version} already exists for {workspace_id}; "
            "supply previous_version to publish a new version"
        )


def _check_previous_version_published(config: WorkspaceConfig) -> None:
    manifest_path = (
        config.publish_root
        / str(config.workspace_id)
        / str(config.previous_version)
        / _MANIFEST_NAME
    )
    manifest = _read_manifest(manifest_path)

    if manifest.get("workspace_state") != _PUBLISHED_STATE:
        raise WorkspaceBuildError(f"Previous workspace version is not published: {manifest_path}")


def _read_manifest(manifest_path: Path) -> dict[str, object]:
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise WorkspaceBuildError(f"Manifest not found: {manifest_path}") from error
    except json.JSONDecodeError as error:
        raise WorkspaceBuildError(f"Cannot read manifest: {manifest_path}") from error


def _write_sections(staging_dir: Path, source_id: str, structure: DocumentStructure) -> str:
    sections_dir = staging_dir / "normalized" / source_id
    sections_dir.mkdir(parents=True, exist_ok=True)
    sections_path = sections_dir / _SECTIONS_NAME
    _write_json(sections_path, structure, f"Cannot write section index: {sections_path}")

    return f"normalized/{source_id}/{_SECTIONS_NAME}"


def _write_manifest(staging_dir: Path, manifest: WorkspaceManifest) -> None:
    manifest_path = staging_dir / _MANIFEST_NAME
    _write_json(manifest_path, manifest, f"Cannot write manifest: {manifest_path}")


def _write_json(path: Path, data: DataclassInstance, error_message: str) -> None:
    try:
        path.write_text(
            json.dumps(dataclasses.asdict(data), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        raise WorkspaceBuildError(error_message) from error


def _validate_manifest(staging_dir: Path, manifest: WorkspaceManifest) -> None:
    for source in manifest.sources:
        for relative_path in (source.original_path, source.normalized_path, source.sections_path):
            if not (staging_dir / relative_path).is_file():
                raise WorkspaceBuildError(f"Manifest references missing file: {relative_path}")

    for asset in manifest.assets:
        if not (staging_dir / asset.path).is_file():
            raise WorkspaceBuildError(f"Manifest references missing asset: {asset.path}")

    for embedded_file in manifest.embedded_files:
        if not (staging_dir / embedded_file.path).is_file():
            raise WorkspaceBuildError(
                f"Manifest references missing embedded file: {embedded_file.path}"
            )
