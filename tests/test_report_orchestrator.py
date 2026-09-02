from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from report_writing_collaborator import build_output_schema, load_variables_config
from report_writing_collaborator.agent import report_orchestrator

if TYPE_CHECKING:
    from pathlib import Path


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


def test_build_bounded_agent_has_schema_and_grounding_skill(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path / "workspace")
    skills_dir = tmp_path / "skills"
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
        grounding_skill,
    )

    assert agent.output_schema is schema
    assert agent.output_key == "result"
    tool_names = {getattr(tool, "__name__", type(tool).__name__) for tool in agent.tools}
    assert tool_names == {
        "glob_workspace",
        "grep_workspace",
        "read_workspace_file",
        "inspect_image",
        "list_sections",
        "read_section",
        "SkillToolset",
    }
    skill_toolset = next(tool for tool in agent.tools if isinstance(tool, SkillToolset))
    assert [skill.frontmatter.name for skill in skill_toolset.skills] == ["evidence-grounding"]


def test_build_bootstrap_agent_has_no_schema_and_structure_skill(tmp_path: Path) -> None:
    workspace = _make_workspace(tmp_path / "workspace")
    skills_dir = tmp_path / "skills"
    structure_skill = load_skill_from_dir(
        _make_skill_dir(skills_dir, "workspace-summary", "Summarizes.", "Build structure.")
    )

    agent = report_orchestrator._build_bootstrap_agent(
        workspace, "anthropic/claude-sonnet-5", structure_skill
    )

    assert agent.output_schema is None
    tool_names = {getattr(tool, "__name__", type(tool).__name__) for tool in agent.tools}
    assert tool_names == {
        "glob_workspace",
        "grep_workspace",
        "read_workspace_file",
        "inspect_image",
        "list_sections",
        "read_section",
        "SkillToolset",
    }
    skill_toolset = next(tool for tool in agent.tools if isinstance(tool, SkillToolset))
    assert [skill.frontmatter.name for skill in skill_toolset.skills] == ["workspace-summary"]


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


def test_academic_report_skill_loads_shared_skills_and_imrad_fields() -> None:
    academic_skill = load_skill_from_dir(report_orchestrator.SKILLS_DIR / "academic-report")
    config = load_variables_config(
        report_orchestrator.SKILLS_DIR / "academic-report" / "variables.json"
    )

    assert "`workspace-summary`" in academic_skill.instructions
    assert "`evidence-grounding`" in academic_skill.instructions
    assert "results" in academic_skill.instructions.lower()
    assert "discussion" in academic_skill.instructions.lower()
    assert len(config.call_groups) == 1
    field_names = [variable.name for variable in config.call_groups[0].variables]
    assert field_names == [
        "title",
        "abstract",
        "introduction",
        "methods",
        "results",
        "discussion",
        "conclusion",
    ]
    build_output_schema(config.call_groups[0])


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

    assert run_call.call_count == 2
    assert '# My Report<sup><a href="#ref-1">1</a></sup>' in result.text
    assert "Not addressed in the available evidence." in result.text
    assert "[Protocol.pdf](sources/src_a/original.pdf#page=1) (protocol), page 1" in result.text

    assert result.task_dir == workspace.parent / ".tasks" / result.task_id
    assert (result.task_dir / "sessions.db").exists()
    assert result.report_path == result.task_dir / "report.md"
    assert result.report_path.read_text(encoding="utf-8") == result.text

    task = json.loads((result.task_dir / "task.json").read_text(encoding="utf-8"))
    assert task["skill_name"] == "general-report-writing"
    assert task["template_name"] == "report.md"
    assert task["model"] == "anthropic/claude-sonnet-5"
    assert task["started_at"] <= task["completed_at"]

    values = json.loads((result.task_dir / "values.json").read_text(encoding="utf-8"))
    assert values == {
        "title": {
            "status": "found",
            "value": "My Report[[cite:0]]",
            "citations": [{"source_id": "src_a", "page": 1}],
        },
        "conclusion": {"status": "not_found"},
    }

    usage = json.loads((result.task_dir / "usage.json").read_text(encoding="utf-8"))
    assert usage == {
        "event_count": 0,
        "tool_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cached_tokens": 0,
        "total_tokens": 0,
    }

    # workspace_root itself stays untouched -- every artifact lands in .tasks/.
    assert not (workspace / "sessions.db").exists()
    assert not (workspace / "report.md").exists()


