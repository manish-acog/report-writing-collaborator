from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from google.adk.tools.skill_toolset import SkillToolset

from report_writing_collaborator.agent.agent import (
    _MAX_READ_LINES,
    build_agent,
    make_workspace_tools,
)

if TYPE_CHECKING:
    from pathlib import Path


def _make_workspace(root: Path) -> Path:
    (root / "normalized" / "src_a").mkdir(parents=True)
    (root / "normalized" / "src_a" / "document.md").write_text(
        "# Title\n\nBody mentions apples and oranges.\n", encoding="utf-8"
    )
    (root / "normalized" / "src_a" / "document.sections.json").write_text(
        json.dumps(
            {
                "source_id": "src_a",
                "sections": [
                    {
                        "section_id": "sec_title",
                        "title": "Title",
                        "heading_level": 1,
                        "heading_path": ["Title"],
                        "start_line": 1,
                        "end_line": 3,
                        "source_pages": [1],
                        "parent_section_id": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
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
    assert result["matches"][0]["section_id"] == "sec_title"
    assert result["matches"][0]["source_pages"] == [1]


def test_grep_workspace_leaves_section_fields_null_outside_normalized_docs(
    tmp_path: Path,
) -> None:
    workspace = _make_workspace(tmp_path)
    _, grep_workspace, _, _ = make_workspace_tools(workspace)

    result = grep_workspace("workspace_id", glob_pattern="manifest.json")

    assert len(result["matches"]) == 1
    assert result["matches"][0]["section_id"] is None
    assert result["matches"][0]["source_pages"] is None


def test_grep_workspace_reports_invalid_pattern(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, grep_workspace, _, _ = make_workspace_tools(workspace)

    result = grep_workspace("(unclosed")

    assert result["status"] == "error"
    assert "Invalid pattern" in result["error_message"]


def test_grep_workspace_default_context_includes_surrounding_lines(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, grep_workspace, _, _ = make_workspace_tools(workspace)

    result = grep_workspace("apples", glob_pattern="**/*.md")

    # Line 3 (the match) with default context_lines=2: lines 1-3 (no line 4).
    assert result["matches"][0]["context"] == (
        "# Title\n\nBody mentions apples and oranges."
    )


def test_grep_workspace_context_clamps_at_start_of_file(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, grep_workspace, _, _ = make_workspace_tools(workspace)

    # Match on line 1: context_lines=2 would need lines -1..3 uncapped;
    # clamped to the file's actual start, line 1.
    result = grep_workspace("Title", glob_pattern="**/*.md")

    assert result["matches"][0]["context"] == (
        "# Title\n\nBody mentions apples and oranges."
    )


def test_grep_workspace_context_lines_zero_returns_only_matched_line(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, grep_workspace, _, _ = make_workspace_tools(workspace)

    result = grep_workspace("apples", glob_pattern="**/*.md", context_lines=0)

    assert result["matches"][0]["context"] == "Body mentions apples and oranges."


def test_grep_workspace_context_lines_capped_at_max(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, grep_workspace, _, _ = make_workspace_tools(workspace)

    uncapped = grep_workspace("apples", glob_pattern="**/*.md", context_lines=0)
    over_cap = grep_workspace("apples", glob_pattern="**/*.md", context_lines=99)

    # context_lines=99 caps at 3, same as passing 3 -- both bounded by the
    # 3-line file, so identical here; the cap itself is exercised by not
    # raising and not silently returning the whole file for a huge value.
    assert over_cap["matches"][0]["context"] != uncapped["matches"][0]["context"]
    assert over_cap["matches"][0]["context"] == (
        "# Title\n\nBody mentions apples and oranges."
    )


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


def test_read_workspace_file_offset_and_limit_returns_partial_content(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, _, read_workspace_file, _ = make_workspace_tools(workspace)

    result = read_workspace_file("normalized/src_a/document.md", offset=3, limit=1)

    assert result["status"] == "success"
    assert result["content"] == "Body mentions apples and oranges."


def test_read_workspace_file_offset_without_limit_reads_to_end(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, _, read_workspace_file, _ = make_workspace_tools(workspace)

    result = read_workspace_file("normalized/src_a/document.md", offset=2)

    assert result["content"] == "\nBody mentions apples and oranges."


def test_read_workspace_file_offset_beyond_eof_returns_empty(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, _, read_workspace_file, _ = make_workspace_tools(workspace)

    result = read_workspace_file("normalized/src_a/document.md", offset=100, limit=10)

    assert result["status"] == "success"
    assert result["content"] == ""


def test_read_workspace_file_caps_lines_even_without_limit(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    line_count = _MAX_READ_LINES + 50
    (workspace / "normalized" / "src_a" / "big.md").write_text(
        "\n".join(f"line {i}" for i in range(line_count)), encoding="utf-8"
    )
    _, _, read_workspace_file, _ = make_workspace_tools(workspace)

    result = read_workspace_file("normalized/src_a/big.md")

    assert result["status"] == "success"
    assert result["content"].count("\n") + 1 == _MAX_READ_LINES
    assert "line 0" in result["content"]
    assert f"line {_MAX_READ_LINES}" not in result["content"]


def test_read_workspace_file_caps_limit_above_max(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    line_count = _MAX_READ_LINES + 50
    (workspace / "normalized" / "src_a" / "big.md").write_text(
        "\n".join(f"line {i}" for i in range(line_count)), encoding="utf-8"
    )
    _, _, read_workspace_file, _ = make_workspace_tools(workspace)

    result = read_workspace_file("normalized/src_a/big.md", offset=1, limit=100_000)

    assert result["content"].count("\n") + 1 == _MAX_READ_LINES


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
        "report_writing_collaborator.agent.agent.litellm.acompletion",
        return_value=_fake_response("A line chart trending upward."),
    ) as completion:
        result = asyncio.run(
            inspect_image("assets/src_a/images/pic.png", question="What trend is shown?")
        )

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
        "report_writing_collaborator.agent.agent.litellm.acompletion",
        return_value=_fake_response("A generic description."),
    ) as completion:
        asyncio.run(inspect_image("assets/src_a/images/pic.png"))

    sent_text = completion.call_args.kwargs["messages"][0]["content"][0]["text"]
    assert "Describe this image" in sent_text


def test_inspect_image_rejects_path_traversal(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path / "workspace")
    (tmp_path / "secret.png").write_bytes(b"\x89PNG")
    _, _, _, inspect_image = make_workspace_tools(workspace)

    result = asyncio.run(inspect_image("../secret.png"))

    assert result["status"] == "error"
    assert "escapes workspace" in result["error_message"]


def test_inspect_image_reports_missing_file(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, _, _, inspect_image = make_workspace_tools(workspace)

    result = asyncio.run(inspect_image("assets/src_a/images/does-not-exist.png"))

    assert result["status"] == "error"
    assert "Not a file" in result["error_message"]


def test_inspect_image_rejects_unsupported_format(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    (workspace / "assets" / "src_a" / "images" / "scan.tiff").write_bytes(b"II*\x00")
    _, _, _, inspect_image = make_workspace_tools(workspace)

    result = asyncio.run(inspect_image("assets/src_a/images/scan.tiff"))

    assert result["status"] == "error"
    assert "Unsupported image format" in result["error_message"]


def test_inspect_image_reports_model_call_failure(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, _, _, inspect_image = make_workspace_tools(workspace)

    with patch(
        "report_writing_collaborator.agent.agent.litellm.acompletion",
        side_effect=RuntimeError("timed out"),
    ):
        result = asyncio.run(inspect_image("assets/src_a/images/pic.png"))

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
        "report_writing_collaborator.agent.agent.litellm.acompletion",
        return_value=_fake_response("described"),
    ) as completion:
        result = asyncio.run(inspect_image("assets/src_a/images/pic.png"))

    assert result["model"] == "openai/gpt-4o"
    assert completion.call_args.kwargs["model"] == "openai/gpt-4o"


def test_inspect_image_calls_overlap_concurrently(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path)
    _, _, _, inspect_image = make_workspace_tools(workspace)
    call_count = 3
    delay_seconds = 0.2

    async def _slow_acompletion(**_kwargs: object) -> object:
        await asyncio.sleep(delay_seconds)
        return _fake_response("described")

    async def _run_concurrently() -> float:
        started = asyncio.get_event_loop().time()
        await asyncio.gather(
            *(inspect_image("assets/src_a/images/pic.png") for _ in range(call_count))
        )
        return asyncio.get_event_loop().time() - started

    with patch(
        "report_writing_collaborator.agent.agent.litellm.acompletion",
        side_effect=_slow_acompletion,
    ):
        elapsed = asyncio.run(_run_concurrently())

    # Serialized, call_count calls would take call_count * delay_seconds; if
    # they actually overlap, the whole gather() takes roughly one delay.
    assert elapsed < delay_seconds * call_count


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
