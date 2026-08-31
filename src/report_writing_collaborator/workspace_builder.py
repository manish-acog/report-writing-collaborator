from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import uuid
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from report_writing_collaborator.document_normalizer import (
    DocumentNormalizer,
    SourceSpec,
    make_source_id,
    supports_document,
)
from report_writing_collaborator.eln_normalizer import ElnNormalizer, ElnSource
from report_writing_collaborator.exceptions import WorkspaceBuildError
from report_writing_collaborator.structure_indexer import StructureIndexer

if TYPE_CHECKING:
    from pathlib import Path

    from _typeshed import DataclassInstance

    from report_writing_collaborator.document_normalizer import NormalizedDocument
    from report_writing_collaborator.structure_indexer import DocumentStructure

_MANIFEST_NAME = "manifest.json"
_SECTIONS_NAME = "document.sections.json"
_STAGING_PREFIX = ".staging-"
_PUBLISHED_STATE = "published"
_WORKSPACE_ID_PREFIX = "ws_"
_ATTACHMENT_INSTANCE_PREFIX = "attachment_"
_ATTACHMENT_INSTANCE_LENGTH = 12
_HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class FileSource:
    path: Path
    source_instance_id: str
    source_role: str | None = None
    parent_source_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceConfig:
    publish_root: Path
    libreoffice_path: str | Path = "soffice"
    benchling_api_key: str | None = None
    benchling_url: str | None = None
    workspace_id: str | None = None
    previous_version: int | None = None


@dataclass(frozen=True, slots=True)
class ManifestSource:
    source_id: str
    source_instance_id: str
    source_role: str | None
    original_filename: str
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
class WorkspaceManifest:
    workspace_id: str
    workspace_version: int
    previous_version: int | None
    workspace_state: str
    sources: tuple[ManifestSource, ...]
    assets: tuple[ManifestAsset, ...]
    derived_artifacts: tuple[dict[str, str], ...]


@dataclass(frozen=True, slots=True)
class _PendingSource:
    source: FileSource | ElnSource
    original_filename: str | None = None
    known_source_id: str | None = None
    ancestor_source_ids: frozenset[str] = frozenset()


def build_workspace(
    sources: list[FileSource | ElnSource],
    config: WorkspaceConfig,
) -> WorkspaceManifest:
    if not sources:
        raise WorkspaceBuildError("At least one source is required")

    _check_unique_instance_ids(sources)
    _check_eln_credentials(sources, config)
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
    sources: list[FileSource | ElnSource],
    staging_dir: Path,
    config: WorkspaceConfig,
    *,
    workspace_id: str,
    workspace_version: int,
    previous_version: int | None,
) -> WorkspaceManifest:
    normalizer = DocumentNormalizer(staging_dir, libreoffice_path=config.libreoffice_path)
    eln_normalizer = ElnNormalizer(
        staging_dir,
        api_key=config.benchling_api_key or "",
        benchling_url=config.benchling_url or "",
    )
    indexer = StructureIndexer(staging_dir)

    repeated_file_ids = _repeated_file_ids(sources)
    pending = deque(
        _PendingSource(
            source,
            original_filename=source.path.name if isinstance(source, FileSource) else None,
            known_source_id=repeated_file_ids.get(source.source_instance_id),
        )
        for source in sources
    )
    normalized_by_id: dict[str, NormalizedDocument] = {}
    eln_source_ids: dict[str, str] = {}
    sections_by_id: dict[str, str] = {}
    source_instance_ids = {source.source_instance_id for source in sources}
    manifest_sources: list[ManifestSource] = []
    manifest_assets: list[ManifestAsset] = []
    asset_keys: set[tuple[str, str]] = set()

    while pending:
        item = pending.popleft()
        source = item.source
        known_source_id = item.known_source_id
        if known_source_id is None and isinstance(source, ElnSource):
            known_source_id = eln_source_ids.get(source.entry_id)
        normalized = normalized_by_id.get(known_source_id) if known_source_id else None

        if normalized is None:
            if isinstance(source, FileSource):
                normalized = normalizer.normalize_document(
                    SourceSpec(path=source.path, source_instance_id=source.source_instance_id)
                )
            else:
                normalized = eln_normalizer.normalize_entry(source)
                eln_source_ids[source.entry_id] = normalized.source_id

            existing = normalized_by_id.get(normalized.source_id)
            if existing is None:
                normalized_by_id[normalized.source_id] = normalized
                structure = indexer.index_structure(normalized)
                sections_by_id[normalized.source_id] = _write_sections(
                    staging_dir,
                    normalized.source_id,
                    structure,
                )
            else:
                normalized = existing

        normalized = dataclasses.replace(
            normalized,
            source_instance_id=source.source_instance_id,
        )
        manifest_sources.append(
            ManifestSource(
                source_id=normalized.source_id,
                source_instance_id=normalized.source_instance_id,
                source_role=source.source_role,
                original_filename=_original_filename(item, normalized),
                source_type=normalized.source_type,
                original_path=normalized.original_path,
                normalized_path=normalized.normalized_path,
                sections_path=sections_by_id[normalized.source_id],
                parent_source_id=source.parent_source_id,
            )
        )

        for asset in normalized.assets:
            _add_asset(
                manifest_assets,
                asset_keys,
                source_id=normalized.source_id,
                path=asset.path,
                sha256=asset.sha256,
            )

        # Record the repeated occurrence, but stop a recursive content cycle.
        if normalized.source_id in item.ancestor_source_ids:
            continue

        child_ancestors = item.ancestor_source_ids | {normalized.source_id}
        for attachment in sorted(normalized.embedded_files, key=lambda value: value.path):
            if not supports_document(attachment.original_name):
                _add_asset(
                    manifest_assets,
                    asset_keys,
                    source_id=normalized.source_id,
                    path=attachment.path,
                    sha256=attachment.sha256,
                )
                continue

            source_instance_id = _attachment_instance_id(
                source.source_instance_id,
                attachment.path,
            )
            if source_instance_id in source_instance_ids:
                raise WorkspaceBuildError(
                    f"Duplicate derived source_instance_id: {source_instance_id}"
                )
            source_instance_ids.add(source_instance_id)
            pending.append(
                _PendingSource(
                    source=FileSource(
                        path=staging_dir / attachment.path,
                        source_instance_id=source_instance_id,
                        parent_source_id=normalized.source_id,
                    ),
                    original_filename=attachment.original_name,
                    known_source_id=make_source_id(attachment.sha256),
                    ancestor_source_ids=child_ancestors,
                )
            )

    manifest = WorkspaceManifest(
        workspace_id=workspace_id,
        workspace_version=workspace_version,
        previous_version=previous_version,
        workspace_state=_PUBLISHED_STATE,
        sources=tuple(manifest_sources),
        assets=tuple(manifest_assets),
        derived_artifacts=(),
    )
    _write_manifest(staging_dir, manifest)
    _validate_manifest(staging_dir, manifest)

    return manifest


