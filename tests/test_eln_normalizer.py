from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock, patch

import pytest

from report_writing_collaborator import (
    ElnFetchError,
    ElnNormalizationError,
    ElnNormalizer,
    ElnSource,
)
from report_writing_collaborator.eln_normalizer import (
    BenchlingFormatter,
    download_external_files_for_entry,
)

if TYPE_CHECKING:
    from pathlib import Path


def _append_note(entry: dict[str, object], note: dict[str, object]) -> None:
    days = cast("list[dict[str, object]]", entry["days"])
    notes = cast("list[dict[str, object]]", days[0]["notes"])
    notes.append(note)


def _sample_entry(*, entry_id: str = "etr_1", name: str = "Study Entry") -> dict[str, object]:
    return {
        "id": entry_id,
        "displayId": "EXP001",
        "name": name,
        "createdAt": "2026-01-01T00:00:00Z",
        "modifiedAt": "2026-01-02T00:00:00Z",
        "creator": {"name": "Ada Lovelace"},
        "webURL": "https://example.benchling.com/etr_1",
        "days": [
            {
                "date": "2026-01-01",
                "notes": [
                    {"type": "text", "text": "Observations:"},
                    {
                        "type": "table",
                        "table": {
                            "name": "Results",
                            "columnLabels": ["Sample", "OD600"],
                            "rows": [
                                {
                                    "cells": [
                                        {"text": "A1"},
                                        {"text": "0.5"},
                                    ]
                                }
                            ],
                        },
                    },
                    {"type": "list_bullet", "text": "Bullet point"},
                    {"type": "list_checkbox", "text": "Checked item", "checked": True},
                ],
            }
        ],
        "fields": {
            "Species": {"textValue": "Mouse"},
        },
    }


def test_benchling_formatter_renders_text_table_and_lists() -> None:
    formatter = BenchlingFormatter()

    markdown = formatter.format_entry(_sample_entry())

    assert "# Study Entry" in markdown
    assert "**Author:** Ada Lovelace" in markdown
    assert "## 2026-01-01" in markdown
    assert "### Observations:" in markdown
    assert "| Sample | OD600 |" in markdown
    assert "| A1 | 0.5 |" in markdown
    assert "- Bullet point" in markdown
    assert "- [x] Checked item" in markdown
    assert "## Custom Fields" in markdown
    assert "**Species:** Mouse" in markdown


def test_benchling_formatter_links_downloaded_asset() -> None:
    entry = _sample_entry()
    _append_note(entry, {"type": "image", "imageId": "img_1", "text": "A plot"})
    formatter = BenchlingFormatter(asset_paths={"img_1": "../../assets/src_x/img_1.png"})

    markdown = formatter.format_entry(entry)

    assert "![A plot](../../assets/src_x/img_1.png)" in markdown


def test_benchling_formatter_degrades_gracefully_on_unknown_note_type() -> None:
    entry = _sample_entry()
    days = cast("list[dict[str, object]]", entry["days"])
    days[0]["notes"] = [{"type": "some_future_type", "name": "Mystery"}]
    formatter = BenchlingFormatter()

    markdown = formatter.format_entry(entry)

    assert "[some_future_type] Mystery" in markdown


def test_normalize_entry_produces_normalized_document(tmp_path: Path) -> None:
    entry = _sample_entry()

    with (
        patch(
            "report_writing_collaborator.eln_normalizer.fetch_entry_by_identifier",
            return_value=entry,
        ),
        patch(
            "report_writing_collaborator.eln_normalizer.fetch_external_file_links_for_entry",
            return_value={},
        ),
        patch(
            "report_writing_collaborator.eln_normalizer.download_external_files_for_entry",
            return_value={},
        ),
    ):
        normalizer = ElnNormalizer(tmp_path, api_key="key", benchling_url="https://x.benchling.com")
        result = normalizer.normalize_entry(
            ElnSource(entry_id="etr_1", source_instance_id="source_01")
        )

    assert result.source_type == "eln"
    assert result.source_instance_id == "source_01"
    assert result.source_id == f"src_{result.hashes.source_sha256[:12]}"
    assert (tmp_path / result.original_path).is_file()
    assert (tmp_path / result.normalized_path).is_file()
    stored_entry = json.loads((tmp_path / result.original_path).read_text(encoding="utf-8"))
    assert stored_entry == entry
    markdown = (tmp_path / result.normalized_path).read_text(encoding="utf-8")
    assert "# Study Entry" in markdown
    assert result.metadata["author"] == "Ada Lovelace"
    assert result.metadata["display_id"] == "EXP001"
    assert result.metadata["name"] == "Study Entry"
    assert result.page_map == ()
    assert result.header_footer == ()
    assert result.embedded_files == ()
    assert result.links == ()
    assert result.warnings == ()