def test_write_report_persists_partial_values_before_a_later_group_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skills_dir = tmp_path / "skills"
    _make_skill_dir(skills_dir, "workspace-summary", "Summarizes.", "Build structure.")
    _make_skill_dir(skills_dir, "evidence-grounding", "Cites.", "Ground every claim.")
    skill_dir = _make_skill_dir(
        skills_dir, "multi-group-report", "Writes a report.", "Extract fields."
    )
    (skill_dir / "variables.json").write_text(
        json.dumps(
            {
                "call_groups": [
                    {
                        "name": "g1",
                        "variables": [
                            {"name": "title", "variable_type": "text", "description": "Title."}
                        ],
                    },
                    {
                        "name": "g2",
                        "variables": [
                            {
                                "name": "conclusion",
                                "variable_type": "text",
                                "description": "Conclusion.",
                            }
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (skill_dir / "templates").mkdir()
    (skill_dir / "templates" / "report.md").write_text(
        "# {{title}}\n\n{{conclusion}}\n\n{{references}}\n", encoding="utf-8"
    )
    workspace = _make_workspace(tmp_path / "workspace")
    monkeypatch.setattr(report_orchestrator, "SKILLS_DIR", skills_dir)

    responses: list[dict | Exception] = [
        {},  # bootstrap turn (expect_output=False; return value is discarded)
        {
            "title": {
                "status": "found",
                "value": "My Report[[cite:0]]",
                "citations": [{"source_id": "src_a", "page": 1}],
            }
        },
        RuntimeError("second group failed"),
    ]

    def fake_run_bounded_call(*args: object, **kwargs: object) -> dict:
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    with (
        patch.object(
            report_orchestrator, "_build_session", wraps=report_orchestrator._build_session
        ) as build_session,
        patch.object(report_orchestrator, "_run_bounded_call", side_effect=fake_run_bounded_call),
        pytest.raises(RuntimeError, match="second group failed"),
    ):
        report_orchestrator.write_report(workspace, skill_name="multi-group-report")

    task_dir = build_session.call_args.args[0]
    values = json.loads((task_dir / "values.json").read_text(encoding="utf-8"))
    assert values == {
        "title": {
            "status": "found",
            "value": "My Report[[cite:0]]",
            "citations": [{"source_id": "src_a", "page": 1}],
        }
    }



def test_summarize_usage_sums_tokens_and_counts_tool_calls(tmp_path: Path) -> None:
    from google.adk.events.event import Event
    from google.genai import types as genai_types

    workspace = _make_workspace(tmp_path / "workspace")
    session_service, session_id = report_orchestrator._build_session(workspace)

    async def _append_events() -> None:
        text_session = await session_service.get_session(
            app_name=report_orchestrator._RUNNER_APP_NAME,
            user_id=report_orchestrator._RUNNER_USER_ID,
            session_id=session_id,
        )
        text_event = Event(
            author="agent",
            content=genai_types.Content(role="model", parts=[genai_types.Part(text="hi")]),
            usage_metadata=genai_types.GenerateContentResponseUsageMetadata(
                prompt_token_count=10,
                candidates_token_count=5,
                cached_content_token_count=2,
                total_token_count=15,
            ),
        )
        await session_service.append_event(text_session, text_event)

        call_session = await session_service.get_session(
            app_name=report_orchestrator._RUNNER_APP_NAME,
            user_id=report_orchestrator._RUNNER_USER_ID,
            session_id=session_id,
        )
        call_event = Event(
            author="agent",
            content=genai_types.Content(
                role="model",
                parts=[
                    genai_types.Part(
                        function_call=genai_types.FunctionCall(name="glob_workspace", args={})
                    )
                ],
            ),
            usage_metadata=genai_types.GenerateContentResponseUsageMetadata(
                prompt_token_count=20,
                candidates_token_count=8,
                cached_content_token_count=0,
                total_token_count=28,
            ),
        )
        await session_service.append_event(call_session, call_event)

    asyncio.run(_append_events())

    usage = asyncio.run(report_orchestrator._summarize_usage(session_service, session_id))
    asyncio.run(session_service.close())

    assert usage == {
        "event_count": 2,
        "tool_calls": 1,
        "prompt_tokens": 30,
        "completion_tokens": 13,
        "cached_tokens": 2,
        "total_tokens": 43,
    }

def test_rerender_task_reproduces_or_reformats_without_a_model_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skills_dir = tmp_path / "skills"
    _make_skill_dir(skills_dir, "workspace-summary", "Summarizes.", "Build structure.")
    _make_skill_dir(skills_dir, "evidence-grounding", "Cites.", "Ground every claim.")
    skill_dir = _make_report_skill(skills_dir)
    (skill_dir / "templates" / "report.html").write_text(
        "<h1>{{title}}</h1>{{conclusion}}{{references}}", encoding="utf-8"
    )
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
    ):
        first = report_orchestrator.write_report(workspace, model="anthropic/claude-sonnet-5")

    # No mock active here: a stray model call would fail loudly, not pass silently.
    same_format = report_orchestrator.rerender_task(first.task_dir, workspace)
    assert same_format.text == first.text
    assert same_format.task_dir == first.task_dir
    assert same_format.task_id == first.task_id

    second_format = report_orchestrator.rerender_task(
        first.task_dir, workspace, template_name="report.html"
    )
    assert second_format.report_path == first.task_dir / "report.html"
    assert second_format.report_path.read_text(encoding="utf-8") == second_format.text
    assert '<h1>My Report<sup><a href="#ref-1">1</a></sup></h1>' in second_format.text
    assert "Not addressed in the available evidence." in second_format.text


def test_build_session_creates_independent_rows_across_reruns(tmp_path: Path) -> None:
    from google.adk.events.event import Event
    from google.genai import types as genai_types

    workspace = _make_workspace(tmp_path / "workspace")

    service_a, session_id_a = report_orchestrator._build_session(workspace)
    service_b, session_id_b = report_orchestrator._build_session(workspace)

    assert session_id_a != session_id_b
    assert (workspace / "sessions.db").exists()

    async def _append(service, session_id, count):
        session = await service.get_session(
            app_name=report_orchestrator._RUNNER_APP_NAME,
            user_id=report_orchestrator._RUNNER_USER_ID,
            session_id=session_id,
        )
        for _ in range(count):
            event = Event(
                author="user",
                content=genai_types.Content(role="user", parts=[genai_types.Part(text="hi")]),
            )
            await service.append_event(session, event)

    async def _load(service, session_id):
        return await service.get_session(
            app_name=report_orchestrator._RUNNER_APP_NAME,
            user_id=report_orchestrator._RUNNER_USER_ID,
            session_id=session_id,
        )

    asyncio.run(_append(service_a, session_id_a, 2))
    asyncio.run(_append(service_b, session_id_b, 1))
    final_a = asyncio.run(_load(service_a, session_id_a))
    final_b = asyncio.run(_load(service_b, session_id_b))
    asyncio.run(service_a.close())
    asyncio.run(service_b.close())

    assert len(final_a.events) == 2
    assert len(final_b.events) == 1


def test_run_bounded_call_retries_once_on_validation_error_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from google.adk.events.event import Event
    from google.adk.events.event_actions import EventActions
    from pydantic import ValidationError

    skills_dir = tmp_path / "skills"
    grounding_skill = load_skill_from_dir(
        _make_skill_dir(skills_dir, "evidence-grounding", "Cites.", "Ground every claim.")
    )
    config = load_variables_config(_make_report_skill(skills_dir) / "variables.json")
    schema = build_output_schema(config.call_groups[0])
    try:
        schema.model_validate_json(
            json.dumps(
                {
                    "title": {
                        "status": "found",
                        "value": "Claim[[cite:1]].",
                        "citations": [{"source_id": "src_a"}],
                    },
                    "conclusion": {"status": "not_found"},
                }
            )
        )
        pytest.fail("expected a ValidationError")
    except ValidationError as caught:
        validation_error = caught

    workspace = _make_workspace(tmp_path / "workspace")
    agent = report_orchestrator._build_bounded_agent(
        workspace, "anthropic/claude-sonnet-5", schema, "do the extraction", grounding_skill
    )
    session_service, session_id = report_orchestrator._build_session(workspace)
    prompts: list[str] = []

    class _FakeRunner:
        def __init__(self, *, agent, app_name, session_service) -> None:
            self._session_service = session_service

        async def run_async(self, *, user_id, session_id, new_message, run_config=None):
            prompts.append(new_message.parts[0].text)
            if len(prompts) == 1:
                raise validation_error
            session = await self._session_service.get_session(
                app_name=report_orchestrator._RUNNER_APP_NAME,
                user_id=report_orchestrator._RUNNER_USER_ID,
                session_id=session_id,
            )
            event = Event(
                author="agent",
                actions=EventActions(state_delta={report_orchestrator._OUTPUT_KEY: {"ok": True}}),
            )
            await self._session_service.append_event(session, event)
            return
            yield

    monkeypatch.setattr(report_orchestrator, "Runner", _FakeRunner)

    result = report_orchestrator._run_bounded_call(
        agent, session_service, session_id, "Extract the fields."
    )

    assert result == {"ok": True}
    assert len(prompts) == 2
    assert prompts[0] == "Extract the fields."
    assert "out of range for field 'title'" in prompts[1]


def test_run_bounded_call_raises_after_retries_exhausted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pydantic import ValidationError

    skills_dir = tmp_path / "skills"
    grounding_skill = load_skill_from_dir(
        _make_skill_dir(skills_dir, "evidence-grounding", "Cites.", "Ground every claim.")
    )
    config = load_variables_config(_make_report_skill(skills_dir) / "variables.json")
    schema = build_output_schema(config.call_groups[0])
    try:
        schema.model_validate_json(
            json.dumps(
                {
                    "title": {
                        "status": "found",
                        "value": "Claim[[cite:1]].",
                        "citations": [{"source_id": "src_a"}],
                    },
                    "conclusion": {"status": "not_found"},
                }
            )
        )
        pytest.fail("expected a ValidationError")
    except ValidationError as caught:
        validation_error = caught

    workspace = _make_workspace(tmp_path / "workspace")
    agent = report_orchestrator._build_bounded_agent(
        workspace, "anthropic/claude-sonnet-5", schema, "do the extraction", grounding_skill
    )
    session_service, session_id = report_orchestrator._build_session(workspace)
    prompts: list[str] = []

    class _AlwaysInvalidRunner:
        def __init__(self, *, agent, app_name, session_service) -> None:
            pass

        async def run_async(self, *, user_id, session_id, new_message, run_config=None):
            prompts.append(new_message.parts[0].text)
            raise validation_error
            yield

    monkeypatch.setattr(report_orchestrator, "Runner", _AlwaysInvalidRunner)

    with pytest.raises(RuntimeError, match="failed schema validation after 2 attempts"):
        report_orchestrator._run_bounded_call(
            agent, session_service, session_id, "Extract the fields."
        )

    assert len(prompts) == report_orchestrator._VALIDATION_RETRY_LIMIT


def test_run_bounded_call_passes_bounded_http_timeout_and_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from google.adk.events.event import Event
    from google.adk.events.event_actions import EventActions

    skills_dir = tmp_path / "skills"
    grounding_skill = load_skill_from_dir(
        _make_skill_dir(skills_dir, "evidence-grounding", "Cites.", "Ground every claim.")
    )
    config = load_variables_config(_make_report_skill(skills_dir) / "variables.json")
    schema = build_output_schema(config.call_groups[0])
    workspace = _make_workspace(tmp_path / "workspace")
    agent = report_orchestrator._build_bounded_agent(
        workspace, "anthropic/claude-sonnet-5", schema, "do the extraction", grounding_skill
    )
    session_service, session_id = report_orchestrator._build_session(workspace)
    captured_run_configs: list[object] = []

    class _FakeRunner:
        def __init__(self, *, agent, app_name, session_service) -> None:
            self._session_service = session_service

        async def run_async(self, *, user_id, session_id, new_message, run_config=None):
            captured_run_configs.append(run_config)
            session = await self._session_service.get_session(
                app_name=report_orchestrator._RUNNER_APP_NAME,
                user_id=report_orchestrator._RUNNER_USER_ID,
                session_id=session_id,
            )
            event = Event(
                author="agent",
                actions=EventActions(state_delta={report_orchestrator._OUTPUT_KEY: {"ok": True}}),
            )
            await self._session_service.append_event(session, event)
            return
            yield

    monkeypatch.setattr(report_orchestrator, "Runner", _FakeRunner)

    report_orchestrator._run_bounded_call(
        agent, session_service, session_id, "Extract the fields."
    )

    assert len(captured_run_configs) == 1
    http_options = captured_run_configs[0].http_options
    assert http_options.timeout == report_orchestrator._MODEL_CALL_TIMEOUT_MS
    assert http_options.retry_options.attempts == report_orchestrator._MODEL_CALL_RETRY_ATTEMPTS
