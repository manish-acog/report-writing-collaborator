from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

import canonical_workspace as cw

_PACKAGE_NAME = "report-writing-collaborator"
_CLI_NAME = "report-writing-agent"
_DEFAULT_SKILL = "general-report-writing"
_DEFAULT_TEMPLATE = "report.md"
_WORKSPACE_ROOT_ENV = "WORKSPACE_ROOT"
_BENCHLING_API_KEY_ENV = "BENCHLING_API_KEY"
_BENCHLING_URL_ENV = "BENCHLING_URL"
_ENV_PATH = Path("src/report_writing_agent/.env")
_WORKSPACES_ROOT = Path(".workspaces")
_FILE_INSTANCE_PREFIX = "file"
_BENCHLING_INSTANCE_PREFIX = "benchling"
_INSTANCE_ID_WIDTH = 2
_USAGE = "Usage: report-writing-agent [OPTIONS]"


app = typer.Typer(add_completion=False, rich_markup_mode="rich")


@dataclass(frozen=True, slots=True)
class _CliOptions:
    files: list[Path]
    benchling_entry_ids: list[str]
    skill: str
    template: str
    model: str | None
    output: Path | None
    json_output: bool
    no_color: bool
    debug: bool


@dataclass(frozen=True, slots=True)
class _RunResult:
    workspace_id: str
    workspace_version: int
    report_path: Path


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"{_CLI_NAME}/{version(_PACKAGE_NAME)}")
        raise typer.Exit()


def _load_env(path: Path) -> None:
    if not path.is_file():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _console(*, stderr: bool, no_color: bool) -> Console:
    pipe_no_color = not sys.stdout.isatty()
    env_no_color = os.environ.get("NO_COLOR") is not None
    return Console(stderr=stderr, no_color=no_color or pipe_no_color or env_no_color)


def _fail(message: str, *, suggestion: str, options: _CliOptions, code: int = 1) -> None:
    error_console = _console(stderr=True, no_color=options.no_color)
    error_console.print(f"[red]✗ Error:[/red] {message}")
    error_console.print(f"  Try: {suggestion}")

    if options.json_output:
        payload = {"ok": False, "error": {"code": "ERROR", "message": message}}
        typer.echo(json.dumps(payload))

    raise typer.Exit(code=code)


def _usage_error(message: str, *, no_color: bool, json_output: bool = False) -> None:
    error_console = _console(stderr=True, no_color=no_color)
    error_console.print(f"[red]✗ Error:[/red] {message}")
    error_console.print(_USAGE)

    if json_output:
        payload = {"ok": False, "error": {"code": "USAGE", "message": message}}
        typer.echo(json.dumps(payload))

    raise typer.Exit(code=2)


def _file_sources(paths: list[Path]) -> list[cw.FileSource]:
    return [
        cw.FileSource(
            path=path,
            source_instance_id=f"{_FILE_INSTANCE_PREFIX}_{index:0{_INSTANCE_ID_WIDTH}d}",
        )
        for index, path in enumerate(paths, start=1)
    ]


def _eln_sources(entry_ids: list[str]) -> list[cw.ElnSource]:
    return [
        cw.ElnSource(
            entry_id=entry_id,
            source_instance_id=f"{_BENCHLING_INSTANCE_PREFIX}_{index:0{_INSTANCE_ID_WIDTH}d}",
        )
        for index, entry_id in enumerate(entry_ids, start=1)
    ]


def _check_inputs(options: _CliOptions) -> None:
    if not options.files and not options.benchling_entry_ids:
        _usage_error(
            "at least one --file or --benchling-entry-id is required",
            no_color=options.no_color,
            json_output=options.json_output,
        )

    for path in options.files:
        if not path.is_file():
            _fail(
                f"File not found: {path}",
                suggestion="check the path and run again",
                options=options,
            )


def _build_workspace(options: _CliOptions) -> cw.WorkspaceManifest:
    sources: list[cw.FileSource | cw.ElnSource] = [
        *_file_sources(options.files),
        *_eln_sources(options.benchling_entry_ids),
    ]
    _WORKSPACES_ROOT.mkdir(parents=True, exist_ok=True)

    return cw.build_workspace(
        sources,
        cw.WorkspaceConfig(
            publish_root=_WORKSPACES_ROOT,
            benchling_api_key=os.environ.get(_BENCHLING_API_KEY_ENV),
            benchling_url=os.environ.get(_BENCHLING_URL_ENV),
        ),
    )


