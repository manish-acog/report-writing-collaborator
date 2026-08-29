from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

import pymupdf
import pymupdf4llm

from report_writing_collaborator.exceptions import (
    DocumentConversionError,
    DocumentNormalizationError,
    DocumentParseError,
    UnsupportedDocumentTypeError,
)

_SOURCE_PREFIX = "src_"
_SOURCE_ID_LENGTH = 12
_HASH_CHUNK_SIZE = 1024 * 1024
_VERSION_PROBE_TIMEOUT_SECONDS = 30
_CONVERSION_TIMEOUT_SECONDS = 120
_LIBREOFFICE_VERSION = "26.8.0"
_NORMALIZER_NAME = "pymupdf4llm"
_MARKDOWN_NAME = "document.md"
_HEADER_FOOTER_CLASSES = frozenset({"page-header", "page-footer"})
_PDF_TYPES = frozenset({"pdf"})
_OFFICE_TYPES = frozenset({"doc", "docx", "ppt", "pptx"})
_SUPPORTED_TYPES = _PDF_TYPES | _OFFICE_TYPES

MetadataValue = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class SourceSpec:
    path: Path
    source_instance_id: str


@dataclass(frozen=True, slots=True)
class Asset:
    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class EmbeddedFile:
    path: str
    original_name: str
    description: str | None
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class DocumentLink:
    page_number: int
    kind: str
    target: str | None
    target_page: int | None


@dataclass(frozen=True, slots=True)
class PageMapping:
    page_number: int
    start_line: int | None
    end_line: int | None


@dataclass(frozen=True, slots=True)
class PageHeaderFooter:
    page_number: int
    header: str | None
    footer: str | None


@dataclass(frozen=True, slots=True)
class FileHashes:
    source_sha256: str
    normalized_sha256: str


@dataclass(frozen=True, slots=True)
class Tooling:
    normalizer: str
    normalizer_version: str
    converter: str | None
    converter_version: str | None


@dataclass(frozen=True, slots=True)
class NormalizedDocument:
    source_id: str
    source_instance_id: str
    source_type: str
    original_path: str
    normalized_path: str
    assets: tuple[Asset, ...]
    embedded_files: tuple[EmbeddedFile, ...]
    links: tuple[DocumentLink, ...]
    page_map: tuple[PageMapping, ...]
    header_footer: tuple[PageHeaderFooter, ...]
    metadata: Mapping[str, MetadataValue]
    hashes: FileHashes
    tooling: Tooling
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _PdfInspection:
    metadata: Mapping[str, MetadataValue]
    embedded_files: tuple[EmbeddedFile, ...]
    links: tuple[DocumentLink, ...]
    warnings: tuple[str, ...]


