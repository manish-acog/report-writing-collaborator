"""ADK wiring for the report-writing agent.

Reads a published, read-only document workspace (built by
report_writing_collaborator.WorkspaceBuilder) through four plain-function
tools, guided by whatever skill(s) are registered. See
agent_execution_over_adk.md and inspect_image.md for the design this
implements.
"""

from __future__ import annotations

import base64
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
    from collections.abc import Callable

SKILLS_DIR = Path(__file__).parent / "skills"
DEFAULT_MODEL = "anthropic/claude-sonnet-5"
_MAX_GREP_MATCHES = 200
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
    "You help produce evidence-grounded output from a published, read-only "
    "document workspace. Use glob_workspace and grep_workspace to find "
    "relevant content, and read_workspace_file to pull exact text before "
    "making any claim. Use inspect_image to ask a vision model about a "
    "chart, figure, or scanned page. Load a skill with load_skill and "
    "follow its instructions exactly."
)


def _within_root(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    return resolved == root or root in resolved.parents


def make_workspace_tools(
    workspace_root: Path,
    agent_model: str = DEFAULT_MODEL,
) -> list[Callable[..., dict]]:
    """Builds glob/grep/read/inspect tools bound to one read-only workspace.

    All four tools are confined to workspace_root: matches or reads that
    would resolve outside it (e.g. via a ".." segment) are rejected or
    silently excluded rather than followed.

    Args:
        workspace_root: The published workspace directory to read from.
        agent_model: The LiteLLM model string inspect_image falls back to
            when REPORT_AGENT_VISION_MODEL is unset.
    """
    workspace_root = workspace_root.resolve()
    vision_model = os.environ.get(_VISION_MODEL_ENV_VAR) or agent_model

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

    def grep_workspace(pattern: str, glob_pattern: str = "**/*") -> dict:
        """Searches workspace text files for a regular expression.

        Args:
            pattern: A Python regular expression to search for.
            glob_pattern: Restrict the search to files matching this glob
                (default: every file), e.g. "**/*.md" for normalized
                Markdown only.

        Returns:
            A dict with "status" and "matches" (each a dict with "path",
            "line_number", "line"), capped at 200 matches, plus
            "truncated". On an invalid pattern, "status" is "error" and
            "error_message" explains why.
        """
        try:
            compiled = re.compile(pattern)
        except re.error as error:
            return {"status": "error", "error_message": f"Invalid pattern: {error}"}

        matches: list[dict] = []
        for path in sorted(workspace_root.glob(glob_pattern)):
            if not path.is_file() or not _within_root(path, workspace_root):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            relative = path.relative_to(workspace_root).as_posix()
            for line_number, line in enumerate(text.splitlines(), start=1):
                if compiled.search(line):
                    matches.append({"path": relative, "line_number": line_number, "line": line})
                    if len(matches) >= _MAX_GREP_MATCHES:
                        return {"status": "success", "matches": matches, "truncated": True}

        return {"status": "success", "matches": matches, "truncated": False}

    def read_workspace_file(path: str) -> dict:
        """Reads the full text content of one workspace file.

        Args:
            path: A workspace-relative file path, e.g. "manifest.json" or
                "normalized/src_.../document.md".

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

        return {"status": "success", "content": content}

    def inspect_image(path: str, question: str | None = None) -> dict:
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
            response = litellm.completion(
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
            "Reads a published document workspace and produces evidence-grounded "
            "output guided by a skill."
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