def _write_report(options: _CliOptions, manifest: cw.WorkspaceManifest) -> _RunResult:
    from report_writing_agent import report_orchestrator

    workspace_dir = _WORKSPACES_ROOT / manifest.workspace_id / str(manifest.workspace_version)
    report = report_orchestrator.write_report(
        workspace_dir,
        skill_name=options.skill,
        template_name=options.template,
        model=options.model,
    )
    report_path = options.output or workspace_dir / options.template
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    return _RunResult(
        workspace_id=manifest.workspace_id,
        workspace_version=manifest.workspace_version,
        report_path=report_path,
    )


def _run(options: _CliOptions) -> _RunResult:
    # report_orchestrator imports agent.py, whose ADK root_agent needs a
    # placeholder WORKSPACE_ROOT before the generated workspace exists.
    os.environ[_WORKSPACE_ROOT_ENV] = os.environ.get(_WORKSPACE_ROOT_ENV) or str(_WORKSPACES_ROOT)
    _load_env(_ENV_PATH)
    _check_inputs(options)

    output_console = _console(stderr=False, no_color=options.no_color)
    error_console = _console(stderr=True, no_color=options.no_color)
    manifest = _build_workspace(options)
    workspace_dir = _WORKSPACES_ROOT / manifest.workspace_id / str(manifest.workspace_version)

    if not options.json_output:
        output_console.print(f"[green]✓[/green] Workspace built: {workspace_dir}")
        with error_console.status("Generating report...", spinner="dots"):
            return _write_report(options, manifest)

    return _write_report(options, manifest)


def _handle_error(error: Exception, options: _CliOptions) -> None:
    if options.debug:
        _console(stderr=True, no_color=options.no_color).print_exception()

    message = str(error) or error.__class__.__name__
    suggestion = "fix the input or credentials and run again"
    if "benchling_api_key" in message or "Benchling" in message:
        suggestion = "set BENCHLING_API_KEY and BENCHLING_URL in src/report_writing_agent/.env"
    elif "API key" in message or "credential" in message.lower() or "auth" in message.lower():
        suggestion = "fill src/report_writing_agent/.env with model credentials"

    _fail(message, suggestion=suggestion, options=options)


@app.command(context_settings={"help_option_names": ["-h", "--help"]})
def main(
    file_paths: Annotated[
        list[Path] | None,
        typer.Option(
            "--file",
            help="Input document path. Repeat for multiple files.",
            show_default=False,
        ),
    ] = None,
    benchling_entry_ids: Annotated[
        list[str] | None,
        typer.Option(
            "--benchling-entry-id",
            help="Benchling entry ID. Repeat for multiple entries. Requires BENCHLING_API_KEY and BENCHLING_URL.",
            show_default=False,
        ),
    ] = None,
    skill: Annotated[
        str,
        typer.Option("--skill", help="Report skill under src/report_writing_agent/skills."),
    ] = _DEFAULT_SKILL,
    template: Annotated[
        str,
        typer.Option("--template", help="Template file under the skill's templates/ directory."),
    ] = _DEFAULT_TEMPLATE,
    model: Annotated[
        str | None,
        typer.Option("--model", help="LiteLLM model string. Defaults to REPORT_AGENT_MODEL."),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Rendered report path."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON to stdout."),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option("--no-color", help="Disable colored output."),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", "-d", help="Print a traceback for unexpected errors."),
    ] = False,
    version_flag: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_show_version,
            help="Show version and exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Build a workspace from sources and write a rendered report.

    \b
    Examples:
      report-writing-agent --file protocol.pdf --file appendix.docx
      report-writing-agent --file protocol.pdf --benchling-entry-id etr_123
    """
    _ = version_flag
    options = _CliOptions(
        files=file_paths or [],
        benchling_entry_ids=benchling_entry_ids or [],
        skill=skill,
        template=template,
        model=model,
        output=output,
        json_output=json_output,
        no_color=no_color,
        debug=debug,
    )

    try:
        result = _run(options)
    except typer.Exit:
        raise
    except Exception as error:
        _handle_error(error, options)

    if options.json_output:
        payload = {
            "ok": True,
            "data": {
                "workspace_id": result.workspace_id,
                "workspace_version": result.workspace_version,
                "report_path": str(result.report_path),
            },
        }
        typer.echo(json.dumps(payload))
    else:
        _console(stderr=False, no_color=options.no_color).print(
            f"[green]✓[/green] Report written: {result.report_path}"
        )


if __name__ == "__main__":
    app()