class DocumentNormalizer:
    def __init__(
        self,
        staging_root: Path,
        libreoffice_path: str | Path = "soffice",
    ) -> None:
        self._root = staging_root.resolve()
        self._libreoffice_path = str(libreoffice_path)
        self._converter_version: str | None = None

        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise DocumentNormalizationError(f"Cannot create staging root: {self._root}") from error

    def normalize_document(self, source: SourceSpec) -> NormalizedDocument:
        if not source.source_instance_id.strip():
            raise DocumentNormalizationError("Source instance ID is required")

        source_path = self._source_path(source.path)
        source_type = source_path.suffix.lower().removeprefix(".")
        self._check_type(source_type)

        source_hash = _sha256(source_path)
        source_id = f"{_SOURCE_PREFIX}{source_hash[:_SOURCE_ID_LENGTH]}"
        original_path = self._copy_source(source_path, source_id, source_hash)
        pdf_path, converter_version = self._pdf_path(original_path, source_type, source_id)

        inspection = self._inspect_pdf(pdf_path, source_id)
        markdown, page_map, header_footer, normalization_warnings = self._normalize_pdf(
            pdf_path, source_id
        )
        normalized_path = self._write_markdown(markdown, source_id)
        assets = self._collect_assets(source_id)

        result = NormalizedDocument(
            source_id=source_id,
            source_instance_id=source.source_instance_id,
            source_type=source_type,
            original_path=self._relative(original_path),
            normalized_path=self._relative(normalized_path),
            assets=assets,
            embedded_files=inspection.embedded_files,
            links=inspection.links,
            page_map=page_map,
            header_footer=header_footer,
            metadata=inspection.metadata,
            hashes=FileHashes(
                source_sha256=source_hash,
                normalized_sha256=_sha256(normalized_path),
            ),
            tooling=Tooling(
                normalizer=_NORMALIZER_NAME,
                normalizer_version=version(_NORMALIZER_NAME),
                converter="libreoffice" if converter_version else None,
                converter_version=converter_version,
            ),
            warnings=inspection.warnings + normalization_warnings,
        )
        self._validate(result)

        return result

    def _source_path(self, path: Path) -> Path:
        try:
            resolved = path.expanduser().resolve(strict=True)
        except OSError as error:
            raise DocumentNormalizationError(f"Source file does not exist: {path}") from error

        if not resolved.is_file():
            raise DocumentNormalizationError(f"Source is not a file: {path}")

        return resolved

    def _check_type(self, source_type: str) -> None:
        if source_type not in _SUPPORTED_TYPES:
            supported = ", ".join(sorted(_SUPPORTED_TYPES))
            raise UnsupportedDocumentTypeError(
                f"Unsupported document type '{source_type or '<none>'}'; expected: {supported}"
            )

    def _copy_source(self, source_path: Path, source_id: str, source_hash: str) -> Path:
        source_dir = self._root / "sources" / source_id
        source_dir.mkdir(parents=True, exist_ok=True)
        original_path = source_dir / f"original{source_path.suffix.lower()}"
        other_originals = tuple(
            path for path in source_dir.glob("original.*") if path != original_path
        )
        if other_originals:
            raise DocumentNormalizationError(f"Source ID collision at: {source_dir}")

        if original_path.exists():
            if _sha256(original_path) != source_hash:
                raise DocumentNormalizationError(f"Source ID collision at: {original_path}")

            return original_path

        try:
            shutil.copyfile(source_path, original_path)
        except OSError as error:
            raise DocumentNormalizationError(f"Cannot preserve source: {source_path}") from error

        return original_path

    def _pdf_path(
        self,
        original_path: Path,
        source_type: str,
        source_id: str,
    ) -> tuple[Path, str | None]:
        if source_type in _PDF_TYPES:
            return original_path, None

        converter_version = self._get_converter_version()
        conversion_dir = self._root / "debug" / "conversion_logs" / source_id
        conversion_dir.mkdir(parents=True, exist_ok=True)
        converted_path = conversion_dir / "converted.pdf"

        # Isolated profiles avoid user state and concurrent LibreOffice locks.
        with tempfile.TemporaryDirectory(dir=conversion_dir) as temporary_dir:
            temporary_path = Path(temporary_dir)
            profile_path = temporary_path / "profile"
            command = [
                self._libreoffice_path,
                f"-env:UserInstallation={profile_path.resolve().as_uri()}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(temporary_path),
                str(original_path),
            ]
            self._run_conversion(command)

            outputs = tuple(temporary_path.glob("*.pdf"))
            if len(outputs) != 1:
                raise DocumentConversionError(
                    f"LibreOffice produced {len(outputs)} PDF files for: {original_path}"
                )

            try:
                os.replace(outputs[0], converted_path)
            except OSError as error:
                raise DocumentConversionError(
                    f"Cannot preserve converted PDF: {converted_path}"
                ) from error

        return converted_path, converter_version

    def _get_converter_version(self) -> str:
        if self._converter_version:
            return self._converter_version

        try:
            completed = subprocess.run(
                [self._libreoffice_path, "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=_VERSION_PROBE_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise DocumentConversionError(
                f"Cannot run LibreOffice: {self._libreoffice_path}"
            ) from error

        match = re.search(r"\b(\d+\.\d+\.\d+)\b", completed.stdout)
        actual_version = match.group(1) if match else None
        if actual_version != _LIBREOFFICE_VERSION:
            raise DocumentConversionError(
                f"LibreOffice {_LIBREOFFICE_VERSION} required; found: "
                f"{actual_version or completed.stdout.strip() or '<unknown>'}"
            )

        self._converter_version = actual_version

        return actual_version

    def _run_conversion(self, command: list[str]) -> None:
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=_CONVERSION_TIMEOUT_SECONDS,
            )
        except subprocess.CalledProcessError as error:
            detail = error.stderr.strip() or error.stdout.strip() or "unknown error"
            raise DocumentConversionError(f"LibreOffice conversion failed: {detail}") from error
        except subprocess.TimeoutExpired as error:
            raise DocumentConversionError("LibreOffice conversion timed out") from error
        except OSError as error:
            raise DocumentConversionError(
                f"Cannot run LibreOffice: {self._libreoffice_path}"
            ) from error

    def _inspect_pdf(self, pdf_path: Path, source_id: str) -> _PdfInspection:
        embedded_dir = self._root / "embedded" / source_id
        _reset_dir(embedded_dir)

        try:
            with pymupdf.open(pdf_path) as document:
                metadata: dict[str, MetadataValue] = dict(sorted(document.metadata.items()))
                metadata["page_count"] = document.page_count
                embedded_files = self._extract_embedded(document, embedded_dir)
                links, warnings = self._extract_links(document)
        except DocumentNormalizationError:
            raise
        except Exception as error:
            raise DocumentParseError(f"Cannot inspect PDF: {pdf_path}") from error

        return _PdfInspection(
            metadata=MappingProxyType(metadata),
            embedded_files=embedded_files,
            links=links,
            warnings=warnings,
        )

    def _extract_embedded(
        self,
        document: pymupdf.Document,
        embedded_dir: Path,
    ) -> tuple[EmbeddedFile, ...]:
        records: list[EmbeddedFile] = []

        for index, name in enumerate(sorted(document.embfile_names()), start=1):
            info = document.embfile_info(name)
            original_name = str(info.get("filename") or name)
            suffix = Path(original_name).suffix.lower()
            artifact_path = embedded_dir / f"attachment_{index:03d}{suffix}"
            content = document.embfile_get(name)
            artifact_path.write_bytes(content)
            description = info.get("desc")
            records.append(
                EmbeddedFile(
                    path=self._relative(artifact_path),
                    original_name=original_name,
                    description=str(description) if description else None,
                    size=len(content),
                    sha256=_sha256(artifact_path),
                )
            )

        return tuple(records)

    def _extract_links(
        self,
        document: pymupdf.Document,
    ) -> tuple[tuple[DocumentLink, ...], tuple[str, ...]]:
        links: list[DocumentLink] = []
        warnings: list[str] = []

        for page_index in range(document.page_count):
            page_number = page_index + 1
            page = document.load_page(page_index)
            for link in page.get_links():
                record = _link_record(page_number, link)
                if record is None:
                    warnings.append(
                        f"Ignored unsupported link kind {link.get('kind')} on page {page_number}"
                    )
                    continue

                links.append(record)

        return tuple(links), tuple(warnings)

    def _normalize_pdf(
        self,
        pdf_path: Path,
        source_id: str,
    ) -> tuple[str, tuple[PageMapping, ...], tuple[PageHeaderFooter, ...], tuple[str, ...]]:
        assets_dir = self._assets_dir(source_id)
        _reset_dir(assets_dir)

        # PyMuPDF4LLM mangles spaces in image paths; extract through a safe temporary path.
        try:
            with tempfile.TemporaryDirectory(prefix="document_images_") as temporary_dir:
                temporary_path = Path(temporary_dir)
                chunks = self._parse_pdf(pdf_path, temporary_path)
                page_bodies, header_footer, warnings = _extract_pages(chunks)
                markdown, page_map = _join_pages(page_bodies)

                for image_path in temporary_path.iterdir():
                    if image_path.is_file():
                        shutil.move(image_path, assets_dir / image_path.name)
        except Exception as error:
            raise DocumentParseError(f"Cannot normalize PDF: {pdf_path}") from error

        normalized_dir = self._normalized_dir(source_id)
        asset_reference = _relative_to_dir(assets_dir, normalized_dir)
        markdown = _rewrite_asset_paths(markdown, temporary_path, asset_reference)

        return markdown, page_map, header_footer, warnings

    def _parse_pdf(self, pdf_path: Path, image_path: Path) -> list[Mapping[str, object]]:
        # header=True/footer=True keeps header/footer text addressable via
        # page_boxes so it can be captured, instead of discarding it outright;
        # _extract_pages strips it back out of the body afterward.
        raw_chunks = pymupdf4llm.to_markdown(
            str(pdf_path),
            write_images=True,
            embed_images=False,
            force_text=True,
            use_ocr=True,
            force_ocr=False,
            ocr_dpi=300,
            header=True,
            footer=True,
            page_chunks=True,
            filename="document",
            image_path=str(image_path),
            show_progress=False,
        )
        if not isinstance(raw_chunks, list):
            raise DocumentParseError("PyMuPDF4LLM did not return page chunks")

        # Third-party chunk dictionaries are untyped; fields are validated when consumed.
        return cast("list[Mapping[str, object]]", raw_chunks)

    def _write_markdown(self, markdown: str, source_id: str) -> Path:
        normalized_dir = self._normalized_dir(source_id)
        normalized_dir.mkdir(parents=True, exist_ok=True)
        normalized_path = normalized_dir / _MARKDOWN_NAME

        try:
            normalized_path.write_text(markdown, encoding="utf-8", newline="\n")
        except OSError as error:
            raise DocumentNormalizationError(
                f"Cannot write normalized Markdown: {normalized_path}"
            ) from error

        return normalized_path

    def _collect_assets(self, source_id: str) -> tuple[Asset, ...]:
        assets_dir = self._assets_dir(source_id)

        return tuple(
            Asset(path=self._relative(path), sha256=_sha256(path))
            for path in sorted(assets_dir.iterdir())
            if path.is_file()
        )

    def _validate(self, document: NormalizedDocument) -> None:
        source_path = self._workspace_path(document.original_path)
        normalized_path = self._workspace_path(document.normalized_path)
        if not source_path.is_file() or _sha256(source_path) != document.hashes.source_sha256:
            raise DocumentNormalizationError("Preserved source failed validation")
        if (
            not normalized_path.is_file()
            or _sha256(normalized_path) != document.hashes.normalized_sha256
        ):
            raise DocumentNormalizationError("Normalized Markdown failed validation")

        for artifact in (*document.assets, *document.embedded_files):
            artifact_path = self._workspace_path(artifact.path)
            if not artifact_path.is_file() or _sha256(artifact_path) != artifact.sha256:
                raise DocumentNormalizationError(f"Artifact failed validation: {artifact.path}")

        if not document.tooling.normalizer_version:
            raise DocumentNormalizationError("Normalizer version is missing")
        if document.tooling.converter and not document.tooling.converter_version:
            raise DocumentNormalizationError("Converter version is missing")

    def _workspace_path(self, relative_path: str) -> Path:
        path = (self._root / relative_path).resolve()

        try:
            path.relative_to(self._root)
        except ValueError as error:
            raise DocumentNormalizationError(
                f"Output path escapes staging root: {relative_path}"
            ) from error

        return path

    def _relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self._root).as_posix()
        except ValueError as error:
            raise DocumentNormalizationError(f"Output path escapes staging root: {path}") from error

    def _assets_dir(self, source_id: str) -> Path:
        return self._root / "assets" / source_id / "images"

    def _normalized_dir(self, source_id: str) -> Path:
        return self._root / "normalized" / source_id


