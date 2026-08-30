"""Drives a report-writing skill's bounded extraction calls and renders the result.

For each call_group in a skill's variables.json, runs one bounded LlmAgent
turn (the four workspace tools, plus the workspace-summary skill for
structural understanding) constrained to that group's schema, merges every
group's results, and renders them against the skill's template. See
docs/general_report_writing.md for the design.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types as genai_types

from report_writing_agent.agent import DEFAULT_MODEL, SKILLS_DIR, make_workspace_tools
from report_writing_collaborator import build_output_schema, load_variables_config, render

if TYPE_CHECKING:
    from pathlib import Path

    from google.adk.skills import Skill
    from pydantic import BaseModel

    from report_writing_collaborator import CallGroup

_DEFAULT_TEMPLATE_NAME = "report.md"
_VARIABLES_FILE_NAME = "variables.json"
_TEMPLATES_DIR_NAME = "templates"
_STRUCTURE_SKILL_NAME = "workspace-summary"
_EXTRACTOR_AGENT_NAME = "report_field_extractor"
_OUTPUT_KEY = "result"
_RUNNER_APP_NAME = "report_orchestrator"
_RUNNER_USER_ID = "report_orchestrator"
_EXTRACTION_PROMPT = "Extract the fields listed in your instructions from this workspace."


def write_report(
    workspace_root: Path,
    skill_name: str = "general-report-writing",
    template_name: str = _DEFAULT_TEMPLATE_NAME,
    model: str | None = None,
) -> str:
    """Runs one bounded extraction call per call_group and renders the report.

    Args:
        workspace_root: The published workspace directory to read from.
        skill_name: The report-writing skill to run, under skills/.
        template_name: Which file in the skill's templates/ to render.
        model: A LiteLLM model string. Defaults to REPORT_AGENT_MODEL.

    Returns:
        The rendered report text.
    """
    workspace_root = workspace_root.resolve()
    model = model or os.environ.get("REPORT_AGENT_MODEL", DEFAULT_MODEL)

    skill_dir = SKILLS_DIR / skill_name
    skill = load_skill_from_dir(skill_dir)
    structure_skill = load_skill_from_dir(SKILLS_DIR / _STRUCTURE_SKILL_NAME)
    config = load_variables_config(skill_dir / _VARIABLES_FILE_NAME)

    values: dict[str, dict] = {}
    for call_group in config.call_groups:
        schema = build_output_schema(call_group)
        instruction = _build_instruction(skill, call_group)
        agent = _build_bounded_agent(workspace_root, model, schema, instruction, structure_skill)
        values.update(_run_bounded_call(agent))

    template_path = skill_dir / _TEMPLATES_DIR_NAME / template_name
    return render(template_path, values)


def _build_instruction(skill: Skill, call_group: CallGroup) -> str:
    field_list = "\n".join(
        f"- **{variable.name}**: {variable.description}" for variable in call_group.variables
    )
    return f"{skill.instructions}\n\n## Fields for this call\n\n{field_list}"


def _build_bounded_agent(
    workspace_root: Path,
    model: str,
    output_schema: type[BaseModel],
    instruction: str,
    structure_skill: Skill,
) -> LlmAgent:
    tools: list[object] = [
        *make_workspace_tools(workspace_root, agent_model=model),
        SkillToolset(skills=[structure_skill]),
    ]
    return LlmAgent(
        model=LiteLlm(model=model),
        name=_EXTRACTOR_AGENT_NAME,
        instruction=instruction,
        tools=tools,
        output_schema=output_schema,
        output_key=_OUTPUT_KEY,
    )


def _run_bounded_call(agent: LlmAgent) -> dict:
    """Runs one bounded LlmAgent turn and returns its validated output_key state."""
    return asyncio.run(_run_bounded_call_async(agent))


async def _run_bounded_call_async(agent: LlmAgent) -> dict:
    runner = InMemoryRunner(agent=agent, app_name=_RUNNER_APP_NAME)
    session = await runner.session_service.create_session(
        app_name=_RUNNER_APP_NAME, user_id=_RUNNER_USER_ID
    )
    message = genai_types.Content(role="user", parts=[genai_types.Part(text=_EXTRACTION_PROMPT)])

    try:
        async for _event in runner.run_async(
            user_id=_RUNNER_USER_ID, session_id=session.id, new_message=message
        ):
            pass
    except Exception as error:
        raise RuntimeError(f"Model call for '{agent.name}' failed: {error}") from error

    updated = await runner.session_service.get_session(
        app_name=_RUNNER_APP_NAME, user_id=_RUNNER_USER_ID, session_id=session.id
    )
    if updated is None or _OUTPUT_KEY not in updated.state:
        raise RuntimeError(f"Model call for '{agent.name}' produced no structured output")

    return updated.state[_OUTPUT_KEY]
