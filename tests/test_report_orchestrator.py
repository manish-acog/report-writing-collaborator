from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from report_writing_collaborator import build_output_schema, load_variables_config
from report_writing_collaborator.agent import report_orchestrator

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _make_skill_dir(root: Path, name: str, description: str, instructions: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{instructions}\n",
        encoding="utf-8",
    )
    return skill_dir


def _make_report_skill(skills_dir: Path) -> Path:
    skill_dir = _make_skill_dir(
        skills_dir,
        "general-report-writing",
        "Writes a structured report.",
        "Build structure first, then extract fields with citations.",
    )
    (skill_dir / "variables.json").write_text(
        json.dumps(
            {
                "call_groups": [
                    {
                        "name": "report_fields",
                        "variables": [
                            {"name": "title", "variable_type": "text", "description": "Title."},
                            {
                                "name": "conclusion",
                                "variable_type": "text",
                                "description": "Conclusion.",
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    templates_dir = skill_dir / "templates"
    templates_dir.mkdir()
    (templates_dir / "report.md").write_text(
        "# {{title}}\n\n{{conclusion}}\n\n{{references}}\n", encoding="utf-8"
    )
    return skill_dir


def _make_workspace(root: Path) -> Path:
    (root / "normalized" / "src_a").mkdir(parents=True)
    (root / "sources" / "src_a").mkdir(parents=True)
    (root / "normalized" / "src_a" / "document.md").write_text("# Title\n", encoding="utf-8")
    (root / "normalized" / "src_a" / "document.sections.json").write_text(
        '{"source_id": "src_a", "sections": []}\n',
        encoding="utf-8",
    )
    (root / "sources" / "src_a" / "original.pdf").write_bytes(b"source")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "workspace_id": "ws_test",
                "sources": [
                    {
                        "source_id": "src_a",
                        "source_role": "protocol",
                        "original_filename": "Protocol.pdf",
                        "original_path": "sources/src_a/original.pdf",
                        "normalized_path": "normalized/src_a/document.md",
                        "sections_path": "normalized/src_a/document.sections.json",
                        "parent_source_id": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return root


def test_build_bounded_agent_has_schema_and_shared_skills(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path / "workspace")
    skills_dir = tmp_path / "skills"
    structure_skill = load_skill_from_dir(
        _make_skill_dir(skills_dir, "workspace-summary", "Summarizes.", "Build structure.")
    )
    grounding_skill = load_skill_from_dir(
        _make_skill_dir(skills_dir, "evidence-grounding", "Cites.", "Ground every claim.")
    )
    config = load_variables_config(_make_report_skill(skills_dir) / "variables.json")
    schema = build_output_schema(config.call_groups[0])

    agent = report_orchestrator._build_bounded_agent(
        workspace,
        "anthropic/claude-sonnet-5",
        schema,
        "do the extraction",
        [structure_skill, grounding_skill],
    )

    assert agent.output_schema is schema
    assert agent.output_key == "result"
    tool_names = {getattr(tool, "__name__", type(tool).__name__) for tool in agent.tools}
    assert tool_names == {
        "glob_workspace",
        "grep_workspace",
        "read_workspace_file",
        "inspect_image",
        "SkillToolset",
    }
    skill_toolset = next(tool for tool in agent.tools if isinstance(tool, SkillToolset))
    assert [skill.frontmatter.name for skill in skill_toolset.skills] == [
        "workspace-summary",
        "evidence-grounding",
    ]


def test_build_instruction_combines_skill_body_and_field_list(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skill = load_skill_from_dir(_make_report_skill(skills_dir))
    config = load_variables_config(skills_dir / "general-report-writing" / "variables.json")

    instruction = report_orchestrator._build_instruction(skill, config.call_groups[0])

    assert "Build structure first" in instruction
    assert "**title**: Title." in instruction
    assert "**conclusion**: Conclusion." in instruction


def test_general_report_skill_loads_shared_grounding_rules() -> None:
    general_skill = load_skill_from_dir(report_orchestrator.SKILLS_DIR / "general-report-writing")
    grounding_skill = load_skill_from_dir(report_orchestrator.SKILLS_DIR / "evidence-grounding")
    grounding_text = " ".join(grounding_skill.instructions.split())
    assert "`evidence-grounding`" in general_skill.instructions
    assert "`[[cite:N]]`" not in general_skill.instructions
    assert "`[[cite:N]]`" in grounding_text
    assert "more than one citation" in grounding_text
    assert "one `Citation` per page" in grounding_text


def test_write_report_merges_call_groups_and_renders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skills_dir = tmp_path / "skills"
    _make_skill_dir(skills_dir, "workspace-summary", "Summarizes.", "Build structure.")
    _make_skill_dir(skills_dir, "evidence-grounding", "Cites.", "Ground every claim.")
    _make_report_skill(skills_dir)
    workspace = _make_workspace(tmp_path / "workspace")
    monkeypatch.setattr(report_orchestrator, "SKILLS_DIR", skills_dir)

    with patch.object(
        report_orchestrator,
        "_run_bounded_call",
        return_value={
            "title": {
                "status": "found",
                "value": "My Report[[cite:0]]",
                "citations": [{"source_id": "src_a", "page": 1}],
            },
            "conclusion": {"status": "not_found"},
        },
    ) as run_call:
        result = report_orchestrator.write_report(workspace, model="anthropic/claude-sonnet-5")

    assert run_call.call_count == 1
    assert '# My Report<sup><a href="#ref-1">1</a></sup>' in result
    assert "Not addressed in the available evidence." in result
    assert "[Protocol.pdf](sources/src_a/original.pdf#page=1) (protocol), page 1" in result
