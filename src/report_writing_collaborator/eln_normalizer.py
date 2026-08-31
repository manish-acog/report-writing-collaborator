from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse
from urllib.request import urlopen

from benchling_sdk.auth.api_key_auth import ApiKeyAuth
from benchling_sdk.benchling import Benchling

from report_writing_collaborator.document_normalizer import (
    EmbeddedFile,
    FileHashes,
    MetadataValue,
    NormalizedDocument,
    Tooling,
    make_source_id,
)
from report_writing_collaborator.exceptions import (
    ElnAuthenticationError,
    ElnFetchError,
    ElnNormalizationError,
    ElnParseError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

_SOURCE_PREFIX = "src_"
_SOURCE_ID_LENGTH = 12
_SOURCE_TYPE = "eln"
_PACKAGE_NAME = "report-writing-collaborator"
_NORMALIZER_NAME = "report_writing_collaborator.eln_normalizer"
_HASH_CHUNK_SIZE = 1024 * 1024
_DOWNLOAD_TIMEOUT_SECONDS = 60
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff")


@dataclass(frozen=True, slots=True)
class ElnSource:
    entry_id: str
    source_instance_id: str
    source_role: str | None = None
    parent_source_id: str | None = None


def _note_title(note: Mapping[str, object]) -> str:
    text_value = str(note.get("text", "")).strip()
    if text_value:
        return text_value

    return str(note.get("name", "")).strip()


class BenchlingFormatter:
    """Formatter that dispatches by note type and degrades gracefully."""

    def __init__(
        self,
        *,
        asset_paths: dict[str, str] | None = None,
        external_file_links: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self.asset_paths = asset_paths or {}
        self.external_file_links = external_file_links or {}
        self.handlers = {
            "text": self._format_text,
            "table": self._format_table,
            "list_bullet": self._format_list_bullet,
            "list_checkbox": self._format_list_checkbox,
            "list_number": self._format_list_number,
            "external_file": self._format_external_file,
            "text_box": self._format_text_box,
            "image": self._format_image,
            "lookup_table": self._format_lookup_table,
            "registration_table": self._format_named_table,
            "results_table": self._format_named_table,
            "dropdown": self._format_dropdown,
            "entity_link": self._format_entity_link,
        }

    def format_entry(self, entry: Mapping[str, object]) -> str:
        lines: list[str] = []
        lines.extend(self._print_header(entry))
        lines.extend(self._print_metadata(entry))

        days = entry.get("days")
        for day in days if isinstance(days, list) else []:
            if not isinstance(day, dict):
                continue

            date_value = str(day.get("date", "")).strip()
            if date_value:
                lines.append(f"## {date_value}")
                lines.append("")

            lines.extend(self._format_notes(day.get("notes", [])))

        lines.extend(self._print_custom_fields(entry))

        return "\n".join(lines).rstrip() + "\n"

    def _print_header(self, entry: Mapping[str, object]) -> list[str]:
        title = str(entry.get("name", "Benchling Entry")).strip() or "Benchling Entry"
        return [f"# {title}", ""]

    def _print_metadata(self, entry: Mapping[str, object]) -> list[str]:
        creator_value = entry.get("creator")
        creator = creator_value if isinstance(creator_value, dict) else {}
        author = str(creator.get("name", "Unknown")).strip() or "Unknown"
        lines = [
            f"- **ID:** `{entry.get('id', '')}`",
            f"- **Display ID:** `{entry.get('displayId', '')}`",
            f"- **Created:** {entry.get('createdAt', '')}",
            f"- **Modified:** {entry.get('modifiedAt', '')}",
            f"- **Author:** {author}",
        ]
        web_url = str(entry.get("webURL", "")).strip()
        if web_url:
            lines.append(f"- **Web URL:** {web_url}")
        lines.append("")

        return lines

    def _format_notes(self, notes: object) -> list[str]:
        if not isinstance(notes, list):
            return []

        output: list[str] = []
        for index, note in enumerate(notes):
            if not isinstance(note, dict):
                continue

            note_type = str(note.get("type", "")).strip()
            indentation = note.get("indentation", 0)
            indent_level = indentation if isinstance(indentation, int) and indentation >= 0 else 0
            indent = "  " * indent_level

            handler = self.handlers.get(note_type)
            next_note = notes[index + 1] if index + 1 < len(notes) else None
            if handler:
                output.extend(handler(note, next_note, indent))
            elif note_type.endswith("_table"):
                output.extend(self._format_named_table(note, next_note, indent))
            else:
                output.extend(self._format_unknown(note, indent))

        return output

    def _format_text(self, note: Mapping[str, object], next_note: object, indent: str) -> list[str]:
        text_content = str(note.get("text", "")).strip()
        if not text_content:
            return []

        embedded_heading = self._extract_embedded_heading(text_content)
        if embedded_heading:
            main_text, heading = embedded_heading
            lines: list[str] = []
            if main_text:
                lines.extend([f"{indent}{main_text}", ""])
            if self._is_heading_context(heading, next_note):
                lines.extend([f"### {heading}", ""])
            else:
                lines.extend([f"{indent}{heading}", ""])
            return lines

        if self._is_heading_context(text_content, next_note):
            return [f"### {text_content}", ""]

        return [f"{indent}{text_content}", ""]

    def _format_table(
        self, note: Mapping[str, object], _next_note: object, indent: str
    ) -> list[str]:
        table = note.get("table")
        if not isinstance(table, dict):
            return []

        table_name = str(table.get("name", "Table")).strip() or "Table"
        lines = [f"{indent}**{table_name}**", ""]

        headers = table.get("columnLabels", [])
        if isinstance(headers, list) and headers:
            clean_headers = [str(item).strip() or "Column" for item in headers]

            lines.append(f"{indent}| " + " | ".join(clean_headers) + " |")
            lines.append(f"{indent}| " + " | ".join(["---"] * len(clean_headers)) + " |")

            for row in table.get("rows", []):
                if not isinstance(row, dict):
                    continue
                cells: list[str] = []
                for cell in row.get("cells", []):
                    if not isinstance(cell, dict):
                        continue
                    cells.append(str(cell.get("text", "")).strip())

                while len(cells) < len(clean_headers):
                    cells.append("")
                cells = cells[: len(clean_headers)]
                escaped_cells = [cell.replace("|", "\\|") for cell in cells]
                lines.append(f"{indent}| " + " | ".join(escaped_cells) + " |")

        lines.append("")

        return lines

    def _format_list_bullet(
        self, note: Mapping[str, object], _next_note: object, indent: str
    ) -> list[str]:
        text = str(note.get("text", "")).strip()
        return [f"{indent}- {text}"] if text else []

    def _format_list_checkbox(
        self, note: Mapping[str, object], _next_note: object, indent: str
    ) -> list[str]:
        text = str(note.get("text", "")).strip()
        if not text:
            return []
        checkbox = "x" if note.get("checked") else " "
        return [f"{indent}- [{checkbox}] {text}"]

    def _format_list_number(
        self, note: Mapping[str, object], _next_note: object, indent: str
    ) -> list[str]:
        text = str(note.get("text", "")).strip()
        if not text:
            return []
        number = note.get("number")
        if isinstance(number, int) and number > 0:
            return [f"{indent}{number}. {text}"]
        return [f"{indent}1. {text}"]

    def _format_external_file(
        self, note: Mapping[str, object], _next_note: object, indent: str
    ) -> list[str]:
        file_id = str(note.get("externalFileId", "Unknown file"))
        description = str(note.get("text", "")).strip()
        asset_path = self.asset_paths.get(file_id)
        link_info = self.external_file_links.get(file_id, {})
        link_url = str(link_info.get("url", "")).strip()
        link_name = str(link_info.get("name", "")).strip() or file_id
        is_pdf = bool(link_info.get("is_pdf", False))

        if asset_path:
            if asset_path.lower().endswith(_IMAGE_EXTENSIONS):
                alt_text = description or file_id
                return [f"{indent}![{alt_text}]({asset_path})", ""]
            link_text = f"**File:** [{file_id}]({asset_path})"
            if description:
                return [f"{indent}{link_text} - {description}", ""]
            return [f"{indent}{link_text}", ""]

        if link_url:
            link_text = f"**File:** [{link_name}]({link_url})"
            if is_pdf or not description:
                return [f"{indent}{link_text}", ""]
            return [f"{indent}{link_text} - {description}", ""]

        if description:
            return [f"{indent}**File:** `{file_id}` — {description}", ""]

        return [f"{indent}**File:** `{file_id}`", ""]

    def _format_text_box(
        self, note: Mapping[str, object], _next_note: object, indent: str
    ) -> list[str]:
        box_name = str(note.get("name", "")).strip()
        box_text = str(note.get("text", "")).strip()
        lines = [f"{indent}> **{box_name}**"]
        if box_text:
            lines.append(f"{indent}> {box_text}")
        lines.append("")

        return lines

    def _format_image(
        self, note: Mapping[str, object], _next_note: object, indent: str
    ) -> list[str]:
        image_id = str(note.get("imageId", "Unknown image"))
        description = str(note.get("text", "")).strip()
        asset_path = self.asset_paths.get(image_id)
        if asset_path:
            alt_text = description or image_id
            return [f"{indent}![{alt_text}]({asset_path})", ""]
        if description:
            return [f"{indent}**Image:** `{image_id}` — {description}", ""]

        return [f"{indent}**Image:** `{image_id}`", ""]

    def _format_lookup_table(
        self, note: Mapping[str, object], _next_note: object, indent: str
    ) -> list[str]:
        name = str(note.get("name", "Lookup Table")).strip() or "Lookup Table"
        lines = [f"{indent}**{name}**"]

        columns = note.get("columns")
        if isinstance(columns, list):
            column_names = [
                str(column.get("name", "")).strip()
                for column in columns
                if isinstance(column, dict) and str(column.get("name", "")).strip()
            ]
            if column_names:
                lines.append(f"{indent}- Columns: {', '.join(column_names)}")

        lines.append("")

        return lines

    def _format_named_table(
        self, note: Mapping[str, object], _next_note: object, indent: str
    ) -> list[str]:
        note_type = str(note.get("type", "table")).strip() or "table"
        name = str(note.get("name", note_type)).strip() or note_type
        return [f"{indent}**{name}** (`{note_type}`)", ""]

    def _format_dropdown(
        self, note: Mapping[str, object], _next_note: object, indent: str
    ) -> list[str]:
        text = str(note.get("text", "")).strip()
        selected = str(note.get("selected", "")).strip()
        if text and selected:
            return [f"{indent}- {text}: {selected}"]
        if text:
            return [f"{indent}- {text}"]
        if selected:
            return [f"{indent}- {selected}"]

        return []

    def _format_entity_link(
        self, note: Mapping[str, object], _next_note: object, indent: str
    ) -> list[str]:
        entity_name = str(note.get("name", "")).strip()
        entity_id = str(note.get("entityId", "")).strip()
        if entity_name and entity_id:
            return [f"{indent}- Linked entity: {entity_name} (`{entity_id}`)"]
        if entity_name:
            return [f"{indent}- Linked entity: {entity_name}"]
        if entity_id:
            return [f"{indent}- Linked entity ID: `{entity_id}`"]

        return [f"{indent}- Linked entity"]

    def _format_unknown(self, note: Mapping[str, object], indent: str) -> list[str]:
        note_type = str(note.get("type", "unknown")).strip() or "unknown"
        title = _note_title(note)
        if title:
            return [f"{indent}- [{note_type}] {title}"]

        return [f"{indent}- [{note_type}]"]

    def _extract_embedded_heading(self, text: str) -> tuple[str, str] | None:
        match = re.search(r"(.*?)([A-Z][^.!?]*:)\s*$", text)
        if not match:
            return None

        main_text = match.group(1).strip()
        potential_heading = match.group(2).strip()
        if (
            len(potential_heading) <= 80
            and "•" not in potential_heading
            and not potential_heading.lower().startswith(("tip:", "note:", "warning:", "caution:"))
        ):
            return main_text, potential_heading

        return None

    def _is_heading_context(self, text: str, next_note: object) -> bool:
        if not text:
            return False

        if (
            len(text) > 80
            or text.endswith((".", "!", "?"))
            or "•" in text
            or text.lower().startswith(("tip:", "note:", "warning:", "caution:"))
        ):
            return False

        if not isinstance(next_note, dict):
            return False

        return next_note.get("type") in {
            "table",
            "list_bullet",
            "list_checkbox",
            "text_box",
            "list_number",
        }

    def _print_custom_fields(self, entry: Mapping[str, object]) -> list[str]:
        fields = entry.get("fields")
        if not isinstance(fields, dict) or not fields:
            return []

        lines = ["## Custom Fields", ""]
        for field_name, field_data in fields.items():
            if not isinstance(field_data, dict):
                continue
            value = field_data.get("textValue") or field_data.get("displayValue")
            if value not in (None, ""):
                escaped_value = str(value).replace("|", "\\|")
                lines.append(f"- **{field_name}:** {escaped_value}")

        if lines[-1] != "":
            lines.append("")

        return lines


def _create_benchling_client(*, api_key: str, benchling_url: str) -> Benchling:
    if not api_key:
        raise ElnAuthenticationError("Benchling API key is required")

    return Benchling(url=benchling_url, auth_method=ApiKeyAuth(api_key))


def fetch_entry_by_identifier(
    identifier: str,
    *,
    api_key: str,
    benchling_url: str,
) -> dict[str, object]:
    """Fetches a notebook entry by display ID first, then entry ID as a fallback."""
    client = _create_benchling_client(api_key=api_key, benchling_url=benchling_url)

    try:
        entries = client.entries.bulk_get_entries(display_ids=[identifier]) or []
        if entries:
            return entries[0].to_dict()
    except Exception as display_error:
        try:
            return client.entries.get_entry_by_id(identifier).to_dict()
        except Exception as id_error:
            raise ElnFetchError(
                f"Failed to fetch Benchling entry by ID or display ID '{identifier}': "
                f"display ID error: {display_error}; ID error: {id_error}"
            ) from id_error

    try:
        return client.entries.get_entry_by_id(identifier).to_dict()
    except Exception as error:
        raise ElnFetchError(f"No Benchling entry found for ID/display ID '{identifier}'") from error


def _extract_external_file_ids(entry: Mapping[str, object]) -> list[str]:
    ids: set[str] = set()
    days = entry.get("days")
    for day in days if isinstance(days, list) else []:
        if not isinstance(day, dict):
            continue
        for note in day.get("notes", []):
            if not isinstance(note, dict):
                continue
            external_file_id = str(note.get("externalFileId", "")).strip()
            if external_file_id:
                ids.add(external_file_id)

    return sorted(ids)


def _extract_download_url(meta: object) -> str:
    for attr in ("download_url", "downloadUrl"):
        direct = str(getattr(meta, attr, "")).strip()
        if direct:
            return direct

    to_dict = getattr(meta, "to_dict", None)
    if callable(to_dict):
        try:
            meta_dict = to_dict()
        except Exception:
            return ""
        if isinstance(meta_dict, dict):
            for key in ("download_url", "downloadUrl", "_download_url"):
                value = str(meta_dict.get(key, "")).strip()
                if value:
                    return value

    return ""


def _safe_name(value: str, fallback: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return candidate or fallback


def _filename_from_meta(meta: object, external_file_id: str, download_url: str) -> str:
    for attr in ("name", "file_name", "filename", "fileName"):
        value = str(getattr(meta, attr, "")).strip()
        if value:
            return _safe_name(value, f"{external_file_id}.bin")

    url_name = unquote(Path(urlparse(download_url).path).name)
    if url_name:
        return _safe_name(url_name, f"{external_file_id}.bin")

    return f"{external_file_id}.bin"


def _download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:
        destination.write_bytes(response.read())


def download_external_files_for_entry(
    entry: Mapping[str, object],
    *,
    api_key: str,
    benchling_url: str,
    output_dir: Path,
) -> dict[str, Path]:
    """Download every external file or fail the incomplete entry."""
    entry_id = str(entry.get("id", "")).strip()
    file_ids = _extract_external_file_ids(entry)
    if not file_ids:
        return {}
    if not entry_id:
        raise ElnFetchError("Cannot acquire external files without an entry ID")

    client = _create_benchling_client(api_key=api_key, benchling_url=benchling_url)
    downloaded: dict[str, Path] = {}

    for file_id in file_ids:
        try:
            meta = client.entries.get_external_file(entry_id, file_id)
            download_url = _extract_download_url(meta)
            if not download_url:
                raise ElnFetchError(f"External file '{file_id}' has no download URL")

            filename = _filename_from_meta(meta, file_id, download_url)
            destination = output_dir / filename
            if destination.exists():
                destination = output_dir / f"{file_id}_{filename}"

            # Signed S3 URLs must be fetched directly, without API auth headers.
            _download_file(download_url, destination)
            downloaded[file_id] = destination
        except ElnFetchError:
            raise
        except Exception as error:
            raise ElnFetchError(f"Failed to acquire external file '{file_id}': {error}") from error

    return downloaded


def fetch_external_file_links_for_entry(
    entry: Mapping[str, object],
    *,
    api_key: str,
    benchling_url: str,
) -> dict[str, dict[str, object]]:
    """Fetches external file metadata and direct URLs without downloading bytes."""
    entry_id = str(entry.get("id", "")).strip()
    file_ids = _extract_external_file_ids(entry)
    if not entry_id or not file_ids:
        return {}

    client = _create_benchling_client(api_key=api_key, benchling_url=benchling_url)
    links: dict[str, dict[str, object]] = {}

    for file_id in file_ids:
        try:
            meta = client.entries.get_external_file(entry_id, file_id)
            download_url = _extract_download_url(meta)
            if not download_url:
                continue

            filename = _filename_from_meta(meta, file_id, download_url)
            url_path = urlparse(download_url).path.lower()
            links[file_id] = {
                "name": filename,
                "url": download_url,
                "is_pdf": filename.lower().endswith(".pdf") or url_path.endswith(".pdf"),
            }
        except Exception:
            continue

    return links


def _entry_metadata(entry: Mapping[str, object]) -> dict[str, MetadataValue]:
    creator = entry.get("creator")
    author = str(creator.get("name", "")).strip() if isinstance(creator, dict) else ""

    return {
        "id": _optional_str(entry.get("id")),
        "name": _optional_str(entry.get("name")),
        "display_id": _optional_str(entry.get("displayId")),
        "created_at": _optional_str(entry.get("createdAt")),
        "modified_at": _optional_str(entry.get("modifiedAt")),
        "author": author or None,
        "web_url": _optional_str(entry.get("webURL")),
    }


def _optional_str(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _relative_to_dir(target: Path, base_dir: Path) -> str:
    # Same rationale as document_normalizer's helper of the same name:
    # Markdown links resolve against the file's own directory, not the
    # workspace root that Asset.path uses.
    return Path(os.path.relpath(target, base_dir)).as_posix()


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)

    path.mkdir(parents=True)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    try:
        with path.open("rb") as file:
            while chunk := file.read(_HASH_CHUNK_SIZE):
                digest.update(chunk)
    except OSError as error:
        raise ElnNormalizationError(f"Cannot hash file: {path}") from error

    return digest.hexdigest()


class ElnNormalizer:
    def __init__(self, staging_root: Path, api_key: str, benchling_url: str) -> None:
        self._root = staging_root.resolve()
        self._api_key = api_key
        self._benchling_url = benchling_url

        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ElnNormalizationError(f"Cannot create staging root: {self._root}") from error

    def normalize_entry(self, source: ElnSource) -> NormalizedDocument:
        if not source.source_instance_id.strip():
            raise ElnNormalizationError("Source instance ID is required")

        entry = fetch_entry_by_identifier(
            source.entry_id, api_key=self._api_key, benchling_url=self._benchling_url
        )
        entry_bytes = json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8")
        entry_hash = _sha256_bytes(entry_bytes)
        source_id = make_source_id(entry_hash)

        original_path = self._preserve_source(source_id, entry_bytes, entry_hash)
        assets_dir = self._root / "assets" / source_id
        _reset_dir(assets_dir)

        try:
            links = fetch_external_file_links_for_entry(
                entry, api_key=self._api_key, benchling_url=self._benchling_url
            )
        except Exception as error:
            raise ElnFetchError(f"Cannot fetch external file links: {error}") from error

        try:
            downloaded = download_external_files_for_entry(
                entry,
                api_key=self._api_key,
                benchling_url=self._benchling_url,
                output_dir=assets_dir,
            )
        except Exception as error:
            raise ElnFetchError(f"Cannot download external files: {error}") from error

        normalized_dir = self._root / "normalized" / source_id
        markdown_path = normalized_dir / "document.md"
        formatter_asset_paths = {
            file_id: _relative_to_dir(path, normalized_dir) for file_id, path in downloaded.items()
        }

        try:
            markdown = BenchlingFormatter(
                asset_paths=formatter_asset_paths,
                external_file_links=links,
            ).format_entry(entry)
        except Exception as error:
            raise ElnParseError(f"Cannot render entry to Markdown: {source.entry_id}") from error

        try:
            normalized_dir.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(markdown, encoding="utf-8")
        except OSError as error:
            raise ElnNormalizationError(
                f"Cannot write normalized Markdown: {markdown_path}"
            ) from error

        embedded_files = tuple(
            EmbeddedFile(
                path=self._relative(path),
                original_name=path.name,
                description=None,
                size=path.stat().st_size,
                sha256=_sha256_file(path),
            )
            for path in sorted(downloaded.values())
        )

        result = NormalizedDocument(
            source_id=source_id,
            source_instance_id=source.source_instance_id,
            source_type=_SOURCE_TYPE,
            original_path=self._relative(original_path),
            normalized_path=self._relative(markdown_path),
            assets=(),
            embedded_files=embedded_files,
            links=(),
            page_map=(),
            header_footer=(),
            metadata=_entry_metadata(entry),
            hashes=FileHashes(
                source_sha256=entry_hash,
                normalized_sha256=_sha256_file(markdown_path),
            ),
            tooling=Tooling(
                normalizer=_NORMALIZER_NAME,
                normalizer_version=version(_PACKAGE_NAME),
                converter=None,
                converter_version=None,
            ),
            warnings=(),
        )
        self._validate(result)

        return result

    def _preserve_source(self, source_id: str, entry_bytes: bytes, entry_hash: str) -> Path:
        source_dir = self._root / "sources" / source_id
        source_dir.mkdir(parents=True, exist_ok=True)
        original_path = source_dir / "original.json"

        if original_path.exists():
            if _sha256_file(original_path) != entry_hash:
                raise ElnNormalizationError(f"Source ID collision at: {original_path}")
            return original_path

        try:
            original_path.write_bytes(entry_bytes)
        except OSError as error:
            raise ElnNormalizationError(f"Cannot preserve source: {original_path}") from error

        return original_path

    def _validate(self, document: NormalizedDocument) -> None:
        source_path = self._workspace_path(document.original_path)
        normalized_path = self._workspace_path(document.normalized_path)
        if not source_path.is_file() or _sha256_file(source_path) != document.hashes.source_sha256:
            raise ElnNormalizationError("Preserved source failed validation")
        if (
            not normalized_path.is_file()
            or _sha256_file(normalized_path) != document.hashes.normalized_sha256
        ):
            raise ElnNormalizationError("Normalized Markdown failed validation")

        for artifact in (*document.assets, *document.embedded_files):
            artifact_path = self._workspace_path(artifact.path)
            if not artifact_path.is_file() or _sha256_file(artifact_path) != artifact.sha256:
                raise ElnNormalizationError(f"Artifact failed validation: {artifact.path}")

        if not document.tooling.normalizer_version:
            raise ElnNormalizationError("Normalizer version is missing")

    def _workspace_path(self, relative_path: str) -> Path:
        path = (self._root / relative_path).resolve()

        try:
            path.relative_to(self._root)
        except ValueError as error:
            raise ElnNormalizationError(
                f"Output path escapes staging root: {relative_path}"
            ) from error

        return path

    def _relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self._root).as_posix()
        except ValueError as error:
            raise ElnNormalizationError(f"Output path escapes staging root: {path}") from error
