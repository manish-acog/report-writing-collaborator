from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from importlib.metadata import version
from typing import TYPE_CHECKING

from report_writing_collaborator.exceptions import StructureIndexingError

if TYPE_CHECKING:
    from pathlib import Path

    from report_writing_collaborator.document_normalizer import NormalizedDocument, PageMapping

_PACKAGE_NAME = "report-writing-collaborator"
_INDEXER_NAME = "report_writing_collaborator.structure_indexer"
_SECTION_ID_LENGTH = 12
_ATX_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*$")
_FENCE_MARKER = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_WHOLE_TITLE_BOLD = re.compile(r"^(\*\*|__)(.+)\1$")
_WHITESPACE_RUN = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class Section:
    section_id: str
    title: str
    heading_level: int
    heading_path: tuple[str, ...]
    start_line: int
    end_line: int
    source_pages: tuple[int, ...]
    parent_section_id: str | None


@dataclass(frozen=True, slots=True)
class StructureHashes:
    structure_sha256: str


@dataclass(frozen=True, slots=True)
class IndexerTooling:
    indexer: str
    indexer_version: str


@dataclass(frozen=True, slots=True)
class DocumentStructure:
    source_id: str
    sections: tuple[Section, ...]
    hashes: StructureHashes
    tooling: IndexerTooling
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Heading:
    level: int
    title: str
    line_number: int


@dataclass(slots=True)
class _PendingSection:
    heading: _Heading
    section_id: str
    heading_path: tuple[str, ...]
    parent_section_id: str | None
    end_line: int = field(default=0)


class StructureIndexer:
    def __init__(self, workspace_root: Path) -> None:
        self._root = workspace_root.resolve()

    def index_structure(self, document: NormalizedDocument) -> DocumentStructure:
        markdown_path = self._workspace_path(document.normalized_path)
        lines = self._read_lines(markdown_path)
        headings, scan_warnings = _scan_headings(lines)
        sections = _build_sections(document.source_id, headings, len(lines), document.page_map)

        structure = DocumentStructure(
            source_id=document.source_id,
            sections=sections,
            hashes=StructureHashes(structure_sha256=_structure_hash(document.source_id, sections)),
            tooling=IndexerTooling(
                indexer=_INDEXER_NAME,
                indexer_version=version(_PACKAGE_NAME),
            ),
            warnings=scan_warnings,
        )
        self._validate(structure)

        return structure

    def _workspace_path(self, relative_path: str) -> Path:
        path = (self._root / relative_path).resolve()

        try:
            path.relative_to(self._root)
        except ValueError as error:
            raise StructureIndexingError(
                f"Normalized Markdown path escapes workspace root: {relative_path}"
            ) from error

        return path

    def _read_lines(self, markdown_path: Path) -> list[str]:
        try:
            text = markdown_path.read_text(encoding="utf-8")
        except OSError as error:
            raise StructureIndexingError(
                f"Cannot read normalized Markdown: {markdown_path}"
            ) from error

        return text.splitlines()

    def _validate(self, structure: DocumentStructure) -> None:
        section_ids = {section.section_id for section in structure.sections}
        if len(section_ids) != len(structure.sections):
            raise StructureIndexingError("Duplicate section IDs detected")

        for section in structure.sections:
            if section.start_line < 1 or section.end_line < section.start_line:
                raise StructureIndexingError(
                    f"Invalid line range for section: {section.section_id}"
                )
            if (
                section.parent_section_id is not None
                and section.parent_section_id not in section_ids
            ):
                raise StructureIndexingError(f"Missing parent section: {section.parent_section_id}")

        if not structure.hashes.structure_sha256:
            raise StructureIndexingError("Structure hash is missing")


def _scan_headings(lines: list[str]) -> tuple[list[_Heading], tuple[str, ...]]:
    headings: list[_Heading] = []
    warnings: list[str] = []
    fence_char: str | None = None
    fence_length = 0

    for line_number, line in enumerate(lines, start=1):
        fence_match = _FENCE_MARKER.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if fence_char is None:
                fence_char, fence_length = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_length:
                fence_char = None
            continue

        if fence_char is not None:
            continue

        heading_match = _ATX_HEADING.match(line)
        if not heading_match:
            continue

        title = _clean_title(heading_match.group(2))
        if not title:
            warnings.append(f"Skipped heading with empty title at line {line_number}")
            continue

        headings.append(
            _Heading(level=len(heading_match.group(1)), title=title, line_number=line_number)
        )

    return headings, tuple(warnings)


def _clean_title(raw_title: str) -> str:
    bold_match = _WHOLE_TITLE_BOLD.match(raw_title)
    return bold_match.group(2) if bold_match else raw_title


def _normalize_title(title: str) -> str:
    return _WHITESPACE_RUN.sub(" ", title).strip().lower()


def _build_sections(
    source_id: str,
    headings: list[_Heading],
    total_lines: int,
    page_map: tuple[PageMapping, ...],
) -> tuple[Section, ...]:
    pending: list[_PendingSection] = []
    # Open ancestors, nearest last; a heading closes every stack entry at its
    # level or deeper (nested extent: a parent's range spans its children).
    stack: list[tuple[_Heading, int]] = []
    sibling_occurrences: dict[tuple[str | None, str], int] = {}

    for heading in headings:
        while stack and stack[-1][0].level >= heading.level:
            _, closed_index = stack.pop()
            pending[closed_index].end_line = heading.line_number - 1

        if stack:
            parent_index = stack[-1][1]
            parent_section_id = pending[parent_index].section_id
            parent_path = pending[parent_index].heading_path
        else:
            parent_section_id = None
            parent_path = ()

        normalized_title = _normalize_title(heading.title)
        occurrence_key = (parent_section_id, normalized_title)
        occurrence = sibling_occurrences.get(occurrence_key, 0) + 1
        sibling_occurrences[occurrence_key] = occurrence

        identity = (
            source_id,
            *(_normalize_title(ancestor) for ancestor in parent_path),
            normalized_title,
            f"occurrence_{occurrence}",
        )
        index = len(pending)
        pending.append(
            _PendingSection(
                heading=heading,
                section_id=_section_id(identity),
                heading_path=(*parent_path, heading.title),
                parent_section_id=parent_section_id,
            )
        )
        stack.append((heading, index))

    while stack:
        _, closed_index = stack.pop()
        pending[closed_index].end_line = total_lines

    return tuple(
        Section(
            section_id=item.section_id,
            title=item.heading.title,
            heading_level=item.heading.level,
            heading_path=item.heading_path,
            start_line=item.heading.line_number,
            end_line=item.end_line,
            source_pages=_pages_for_range(item.heading.line_number, item.end_line, page_map),
            parent_section_id=item.parent_section_id,
        )
        for item in pending
    )


def _pages_for_range(
    start_line: int,
    end_line: int,
    page_map: tuple[PageMapping, ...],
) -> tuple[int, ...]:
    return tuple(
        mapping.page_number
        for mapping in page_map
        if mapping.start_line is not None
        and mapping.end_line is not None
        and mapping.start_line <= end_line
        and mapping.end_line >= start_line
    )


def _section_id(identity: tuple[str, ...]) -> str:
    digest = hashlib.sha256("\n".join(identity).encode("utf-8")).hexdigest()
    return f"sec_{digest[:_SECTION_ID_LENGTH]}"


def _structure_hash(source_id: str, sections: tuple[Section, ...]) -> str:
    parts = [source_id]
    for section in sections:
        parts.extend((section.section_id, str(section.start_line), str(section.end_line)))

    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
