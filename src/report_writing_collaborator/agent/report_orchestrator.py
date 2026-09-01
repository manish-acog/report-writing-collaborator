"""Drives a report-writing skill's bounded extraction calls and renders the result.

Runs one shared, database-backed ADK session per write_report() call: a
bootstrap turn (workspace-summary only) builds structural understanding
once, then one bounded LlmAgent turn per call_group (evidence-grounding
plus workspace tools, constrained to that group's schema) extracts fields
against the same session, so later turns build on earlier ones instead of
re-discovering the workspace. A call_group whose output fails schema
validation (e.g. an out-of-range [[cite:N]] marker) gets one corrective
retry, fed the validation error as a new turn, before the run gives up on
it. Every group's results are merged and rendered against the skill's
template. Everything the run produces -- the session transcript,
provenance, and the rendered report -- is written to
.tasks/<task_id>/, a sibling of workspace_root's numbered version
directory; workspace_root itself is never written to. See
docs/general_report_writing.md, docs/extraction_session_persistence.md,
docs/citation_marker_retry.md, and docs/task_run_artifacts.md for the
design.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types as genai_types
from pydantic import ValidationError

from report_writing_collaborator import build_output_schema, load_variables_config, render
from report_writing_collaborator.agent.agent import DEFAULT_MODEL, SKILLS_DIR, make_workspace_tools

if TYPE_CHECKING:
    from pathlib import Path

    from google.adk.sessions import BaseSessionService
    from google.adk.skills import Skill
    from pydantic import BaseModel

    from report_writing_collaborator import CallGroup

_DEFAULT_TEMPLATE_NAME = "report.md"
_VARIABLES_FILE_NAME = "variables.json"
_TEMPLATES_DIR_NAME = "templates"
_STRUCTURE_SKILL_NAME = "workspace-summary"
_GROUNDING_SKILL_NAME = "evidence-grounding"
_EXTRACTOR_AGENT_NAME = "report_field_extractor"
_OUTPUT_KEY = "result"
_RUNNER_APP_NAME = "report_orchestrator"
_RUNNER_USER_ID = "report_orchestrator"
_SESSIONS_DB_NAME = "sessions.db"
_TASKS_DIR_NAME = ".tasks"
_TASK_FILE_NAME = "task.json"
# Total attempts for one call_group's turn, including the first: one
# corrective retry on a citation-marker validation failure before giving up.
_VALIDATION_RETRY_LIMIT = 2
_EXTRACTION_PROMPT = "Extract the fields listed in your instructions from this workspace."
_BOOTSTRAP_PROMPT = (
    "Load the `workspace-summary` skill and follow its structural pass to build "
    "a complete understanding of this workspace's source graph, roles, "
    "hierarchy, assets, and images. The extraction calls that follow in this "
    "same session build on this understanding, so be thorough."
)


@dataclass(frozen=True, slots=True)
class WriteReportResult:
    """One write_report() run's rendered text and where it's archived."""

    text: str
    task_id: str
    task_dir: Path
    report_path: Path


def write_report(
    workspace_root: Path,
    skill_name: str = "general-report-writing",
    template_name: str = _DEFAULT_TEMPLATE_NAME,
    model: str | None = None,
) -> WriteReportResult:
    """Runs a bootstrap turn, one bounded extraction call per call_group, and renders.

    Every turn runs against one shared, database-backed session
    (<task_dir>/sessions.db) so later turns see earlier ones' context.

    Args:
        workspace_root: The published workspace directory to read from.
        skill_name: The report-writing skill to run, under skills/.
        template_name: Which file in the skill's templates/ to render.
        model: A LiteLLM model string. Defaults to REPORT_AGENT_MODEL.

    Returns:
        The rendered report text and its .tasks/<task_id>/ archive location.
    """
    workspace_root = workspace_root.resolve()
    model = model or os.environ.get("REPORT_AGENT_MODEL", DEFAULT_MODEL)
    started_at = datetime.now(UTC)

    task_id = uuid.uuid4().hex
    task_dir = workspace_root.parent / _TASKS_DIR_NAME / task_id
    task_dir.mkdir(parents=True)

    skill_dir = SKILLS_DIR / skill_name
    skill = load_skill_from_dir(skill_dir)
    structure_skill = load_skill_from_dir(SKILLS_DIR / _STRUCTURE_SKILL_NAME)
    grounding_skill = load_skill_from_dir(SKILLS_DIR / _GROUNDING_SKILL_NAME)
    config = load_variables_config(skill_dir / _VARIABLES_FILE_NAME)

    session_service, session_id = _build_session(task_dir)

    bootstrap_agent = _build_bootstrap_agent(workspace_root, model, structure_skill)
    _run_bounded_call(
        bootstrap_agent, session_service, session_id, _BOOTSTRAP_PROMPT, expect_output=False
    )

    values: dict[str, dict] = {}
    for call_group in config.call_groups:
        schema = build_output_schema(call_group)
        instruction = _build_instruction(skill, call_group)
        agent = _build_bounded_agent(workspace_root, model, schema, instruction, grounding_skill)
        values.update(_run_bounded_call(agent, session_service, session_id, _EXTRACTION_PROMPT))

    asyncio.run(session_service.close())

    template_path = skill_dir / _TEMPLATES_DIR_NAME / template_name
    text = render(template_path, values, workspace_root)

    report_path = task_dir / template_name
    report_path.write_text(text, encoding="utf-8")
    _write_task_metadata(
        task_dir,
        workspace_root=workspace_root,
        skill_name=skill_name,
        template_name=template_name,
        model=model,
        started_at=started_at,
        completed_at=datetime.now(UTC),
    )

    return WriteReportResult(
        text=text, task_id=task_id, task_dir=task_dir, report_path=report_path
    )


def _write_task_metadata(
    task_dir: Path,
    *,
    workspace_root: Path,
    skill_name: str,
    template_name: str,
    model: str,
    started_at: datetime,
    completed_at: datetime,
) -> None:
    workspace_id, workspace_version = _workspace_identity(workspace_root)
    task = {
        "workspace_id": workspace_id,
        "workspace_version": workspace_version,
        "skill_name": skill_name,
        "template_name": template_name,
        "model": model,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
    }
    (task_dir / _TASK_FILE_NAME).write_text(
        json.dumps(task, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _workspace_identity(workspace_root: Path) -> tuple[str, int | str]:
    """Best-effort workspace_id/workspace_version from workspace_root's own path shape.

    Real runs pass <publish_root>/<workspace_id>/<version>/, where
    workspace_version parses as int. A workspace_root that doesn't follow
    that shape (e.g. a synthetic test fixture) records its raw directory
    name instead of failing task.json construction.
    """
    workspace_id = workspace_root.parent.name
    version_name = workspace_root.name
    try:
        workspace_version: int | str = int(version_name)
    except ValueError:
        workspace_version = version_name

    return workspace_id, workspace_version


def _build_session(task_dir: Path) -> tuple[DatabaseSessionService, str]:
    """Builds the run's shared session service and a fresh session.

    Points sqlalchemy at <task_dir>/sessions.db. Every write_report() call
    gets its own fresh session_id, never resumed; sessions.db accumulates
    exactly one row per run -- it lives in this run's own task_dir.
    """
    db_path = task_dir / _SESSIONS_DB_NAME
    session_service = DatabaseSessionService(db_url=f"sqlite+aiosqlite:///{db_path}")
    session = asyncio.run(
        session_service.create_session(app_name=_RUNNER_APP_NAME, user_id=_RUNNER_USER_ID)
    )
    return session_service, session.id


def _build_instruction(skill: Skill, call_group: CallGroup) -> str:
    field_list = "\n".join(
        f"- **{variable.name}**: {variable.description}" for variable in call_group.variables
    )
    return f"{skill.instructions}\n\n## Fields for this call\n\n{field_list}"


def _build_bootstrap_agent(
    workspace_root: Path,
    model: str,
    structure_skill: Skill,
) -> LlmAgent:
    """Builds the once-per-run agent that primes the shared session with workspace structure."""
    tools: list[object] = [
        *make_workspace_tools(workspace_root, agent_model=model),
        SkillToolset(skills=[structure_skill]),
    ]
    return LlmAgent(
        model=LiteLlm(model=model),
        name=_EXTRACTOR_AGENT_NAME,
        instruction=_BOOTSTRAP_PROMPT,
        tools=tools,
    )


def _build_bounded_agent(
    workspace_root: Path,
    model: str,
    output_schema: type[BaseModel],
    instruction: str,
    grounding_skill: Skill,
) -> LlmAgent:
    tools: list[object] = [
        *make_workspace_tools(workspace_root, agent_model=model),
        SkillToolset(skills=[grounding_skill]),
    ]
    return LlmAgent(
        model=LiteLlm(model=model),
        name=_EXTRACTOR_AGENT_NAME,
        instruction=instruction,
        tools=tools,
        output_schema=output_schema,
        output_key=_OUTPUT_KEY,
    )


def _run_bounded_call(
    agent: LlmAgent,
    session_service: BaseSessionService,
    session_id: str,
    prompt: str,
    *,
    expect_output: bool = True,
) -> dict:
    """Runs one bounded LlmAgent turn against the shared session.

    Returns its validated output_key state, or {} when expect_output is
    False (the bootstrap turn has no structured output to collect).
    """
    return asyncio.run(
        _run_bounded_call_async(
            agent, session_service, session_id, prompt, expect_output=expect_output
        )
    )


async def _run_bounded_call_async(
    agent: LlmAgent,
    session_service: BaseSessionService,
    session_id: str,
    prompt: str,
    *,
    expect_output: bool,
) -> dict:
    runner = Runner(agent=agent, app_name=_RUNNER_APP_NAME, session_service=session_service)
    next_prompt = prompt

    for attempt in range(1, _VALIDATION_RETRY_LIMIT + 1):
        message = genai_types.Content(role="user", parts=[genai_types.Part(text=next_prompt)])
        try:
            async for _event in runner.run_async(
                user_id=_RUNNER_USER_ID, session_id=session_id, new_message=message
            ):
                pass
        except ValidationError as error:
            if attempt == _VALIDATION_RETRY_LIMIT:
                raise RuntimeError(
                    f"Model call for '{agent.name}' failed schema validation after "
                    f"{attempt} attempts: {'; '.join(_validation_messages(error))}"
                ) from error
            next_prompt = _corrective_prompt(error)
            continue
        except Exception as error:
            raise RuntimeError(f"Model call for '{agent.name}' failed: {error}") from error
        else:
            break

    if not expect_output:
        return {}

    updated = await session_service.get_session(
        app_name=_RUNNER_APP_NAME, user_id=_RUNNER_USER_ID, session_id=session_id
    )
    if updated is None or _OUTPUT_KEY not in updated.state:
        raise RuntimeError(f"Model call for '{agent.name}' produced no structured output")

    return updated.state[_OUTPUT_KEY]


def _validation_messages(error: ValidationError) -> list[str]:
    """Extracts each error's own message, without pydantic's boilerplate wrapper text."""
    messages = []
    for detail in error.errors():
        ctx_error = detail.get("ctx", {}).get("error")
        messages.append(str(ctx_error) if ctx_error is not None else detail["msg"])
    return messages


def _corrective_prompt(error: ValidationError) -> str:
    """Builds the next turn's message: the validation failure, sent back for a fix."""
    details = "; ".join(_validation_messages(error))
    return (
        f"Your last response failed schema validation: {details}. Correct the "
        f"issue and resend the complete output for this call."
    )