def _original_filename(item: _PendingSource, normalized: NormalizedDocument) -> str:
    if item.original_filename:
        return item.original_filename

    source = item.source
    if isinstance(source, ElnSource):
        name = normalized.metadata.get("name")
        return str(name).strip() if name else source.entry_id

    return source.path.name


def _attachment_instance_id(parent_instance_id: str, attachment_path: str) -> str:
    identity = f"{parent_instance_id}\0{attachment_path}".encode()
    digest = hashlib.sha256(identity).hexdigest()
    return f"{_ATTACHMENT_INSTANCE_PREFIX}{digest[:_ATTACHMENT_INSTANCE_LENGTH]}"


def _add_asset(
    assets: list[ManifestAsset],
    keys: set[tuple[str, str]],
    *,
    source_id: str,
    path: str,
    sha256: str,
) -> None:
    key = (source_id, path)
    if key in keys:
        return

    keys.add(key)
    assets.append(ManifestAsset(source_id=source_id, path=path, sha256=sha256))


def _repeated_file_ids(sources: list[FileSource | ElnSource]) -> dict[str, str]:
    sources_by_size: dict[int, list[FileSource]] = {}
    for source in sources:
        if not isinstance(source, FileSource) or not source.path.is_file():
            continue

        size = source.path.stat().st_size
        sources_by_size.setdefault(size, []).append(source)

    return {
        source.source_instance_id: make_source_id(_file_sha256(source.path))
        for same_size_sources in sources_by_size.values()
        if len(same_size_sources) > 1
        for source in same_size_sources
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _check_unique_instance_ids(sources: list[FileSource | ElnSource]) -> None:
    seen: set[str] = set()

    for source in sources:
        if source.source_instance_id in seen:
            raise WorkspaceBuildError(f"Duplicate source_instance_id: {source.source_instance_id}")
        seen.add(source.source_instance_id)


def _check_eln_credentials(sources: list[FileSource | ElnSource], config: WorkspaceConfig) -> None:
    has_eln_source = any(isinstance(source, ElnSource) for source in sources)
    if has_eln_source and not (config.benchling_api_key and config.benchling_url):
        raise WorkspaceBuildError(
            "benchling_api_key and benchling_url are required when an ElnSource is included"
        )


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
    source_ids = {source.source_id for source in manifest.sources}
    source_instance_ids = [source.source_instance_id for source in manifest.sources]
    if len(source_instance_ids) != len(set(source_instance_ids)):
        raise WorkspaceBuildError("Manifest contains duplicate source_instance_id values")

    for source in manifest.sources:
        if source.parent_source_id is not None and source.parent_source_id not in source_ids:
            raise WorkspaceBuildError(
                f"Manifest source references missing parent: {source.parent_source_id}"
            )

    for source in manifest.sources:
        for relative_path in (source.original_path, source.normalized_path, source.sections_path):
            if not (staging_dir / relative_path).is_file():
                raise WorkspaceBuildError(f"Manifest references missing file: {relative_path}")

    for asset in manifest.assets:
        if asset.source_id not in source_ids:
            raise WorkspaceBuildError(
                f"Manifest asset references missing source: {asset.source_id}"
            )
        if not (staging_dir / asset.path).is_file():
            raise WorkspaceBuildError(f"Manifest references missing asset: {asset.path}")