def test_normalize_entry_reports_downloads_as_embedded_files(tmp_path: Path) -> None:
    entry = _sample_entry()
    _append_note(entry, {"type": "image", "imageId": "img_1", "text": "A plot"})

    def fake_download(_entry, *, api_key, benchling_url, output_dir):
        destination = output_dir / "plot.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"\x89PNG")
        return {"img_1": destination}

    with (
        patch(
            "report_writing_collaborator.eln_normalizer.fetch_entry_by_identifier",
            return_value=entry,
        ),
        patch(
            "report_writing_collaborator.eln_normalizer.fetch_external_file_links_for_entry",
            return_value={},
        ),
        patch(
            "report_writing_collaborator.eln_normalizer.download_external_files_for_entry",
            side_effect=fake_download,
        ),
    ):
        normalizer = ElnNormalizer(tmp_path, api_key="key", benchling_url="https://x.benchling.com")
        result = normalizer.normalize_entry(
            ElnSource(entry_id="etr_1", source_instance_id="source_01")
        )

    assert result.assets == ()
    assert len(result.embedded_files) == 1
    assert (tmp_path / result.embedded_files[0].path).is_file()
    markdown = (tmp_path / result.normalized_path).read_text(encoding="utf-8")
    assert "![A plot](../../assets/" in markdown


def test_normalize_entry_propagates_download_failure(tmp_path: Path) -> None:
    entry = _sample_entry()

    with (
        patch(
            "report_writing_collaborator.eln_normalizer.fetch_entry_by_identifier",
            return_value=entry,
        ),
        patch(
            "report_writing_collaborator.eln_normalizer.fetch_external_file_links_for_entry",
            return_value={},
        ),
        patch(
            "report_writing_collaborator.eln_normalizer.download_external_files_for_entry",
            side_effect=ElnFetchError("Failed to acquire external file 'ext_1'"),
        ),
        pytest.raises(ElnFetchError, match="ext_1"),
    ):
        normalizer = ElnNormalizer(
            tmp_path,
            api_key="key",
            benchling_url="https://x.benchling.com",
        )
        normalizer.normalize_entry(ElnSource(entry_id="etr_1", source_instance_id="source_01"))


def test_external_file_download_failure_is_fatal(tmp_path: Path) -> None:
    entry = _sample_entry()
    _append_note(
        entry,
        {"type": "external_file", "externalFileId": "ext_1", "name": "Evidence"},
    )
    client = Mock()
    client.entries.get_external_file.side_effect = OSError("timeout")

    with (
        patch(
            "report_writing_collaborator.eln_normalizer._create_benchling_client",
            return_value=client,
        ),
        pytest.raises(ElnFetchError, match="ext_1"),
    ):
        download_external_files_for_entry(
            entry,
            api_key="key",
            benchling_url="https://x.benchling.com",
            output_dir=tmp_path,
        )


def test_external_file_requires_entry_id(tmp_path: Path) -> None:
    entry = _sample_entry()
    entry.pop("id")
    _append_note(
        entry,
        {"type": "external_file", "externalFileId": "ext_1", "name": "Evidence"},
    )

    with pytest.raises(ElnFetchError, match="entry ID"):
        download_external_files_for_entry(
            entry,
            api_key="key",
            benchling_url="https://x.benchling.com",
            output_dir=tmp_path,
        )


def test_normalize_entry_wraps_fetch_failure(tmp_path: Path) -> None:
    with patch(
        "report_writing_collaborator.eln_normalizer.fetch_entry_by_identifier",
        side_effect=ElnFetchError("boom"),
    ):
        normalizer = ElnNormalizer(tmp_path, api_key="key", benchling_url="https://x.benchling.com")

        with pytest.raises(ElnFetchError):
            normalizer.normalize_entry(ElnSource(entry_id="etr_1", source_instance_id="source_01"))


def test_normalize_entry_requires_source_instance_id(tmp_path: Path) -> None:
    normalizer = ElnNormalizer(tmp_path, api_key="key", benchling_url="https://x.benchling.com")

    with pytest.raises(ElnNormalizationError, match="instance ID is required"):
        normalizer.normalize_entry(ElnSource(entry_id="etr_1", source_instance_id=""))


def test_two_entries_get_distinct_source_ids(tmp_path: Path) -> None:
    entry_a = _sample_entry(entry_id="etr_a", name="Entry A")
    entry_b = _sample_entry(entry_id="etr_b", name="Entry B")

    def fake_fetch(identifier, *, api_key, benchling_url):
        return entry_a if identifier == "etr_a" else entry_b

    with (
        patch(
            "report_writing_collaborator.eln_normalizer.fetch_entry_by_identifier",
            side_effect=fake_fetch,
        ),
        patch(
            "report_writing_collaborator.eln_normalizer.fetch_external_file_links_for_entry",
            return_value={},
        ),
        patch(
            "report_writing_collaborator.eln_normalizer.download_external_files_for_entry",
            return_value={},
        ),
    ):
        normalizer = ElnNormalizer(tmp_path, api_key="key", benchling_url="https://x.benchling.com")
        result_a = normalizer.normalize_entry(
            ElnSource(entry_id="etr_a", source_instance_id="source_01")
        )
        result_b = normalizer.normalize_entry(
            ElnSource(entry_id="etr_b", source_instance_id="source_02")
        )

    assert result_a.source_id != result_b.source_id
