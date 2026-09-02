"""ADK wiring for the report-writing agent.

Reads a published, read-only document workspace (built by
report_writing_collaborator.WorkspaceBuilder) through four plain-function
tools, guided by whatever skill(s) are registered. grep_workspace gives
matches surrounding context plus section_id/source_pages, resolved from
the matched line; read_workspace_file's offset/limit widens a
confirmed-relevant spot without a second tool. No bespoke
fetch-by-structural-unit tool -- document.sections.json stays a plain,
directly-readable artifact for the rare genuine structural-discovery
need. See agent_execution_over_adk.md, inspect_image.md, and
docs/workspace_search_tools.md for the design this implements.
"""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

import litellm
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

SKILLS_DIR = Path(__file__).parent / "skills"
DEFAULT_MODEL = "anthropic/claude-sonnet-5"
_MAX_GREP_MATCHES = 200
_DEFAULT_CONTEXT_LINES = 2
_MAX_CONTEXT_LINES = 3
_NORMALIZED_DIR_NAME = "normalized"
_NORMALIZED_DOC_NAME = "document.md"
_SECTIONS_FILE_NAME = "document.sections.json"
_VISION_MODEL_ENV_VAR = "REPORT_AGENT_VISION_MODEL"
_VISION_TIMEOUT_SECONDS = 60
_DEFAULT_IMAGE_QUESTION = "Describe this image, including any text, data, or diagrams it contains."
# Vision APIs (Anthropic, OpenAI, Azure OpenAI) accept a narrower set of
# image formats than assets carry in general; unlike ElnNormalizer's broader
# asset-detection list, this is what's safe to actually send to a model.
_VISION_IMAGE_TYPES = {
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".gif": "gif",
    ".webp": "webp",
}
_AGENT_INSTRUCTION = (
    "You help produce evidence-grounded output from the provided documents. "
    "Use glob_workspace and grep_workspace to find "
    "relevant content, and read_workspace_file to pull exact text before "
    "making any claim. Use inspect_image to ask a vision model about a "
    "chart, figure, or scanned page. Load a skill with load_skill and "
    "follow its instructions exactly."
)


