from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from google.adk.tools.skill_toolset import SkillToolset

from report_writing_collaborator.agent.agent import build_agent, make_workspace_tools

if TYPE_CHECKING:
    from pathlib import Path


def _make_workspace(root: Path) -> Path:
    (root / "normalized" / "src_a").mkdir(parents=True)
    (root / "normalized" / "src_a" / "document.md").write_text(
        "# Title\n\nBody mentions apples and oranges.\n", encoding="utf-8"
    )
    (root / "manifest.json").write_text('{"workspace_id": "ws_test"}\n', encoding="utf-8")
    (root / "assets" / "src_a" / "images").mkdir(parents=True)
    (root / "assets" / "src_a" / "images" / "pic.png").write_bytes(b"\x89PNG")
    return root


def test_glob_workspace_lists_matching_files(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    glob_workspace, _, _, _ = make_workspace_tools(workspace)

    result = glob_workspace("normalized/*/document.md")

    assert result["status"] == "success"
    assert result["paths"] == ["normalized/src_a/document.md"]


def test_glob_workspace_rejects_traversal_outside_root(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path / "workspace")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    glob_workspace, _, _, _ = make_workspace_tools(workspace)

    result = glob_workspace("../secret.txt")

    assert result["status"] == "success"
    assert result["paths"] == []


def test_grep_workspace_finds_matching_lines(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, grep_workspace, _, _ = make_workspace_tools(workspace)

    result = grep_workspace("apples", glob_pattern="**/*.md")

    assert result["status"] == "success"
    assert result["truncated"] is False
    assert len(result["matches"]) == 1
    assert result["matches"][0]["path"] == "normalized/src_a/document.md"
    assert "apples" in result["matches"][0]["line"]


def test_grep_workspace_reports_invalid_pattern(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, grep_workspace, _, _ = make_workspace_tools(workspace)

    result = grep_workspace("(unclosed")

    assert result["status"] == "error"
    assert "Invalid pattern" in result["error_message"]


def test_read_workspace_file_returns_content(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, _, read_workspace_file, _ = make_workspace_tools(workspace)

    result = read_workspace_file("manifest.json")

    assert result["status"] == "success"
    assert "ws_test" in result["content"]


def test_read_workspace_file_rejects_path_traversal(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path / "workspace")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    _, _, read_workspace_file, _ = make_workspace_tools(workspace)

    result = read_workspace_file("../secret.txt")

    assert result["status"] == "error"
    assert "escapes workspace" in result["error_message"]


def test_read_workspace_file_reports_missing_file(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, _, read_workspace_file, _ = make_workspace_tools(workspace)

    result = read_workspace_file("normalized/does-not-exist.md")

    assert result["status"] == "error"
    assert "Not a file" in result["error_message"]


def _fake_response(text: str) -> object:
    message = type("Message", (), {"content": text})()
    choice = type("Choice", (), {"message": message})()
    return type("Response", (), {"choices": [choice]})()


def test_inspect_image_returns_description(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REPORT_AGENT_VISION_MODEL", raising=False)
    workspace = _make_workspace(tmp_path)
    _, _, _, inspect_image = make_workspace_tools(
        workspace, agent_model="anthropic/claude-sonnet-5"
    )

    with patch(
        "report_writing_collaborator.agent.agent.litellm.completion",
        return_value=_fake_response("A line chart trending upward."),
    ) as completion:
        result = inspect_image("assets/src_a/images/pic.png", question="What trend is shown?")

    assert result == {
        "status": "success",
        "description": "A line chart trending upward.",
        "model": "anthropic/claude-sonnet-5",
    }
    sent_content = completion.call_args.kwargs["messages"][0]["content"]
    assert sent_content[0] == {"type": "text", "text": "What trend is shown?"}
    assert sent_content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_inspect_image_uses_default_question_when_omitted(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, _, _, inspect_image = make_workspace_tools(workspace)

    with patch(
        "report_writing_collaborator.agent.agent.litellm.completion",
        return_value=_fake_response("A generic description."),
    ) as completion:
        inspect_image("assets/src_a/images/pic.png")

    sent_text = completion.call_args.kwargs["messages"][0]["content"][0]["text"]
    assert "Describe this image" in sent_text


def test_inspect_image_rejects_path_traversal(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path / "workspace")
    (tmp_path / "secret.png").write_bytes(b"\x89PNG")
    _, _, _, inspect_image = make_workspace_tools(workspace)

    result = inspect_image("../secret.png")

    assert result["status"] == "error"
    assert "escapes workspace" in result["error_message"]


def test_inspect_image_reports_missing_file(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, _, _, inspect_image = make_workspace_tools(workspace)

    result = inspect_image("assets/src_a/images/does-not-exist.png")

    assert result["status"] == "error"
    assert "Not a file" in result["error_message"]


def test_inspect_image_rejects_unsupported_format(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    (workspace / "assets" / "src_a" / "images" / "scan.tiff").write_bytes(b"II*\x00")
    _, _, _, inspect_image = make_workspace_tools(workspace)

    result = inspect_image("assets/src_a/images/scan.tiff")

    assert result["status"] == "error"
    assert "Unsupported image format" in result["error_message"]


def test_inspect_image_reports_model_call_failure(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, _, _, inspect_image = make_workspace_tools(workspace)

    with patch(
        "report_writing_collaborator.agent.agent.litellm.completion",
        side_effect=RuntimeError("timed out"),
    ):
        result = inspect_image("assets/src_a/images/pic.png")

    assert result["status"] == "error"
    assert "Vision model call failed" in result["error_message"]


def test_inspect_image_prefers_vision_model_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPORT_AGENT_VISION_MODEL", "openai/gpt-4o")
    workspace = _make_workspace(tmp_path)
    _, _, _, inspect_image = make_workspace_tools(
        workspace, agent_model="anthropic/claude-sonnet-5"
    )

    with patch(
        "report_writing_collaborator.agent.agent.litellm.completion",
        return_value=_fake_response("described"),
    ) as completion:
        result = inspect_image("assets/src_a/images/pic.png")

    assert result["model"] == "openai/gpt-4o"
    assert completion.call_args.kwargs["model"] == "openai/gpt-4o"


def test_build_agent_constructs_without_llm_call(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)

    agent = build_agent(workspace, model="anthropic/claude-sonnet-5")

    assert agent.name == "report_writing_agent"
    assert len(agent.tools) == 5
    tool_names = {getattr(tool, "__name__", type(tool).__name__) for tool in agent.tools}
    assert tool_names == {
        "glob_workspace",
        "grep_workspace",
        "read_workspace_file",
        "inspect_image",
        "SkillToolset",
    }


def test_build_agent_selects_named_skills_only(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)

    agent = build_agent(workspace, skill_names=["workspace-summary"])

    skill_toolset = next(tool for tool in agent.tools if isinstance(tool, SkillToolset))
    assert [skill.frontmatter.name for skill in skill_toolset.skills] == ["workspace-summary"]


def test_build_agent_rejects_unknown_skill_name(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)

    with pytest.raises(KeyError):
        build_agent(workspace, skill_names=["does-not-exist"])