def _extract_pages(
    chunks: list[Mapping[str, object]],
) -> tuple[list[str], tuple[PageHeaderFooter, ...], tuple[str, ...]]:
    bodies: list[str] = []
    header_footer: list[PageHeaderFooter] = []
    warnings: list[str] = []

    for page_number, chunk in enumerate(chunks, start=1):
        text = chunk.get("text")
        if not isinstance(text, str):
            raise DocumentParseError(f"Page {page_number} has no Markdown text")

        boxes = chunk.get("page_boxes")
        boxes = boxes if isinstance(boxes, list) else []

        header = _box_text(text, boxes, "page-header")
        footer = _box_text(text, boxes, "page-footer")
        body = _strip_boxes(text, boxes, _HEADER_FOOTER_CLASSES)

        if not body.strip() and text.strip():
            # Layout misclassified the page's only content as header/footer;
            # keep it in the body rather than silently discarding the page.
            body = text
            warnings.append(
                f"Page {page_number} classified entirely as header/footer; "
                "original text kept in body"
            )

        bodies.append(body)
        if header or footer:
            header_footer.append(PageHeaderFooter(page_number, header, footer))

    return bodies, tuple(header_footer), tuple(warnings)


def _box_text(text: str, boxes: list[object], box_class: str) -> str | None:
    pieces = [
        text[start:stop].strip() for start, stop in _box_ranges(boxes, frozenset({box_class}))
    ]
    pieces = [piece for piece in pieces if piece]

    return " ".join(pieces) if pieces else None