def _within_root(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    return resolved == root or root in resolved.parents


def _source_id_for_normalized_doc(relative_path: str) -> str | None:
    """Extracts source_id from "normalized/<source_id>/document.md", else None."""
    parts = relative_path.split("/")
    if len(parts) == 3 and parts[0] == _NORMALIZED_DIR_NAME and parts[2] == _NORMALIZED_DOC_NAME:
        return parts[1]
    return None


def make_workspace_tools(
    workspace_root: Path,
    agent_model: str = DEFAULT_MODEL,
) -> list[Callable[..., dict | Awaitable[dict]]]:
    """Builds glob/grep/read/inspect tools bound to one read-only workspace.

    All four tools are confined to workspace_root: matches or reads that
    would resolve outside it (e.g. via a ".." segment) are rejected or
    silently excluded rather than followed. inspect_image is the only
    async tool -- it awaits the vision model call so concurrent
    inspect_image calls overlap instead of blocking the event loop in
    series; ADK detects the coroutine automatically at call time.

    Args:
        workspace_root: The published workspace directory to read from.
        agent_model: The LiteLLM model string inspect_image falls back to
            when REPORT_AGENT_VISION_MODEL is unset.
    """
    workspace_root = workspace_root.resolve()
    vision_model = os.environ.get(_VISION_MODEL_ENV_VAR) or agent_model
    sections_cache: dict[str, list[dict] | None] = {}

    def _sections_for_source(source_id: str) -> list[dict] | None:
        """Loads and caches one source's document.sections.json, by source_id."""
        if source_id in sections_cache:
            return sections_cache[source_id]

        sections_path = workspace_root / _NORMALIZED_DIR_NAME / source_id / _SECTIONS_FILE_NAME
        sections: list[dict] | None = None
        if _within_root(sections_path, workspace_root) and sections_path.is_file():
            try:
                index = json.loads(sections_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                index = None
            candidate = index.get("sections") if isinstance(index, dict) else None
            sections = candidate if isinstance(candidate, list) else None

        sections_cache[source_id] = sections
        return sections

    def _section_at_line(source_id: str, line_number: int) -> dict | None:
        for section in _sections_for_source(source_id) or []:
            if section["start_line"] <= line_number <= section["end_line"]:
                return section
        return None

    def glob_workspace(pattern: str) -> dict:
        """Lists workspace files matching a glob pattern.

        Args:
            pattern: A glob pattern relative to the workspace root, e.g.
                "normalized/*/document.md" or "**/*.png".

        Returns:
            A dict with "status" and "paths" (sorted, workspace-relative).
        """
        paths = sorted(
            path.relative_to(workspace_root).as_posix()
            for path in workspace_root.glob(pattern)
            if path.is_file() and _within_root(path, workspace_root)
        )
        return {"status": "success", "paths": paths}

    def grep_workspace(
        pattern: str,
        glob_pattern: str = "**/*",
        context_lines: int = _DEFAULT_CONTEXT_LINES,
    ) -> dict:
        """Searches workspace text files for a regular expression.

        Args:
            pattern: A Python regular expression to search for.
            glob_pattern: Restrict the search to files matching this glob
                (default: every file), e.g. "**/*.md" for normalized
                Markdown only.
            context_lines: Lines of surrounding context before and after
                each match (default 2, capped at 3). For pulling more than
                that around a confirmed-relevant spot, use
                read_workspace_file's offset/limit instead -- this is for
                cheap context across many matches, not a second way to
                read a large chunk.

        Returns:
            A dict with "status" and "matches" (each a dict with "path",
            "line_number", "line", "context" -- context_lines before
            through context_lines after the matched line, joined by
            newlines -- "section_id", "source_pages" -- the latter two
            are null when the match isn't inside a normalized document
            with a section index, e.g. manifest.json), capped at 200
            matches, plus "truncated". On an invalid pattern, "status" is
            "error" and "error_message" explains why.
        """
        try:
            compiled = re.compile(pattern)
        except re.error as error:
            return {"status": "error", "error_message": f"Invalid pattern: {error}"}

        context_lines = max(0, min(context_lines, _MAX_CONTEXT_LINES))

        matches: list[dict] = []
        for path in sorted(workspace_root.glob(glob_pattern)):
            if not path.is_file() or not _within_root(path, workspace_root):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            relative = path.relative_to(workspace_root).as_posix()
            source_id = _source_id_for_normalized_doc(relative)
            lines = text.splitlines()
            for index, line in enumerate(lines):
                if not compiled.search(line):
                    continue
                line_number = index + 1
                section = _section_at_line(source_id, line_number) if source_id else None
                context_start = max(index - context_lines, 0)
                context_end = min(index + context_lines + 1, len(lines))
                matches.append({
                    "path": relative,
                    "line_number": line_number,
                    "line": line,
                    "context": "\n".join(lines[context_start:context_end]),
                    "section_id": section["section_id"] if section else None,
                    "source_pages": section["source_pages"] if section else None,
                })
                if len(matches) >= _MAX_GREP_MATCHES:
                    return {"status": "success", "matches": matches, "truncated": True}

        return {"status": "success", "matches": matches, "truncated": False}

    def read_workspace_file(path: str, offset: int | None = None, limit: int | None = None) -> dict:
        """Reads the text content of one workspace file, in full or by line range.

        Args:
            path: A workspace-relative file path, e.g. "manifest.json" or
                "normalized/src_.../document.md".
            offset: 1-indexed starting line. Omitted with limit also
                omitted: the whole file, unchanged from a plain read.
            limit: Number of lines to return from offset. Omitted: to the
                end of the file. Widen progressively (a bigger limit, or
                an earlier offset) against an already-known location
                rather than re-searching.

        Returns:
            A dict with "status" and "content", or "status": "error" and
            "error_message" if the path escapes the workspace, is missing,
            or isn't text.
        """
        resolved = (workspace_root / path).resolve()
        if not _within_root(resolved, workspace_root):
            return {"status": "error", "error_message": f"Path escapes workspace: {path}"}
        if not resolved.is_file():
            return {"status": "error", "error_message": f"Not a file: {path}"}
        try:
            content = resolved.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as error:
            return {"status": "error", "error_message": f"Cannot read {path}: {error}"}

        if offset is not None or limit is not None:
            lines = content.splitlines()
            start = max((offset or 1) - 1, 0)
            end = len(lines) if limit is None else start + limit
            content = "\n".join(lines[start:end])

        return {"status": "success", "content": content}

    async def inspect_image(path: str, question: str | None = None) -> dict:
        """Asks a vision-capable model about one workspace image asset.

        Args:
            path: A workspace-relative image path, e.g.
                "assets/src_x/fig2.png".
            question: What to ask about the image. Defaults to a neutral
                description when omitted.

        Returns:
            A dict with "status", "description", and "model" on success, or
            "status": "error" and "error_message" if the path escapes the
            workspace, is missing, has an unsupported format, or the model
            call fails.
        """
        resolved = (workspace_root / path).resolve()
        if not _within_root(resolved, workspace_root):
            return {"status": "error", "error_message": f"Path escapes workspace: {path}"}
        if not resolved.is_file():
            return {"status": "error", "error_message": f"Not a file: {path}"}

        image_type = _VISION_IMAGE_TYPES.get(resolved.suffix.lower())
        if image_type is None:
            supported = ", ".join(sorted(_VISION_IMAGE_TYPES))
            return {
                "status": "error",
                "error_message": (
                    f"Unsupported image format '{resolved.suffix}'; expected: {supported}"
                ),
            }

        try:
            encoded = base64.b64encode(resolved.read_bytes()).decode("ascii")
        except OSError as error:
            return {"status": "error", "error_message": f"Cannot read {path}: {error}"}

        try:
            response = await litellm.acompletion(
                model=vision_model,
                timeout=_VISION_TIMEOUT_SECONDS,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": question or _DEFAULT_IMAGE_QUESTION},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/{image_type};base64,{encoded}"},
                            },
                        ],
                    }
                ],
            )
        except Exception as error:
            return {"status": "error", "error_message": f"Vision model call failed: {error}"}

        return {
            "status": "success",
            "description": response.choices[0].message.content,
            "model": vision_model,
        }

    return [glob_workspace, grep_workspace, read_workspace_file, inspect_image]


