"""Benchling parser utilities.

Fetches a Benchling entry by ID or display ID from the API and renders markdown
with note-type aware formatting.
"""

from __future__ import annotations
import argparse
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import urlopen
from dotenv import load_dotenv
from benchling_sdk.auth.api_key_auth import ApiKeyAuth
from benchling_sdk.benchling import Benchling



def _note_title(note: dict[str, Any]) -> str:
  text_value = str(note.get("text", "")).strip()
  if text_value:
    return text_value
  name_value = str(note.get("name", "")).strip()
  if name_value:
    return name_value
  return ""


class BenchlingFormatter:
  """Formatter that dispatches by note type and degrades gracefully."""

  def __init__(
    self,
    *,
    asset_paths: dict[str, str] | None = None,
    external_file_links: dict[str, dict[str, Any]] | None = None,
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

  def format_entry(self, entry: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.extend(self._print_header(entry))
    lines.extend(self._print_metadata(entry))

    for day in entry.get("days", []):
      if not isinstance(day, dict):
        continue

      date_value = str(day.get("date", "")).strip()
      if date_value:
        lines.append(f"## {date_value}")
        lines.append("")

      lines.extend(self._format_notes(day.get("notes", [])))

    lines.extend(self._print_custom_fields(entry))
    return "\n".join(lines).rstrip() + "\n"

  def _print_header(self, entry: dict[str, Any]) -> list[str]:
    title = str(entry.get("name", "Benchling Entry")).strip() or "Benchling Entry"
    return [f"# {title}", ""]

  def _print_metadata(self, entry: dict[str, Any]) -> list[str]:
    creator = entry.get("creator") if isinstance(entry.get("creator"), dict) else {}
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

  def _format_notes(self, notes: Any) -> list[str]:
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

  def _format_text(self, note: dict[str, Any], next_note: Any, indent: str) -> list[str]:
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

  def _format_table(self, note: dict[str, Any], _next_note: Any, indent: str) -> list[str]:
    table = note.get("table")
    if not isinstance(table, dict):
      return []

    table_name = str(table.get("name", "Table")).strip() or "Table"
    lines = [f"{indent}**{table_name}**", ""]

    headers = table.get("columnLabels", [])
    if isinstance(headers, list) and headers:
      clean_headers = [
        str(item).strip() if str(item).strip() else "Column"
        for item in headers
      ]

      lines.append(f"{indent}| " + " | ".join(clean_headers) + " |")
      lines.append(f"{indent}| " + " | ".join(["---"] * len(clean_headers)) + " |")

      for row in table.get("rows", []):
        if not isinstance(row, dict):
          continue
        cells: list[str] = []
        for cell in row.get("cells", []):
          if not isinstance(cell, dict):
            continue
          cell_text = str(cell.get("text", "")).strip()
          cells.append(cell_text)

        while len(cells) < len(clean_headers):
          cells.append("")
        cells = cells[: len(clean_headers)]
        escaped_cells = [cell.replace("|", "\\|") for cell in cells]
        lines.append(f"{indent}| " + " | ".join(escaped_cells) + " |")

    lines.append("")
    return lines

  def _format_list_bullet(self, note: dict[str, Any], _next_note: Any, indent: str) -> list[str]:
    text = str(note.get("text", "")).strip()
    return [f"{indent}- {text}"] if text else []

  def _format_list_checkbox(self, note: dict[str, Any], _next_note: Any, indent: str) -> list[str]:
    text = str(note.get("text", "")).strip()
    if not text:
      return []
    checkbox = "x" if note.get("checked") else " "
    return [f"{indent}- [{checkbox}] {text}"]

  def _format_list_number(self, note: dict[str, Any], _next_note: Any, indent: str) -> list[str]:
    text = str(note.get("text", "")).strip()
    if not text:
      return []
    number = note.get("number")
    if isinstance(number, int) and number > 0:
      return [f"{indent}{number}. {text}"]
    return [f"{indent}1. {text}"]

  def _format_external_file(self, note: dict[str, Any], _next_note: Any, indent: str) -> list[str]:
    file_id = str(note.get("externalFileId", "Unknown file"))
    description = str(note.get("text", "")).strip()
    asset_path = self.asset_paths.get(file_id)
    link_info = self.external_file_links.get(file_id, {})
    link_url = str(link_info.get("url", "")).strip()
    link_name = str(link_info.get("name", "")).strip() or file_id
    is_pdf = bool(link_info.get("is_pdf", False))

    if asset_path:
      lower_path = asset_path.lower()
      if lower_path.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff")):
        alt_text = description or file_id
        return [f"{indent}![{alt_text}]({asset_path})", ""]
      link_text = f"**File:** [{file_id}]({asset_path})"
      if description:
        return [f"{indent}{link_text} - {description}", ""]
      return [f"{indent}{link_text}", ""]

    if link_url:
      link_text = f"**File:** [{link_name}]({link_url})"
      if is_pdf:
        return [f"{indent}{link_text}", ""]
      if description:
        return [f"{indent}{link_text} - {description}", ""]
      return [f"{indent}{link_text}", ""]

    if description:
      return [f"{indent}**File:** `{file_id}` — {description}", ""]
    return [f"{indent}**File:** `{file_id}`", ""]

  def _format_text_box(self, note: dict[str, Any], _next_note: Any, indent: str) -> list[str]:
    box_name = str(note.get("name", "")).strip()
    box_text = str(note.get("text", "")).strip()
    lines = [f"{indent}> **{box_name}**"]
    if box_text:
      lines.append(f"{indent}> {box_text}")
    lines.append("")
    return lines

  def _format_image(self, note: dict[str, Any], _next_note: Any, indent: str) -> list[str]:
    image_id = str(note.get("imageId", "Unknown image"))
    description = str(note.get("text", "")).strip()
    asset_path = self.asset_paths.get(image_id)
    if asset_path:
      alt_text = description or image_id
      return [f"{indent}![{alt_text}]({asset_path})", ""]
    if description:
      return [f"{indent}**Image:** `{image_id}` — {description}", ""]
    return [f"{indent}**Image:** `{image_id}`", ""]

  def _format_lookup_table(self, note: dict[str, Any], _next_note: Any, indent: str) -> list[str]:
    name = str(note.get("name", "Lookup Table")).strip() or "Lookup Table"
    lines = [f"{indent}**{name}**"]

    columns = note.get("columns")
    if isinstance(columns, list):
      column_names: list[str] = []
      for column in columns:
        if not isinstance(column, dict):
          continue
        column_name = str(column.get("name", "")).strip()
        if column_name:
          column_names.append(column_name)
      if column_names:
        lines.append(f"{indent}- Columns: {', '.join(column_names)}")

    lines.append("")
    return lines

  def _format_named_table(self, note: dict[str, Any], _next_note: Any, indent: str) -> list[str]:
    note_type = str(note.get("type", "table")).strip() or "table"
    name = str(note.get("name", note_type)).strip() or note_type
    return [f"{indent}**{name}** (`{note_type}`)", ""]

  def _format_dropdown(self, note: dict[str, Any], _next_note: Any, indent: str) -> list[str]:
    text = str(note.get("text", "")).strip()
    selected = str(note.get("selected", "")).strip()
    if text and selected:
      return [f"{indent}- {text}: {selected}"]
    if text:
      return [f"{indent}- {text}"]
    if selected:
      return [f"{indent}- {selected}"]
    return []

  def _format_entity_link(self, note: dict[str, Any], _next_note: Any, indent: str) -> list[str]:
    entity_name = str(note.get("name", "")).strip()
    entity_id = str(note.get("entityId", "")).strip()
    if entity_name and entity_id:
      return [f"{indent}- Linked entity: {entity_name} (`{entity_id}`)"]
    if entity_name:
      return [f"{indent}- Linked entity: {entity_name}"]
    if entity_id:
      return [f"{indent}- Linked entity ID: `{entity_id}`"]
    return [f"{indent}- Linked entity"]

  def _format_unknown(self, note: dict[str, Any], indent: str) -> list[str]:
    note_type = str(note.get("type", "unknown")).strip() or "unknown"
    title = _note_title(note)
    if title:
      return [f"{indent}- [{note_type}] {title}"]
    return [f"{indent}- [{note_type}]"]

  def _extract_embedded_heading(self, text: str) -> tuple[str, str] | None:
    heading_pattern = r"(.*?)([A-Z][^.!?]*:)\s*$"
    match = re.search(heading_pattern, text)
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

  def _is_heading_context(self, text: str, next_note: Any) -> bool:
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

    return next_note.get("type") in ["table", "list_bullet", "list_checkbox", "text_box", "list_number"]

  def _print_custom_fields(self, entry: dict[str, Any]) -> list[str]:
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
  if Benchling is None or ApiKeyAuth is None:
    raise RuntimeError("benchling_sdk is not installed. Run 'uv add benchling_sdk'.")
  if not api_key:
    raise ValueError("Benchling API key is required for API mode")
  return Benchling(url=benchling_url, auth_method=ApiKeyAuth(api_key))


def fetch_entry_by_id(entry_id: str, *, api_key: str, benchling_url: str) -> dict[str, Any]:
  client = _create_benchling_client(api_key=api_key, benchling_url=benchling_url)

  entry = client.entries.get_entry_by_id(entry_id)
  return entry.to_dict()


def fetch_entry_by_identifier(identifier: str, *, api_key: str, benchling_url: str) -> dict[str, Any]:
  """Fetch a notebook entry by display ID first, then entry ID as a fallback."""
  client = _create_benchling_client(api_key=api_key, benchling_url=benchling_url)

  try:
    entries = client.entries.bulk_get_entries(display_ids=[identifier]) or []
    if entries:
      return entries[0].to_dict()
  except Exception as display_error:
    try:
      entry = client.entries.get_entry_by_id(identifier)
      return entry.to_dict()
    except Exception as id_error:
      raise RuntimeError(
        f"Failed to fetch Benchling entry by ID or display ID '{identifier}'. "
        f"Display ID error: {display_error}. ID error: {id_error}"
      ) from id_error

  try:
    entry = client.entries.get_entry_by_id(identifier)
    return entry.to_dict()
  except Exception as id_error:
    raise ValueError(f"No Benchling entry found for ID/display ID '{identifier}'.") from id_error


def _extract_external_file_ids(entry: dict[str, Any]) -> list[str]:
  ids: set[str] = set()
  for day in entry.get("days", []):
    if not isinstance(day, dict):
      continue
    for note in day.get("notes", []):
      if not isinstance(note, dict):
        continue
      external_file_id = str(note.get("externalFileId", "")).strip()
      if external_file_id:
        ids.add(external_file_id)
  return sorted(ids)


def _extract_download_url(meta: Any) -> str:
  direct = str(getattr(meta, "download_url", "")).strip()
  if direct:
    return direct

  direct_alt = str(getattr(meta, "downloadUrl", "")).strip()
  if direct_alt:
    return direct_alt

  if hasattr(meta, "to_dict"):
    try:
      meta_dict = meta.to_dict()
      if isinstance(meta_dict, dict):
        for key in ("download_url", "downloadUrl", "_download_url"):
          value = str(meta_dict.get(key, "")).strip()
          if value:
            return value
    except Exception:
      return ""

  return ""


def _safe_name(value: str, fallback: str) -> str:
  candidate = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
  return candidate or fallback


def _filename_from_meta(meta: Any, external_file_id: str, download_url: str) -> str:
  for attr in ("name", "file_name", "filename", "fileName"):
    value = str(getattr(meta, attr, "")).strip()
    if value:
      return _safe_name(value, f"{external_file_id}.bin")

  parsed = urlparse(download_url)
  url_name = unquote(Path(parsed.path).name)
  if url_name:
    return _safe_name(url_name, f"{external_file_id}.bin")

  return f"{external_file_id}.bin"


def _download_file(url: str, destination: Path, timeout_seconds: int = 60) -> None:
  destination.parent.mkdir(parents=True, exist_ok=True)
  with urlopen(url, timeout=timeout_seconds) as response:
    destination.write_bytes(response.read())


def download_external_files_for_entry(
  entry: dict[str, Any],
  *,
  api_key: str,
  benchling_url: str,
  output_dir: Path,
) -> dict[str, Path]:
  entry_id = str(entry.get("id", "")).strip()
  if not entry_id:
    return {}

  file_ids = _extract_external_file_ids(entry)
  if not file_ids:
    return {}

  client = _create_benchling_client(api_key=api_key, benchling_url=benchling_url)
  downloaded: dict[str, Path] = {}

  for file_id in file_ids:
    try:
      meta = client.entries.get_external_file(entry_id, file_id)
      download_url = _extract_download_url(meta)
      if not download_url:
        continue

      filename = _filename_from_meta(meta, file_id, download_url)
      destination = output_dir / filename
      if destination.exists():
        destination = output_dir / f"{file_id}_{filename}"

      # Signed S3 URLs should be fetched directly, without API Authorization headers.
      _download_file(download_url, destination)
      downloaded[file_id] = destination
    except Exception as exc:
      print(f"Warning: failed to download external file '{file_id}': {exc}")

  return downloaded


def fetch_external_file_links_for_entry(
  entry: dict[str, Any],
  *,
  api_key: str,
  benchling_url: str,
) -> dict[str, dict[str, Any]]:
  """Fetch external file metadata and direct URLs without downloading file bytes."""
  entry_id = str(entry.get("id", "")).strip()
  if not entry_id:
    return {}

  file_ids = _extract_external_file_ids(entry)
  if not file_ids:
    return {}

  client = _create_benchling_client(api_key=api_key, benchling_url=benchling_url)
  links: dict[str, dict[str, Any]] = {}

  for file_id in file_ids:
    try:
      meta = client.entries.get_external_file(entry_id, file_id)
      download_url = _extract_download_url(meta)
      if not download_url:
        continue

      filename = _filename_from_meta(meta, file_id, download_url)
      url_path = urlparse(download_url).path.lower()
      is_pdf = filename.lower().endswith(".pdf") or url_path.endswith(".pdf")
      links[file_id] = {
        "name": filename,
        "url": download_url,
        "is_pdf": is_pdf,
      }
    except Exception as exc:
      print(f"Warning: failed to fetch external file link '{file_id}': {exc}")

  return links


def format_benchling_entry_to_markdown(
  entry: dict[str, Any],
  output_path: Path,
  *,
  asset_paths: dict[str, Path] | None = None,
  external_file_links: dict[str, dict[str, Any]] | None = None,
) -> None:
  formatter_asset_paths: dict[str, str] = {}
  if asset_paths:
    for asset_id, asset_path in asset_paths.items():
      rel_path = Path(os.path.relpath(asset_path, output_path.parent)).as_posix()
      formatter_asset_paths[asset_id] = rel_path

  formatter = BenchlingFormatter(
    asset_paths=formatter_asset_paths,
    external_file_links=external_file_links,
  )
  markdown_output = formatter.format_entry(entry)

  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(markdown_output, encoding="utf-8")


def main() -> None:
  load_dotenv()

  parser = argparse.ArgumentParser(
    description=(
      "Fetch a Benchling entry by ID or display ID from the API and write markdown output."
    )
  )
  parser.add_argument(
    "--output",
    default="data/benchling_extracted.md",
    help="Path to output markdown file",
  )
  parser.add_argument(
    "--entry-id",
    required=True,
    help="Benchling entry ID (e.g., etr_xxx) or display ID (e.g., EXP23026996)",
  )
  parser.add_argument(
    "--benchling-url",
    default="https://biomarin.benchling.com/",
    help="Benchling tenant URL for API mode",
  )
  parser.add_argument(
    "--api-key-env",
    default="BENCHLING_API_KEY",
    help="Environment variable name containing Benchling API key",
  )
  parser.add_argument(
    "--download-external-files",
    action="store_true",
    help="Download external files referenced by the entry and link/embed them in markdown.",
  )
  parser.add_argument(
    "--assets-dir",
    default="",
    help=(
      "Directory for downloaded external files. "
      "Defaults to <output_stem>_assets next to the output markdown."
    ),
  )
  args = parser.parse_args()

  output_path = Path(args.output)
  api_key = os.getenv(args.api_key_env, "")
  entry = fetch_entry_by_identifier(
    args.entry_id,
    api_key=api_key,
    benchling_url=args.benchling_url,
  )

  external_file_links: dict[str, dict[str, Any]] | None = None
  try:
    external_file_links = fetch_external_file_links_for_entry(
      entry,
      api_key=api_key,
      benchling_url=args.benchling_url,
    )
  except Exception as exc:
    print(f"Warning: failed to fetch external file links: {exc}")

  asset_paths: dict[str, Path] | None = None
  if args.download_external_files:
    if args.assets_dir:
      assets_dir = Path(args.assets_dir)
    else:
      assets_dir = output_path.parent / f"{output_path.stem}_assets"
    asset_paths = download_external_files_for_entry(
      entry,
      api_key=api_key,
      benchling_url=args.benchling_url,
      output_dir=assets_dir,
    )

  format_benchling_entry_to_markdown(
    entry,
    output_path,
    asset_paths=asset_paths,
    external_file_links=external_file_links,
  )


if __name__ == "__main__":
  main()