def _strip_boxes(text: str, boxes: list[object], classes: frozenset[str]) -> str:
    for start, stop in sorted(_box_ranges(boxes, classes), reverse=True):
        text = text[:start] + text[stop:]

    return text


def _box_ranges(boxes: list[object], classes: frozenset[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []

    for box in boxes:
        if not isinstance(box, dict) or box.get("class") not in classes:
            continue

        pos = box.get("pos")
        if not (isinstance(pos, (tuple, list)) and len(pos) == 2):
            continue

        start, stop = pos
        if isinstance(start, int) and isinstance(stop, int) and stop > start:
            ranges.append((start, stop))

    return ranges


def _join_pages(page_bodies: list[str]) -> tuple[str, tuple[PageMapping, ...]]:
    lines: list[str] = []
    page_map: list[PageMapping] = []

    for page_number, body in enumerate(page_bodies, start=1):
        page_lines = body.rstrip("\n").splitlines() if body else []
        if page_lines:
            start_line = len(lines) + 1
            lines.extend(page_lines)
            end_line = len(lines)
        else:
            start_line = None
            end_line = None

        page_map.append(
            PageMapping(
                page_number=page_number,
                start_line=start_line,
                end_line=end_line,
            )
        )
        if page_number < len(page_bodies) and lines and lines[-1] != "":
            lines.append("")

    markdown = "\n".join(lines).rstrip()
    if markdown:
        markdown += "\n"

    return markdown, tuple(page_map)


def _rewrite_asset_paths(markdown: str, temporary_path: Path, replacement: str) -> str:
    references = {temporary_path.resolve().as_posix()}

    with suppress(ValueError):
        references.add(temporary_path.resolve().relative_to(Path.cwd().resolve()).as_posix())

    for reference in sorted(references, key=len, reverse=True):
        markdown = markdown.replace(reference, replacement)

    return markdown


def _relative_to_dir(target: Path, base_dir: Path) -> str:
    # CommonMark resolves relative links against the containing file's
    # directory, not the workspace root; the manifest's Asset.path uses the
    # latter, so the two must be computed separately.
    return Path(os.path.relpath(target, base_dir)).as_posix()


def _link_record(page_number: int, link: Mapping[str, object]) -> DocumentLink | None:
    kind = link.get("kind")

    if kind == pymupdf.LINK_GOTO:
        target_page = _page_number(link.get("page"))
        return DocumentLink(page_number, "internal", None, target_page)
    if kind == pymupdf.LINK_NAMED:
        return DocumentLink(page_number, "internal", _string(link.get("nameddest")), None)
    if kind == pymupdf.LINK_URI:
        return DocumentLink(page_number, "external", _string(link.get("uri")), None)
    if kind in {pymupdf.LINK_GOTOR, pymupdf.LINK_LAUNCH}:
        return DocumentLink(
            page_number,
            "remote_file",
            _string(link.get("file")),
            _page_number(link.get("page")),
        )

    return None


def _page_number(value: object) -> int | None:
    return value + 1 if isinstance(value, int) and value >= 0 else None


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)

    path.mkdir(parents=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    try:
        with path.open("rb") as file:
            while chunk := file.read(_HASH_CHUNK_SIZE):
                digest.update(chunk)
    except OSError as error:
        raise DocumentNormalizationError(f"Cannot hash file: {path}") from error

    return digest.hexdigest()