def build_agent(
    workspace_root: Path,
    skill_names: list[str] | None = None,
    model: str | None = None,
) -> LlmAgent:
    """Builds one LlmAgent scoped to a single published workspace.

    Args:
        workspace_root: The published <workspace_id>/<workspace_version>/
            directory to read from.
        skill_names: Names of skill directories under skills/ to register.
            Defaults to every skill found there.
        model: A LiteLLM model string. Defaults to the REPORT_AGENT_MODEL
            environment variable, falling back to Claude Sonnet.

    Returns:
        A configured LlmAgent, not yet run.
    """
    available = sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir())
    if skill_names is None:
        selected = available
    else:
        by_name = {path.name: path for path in available}
        selected = [by_name[name] for name in skill_names]

    model = model or os.environ.get("REPORT_AGENT_MODEL", DEFAULT_MODEL)
    skills = [load_skill_from_dir(skill_dir) for skill_dir in selected]
    tools: list[object] = [
        *make_workspace_tools(workspace_root, agent_model=model),
        SkillToolset(skills=skills),
    ]

    return LlmAgent(
        model=LiteLlm(model=model),
        name="report_writing_agent",
        description=(
            "Reads the provided documents and produces evidence-grounded output guided by a skill."
        ),
        instruction=_AGENT_INSTRUCTION,
        tools=tools,
    )


def _demo_workspace_root() -> Path:
    configured = os.environ.get("WORKSPACE_ROOT")
    if not configured:
        raise RuntimeError(
            "Set WORKSPACE_ROOT to a published <workspace_id>/<workspace_version>/ "
            "directory before running this agent (see .env.example)."
        )
    return Path(configured)


root_agent = build_agent(_demo_workspace_root())
