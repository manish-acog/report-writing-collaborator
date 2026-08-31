from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import patch

from typer.testing import CliRunner

from report_writing_agent.cli import main as cli_main
from report_writing_collaborator import ElnSource, FileSource

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_cli_builds_workspace_and_writes_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    source_file = tmp_path / "protocol.pdf"
    source_file.write_bytes(b"pdf")
    report_path = tmp_path / "reports" / "final.md"
    workspaces_root = tmp_path / ".workspaces"
    built_sources: list[FileSource | ElnSource] = []

    monkeypatch.setattr(cli_main, "_ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(cli_main, "_WORKSPACES_ROOT", workspaces_root)

    def fake_build(sources, config):
        built_sources.extend(sources)
        assert config.publish_root == workspaces_root
        assert config.benchling_api_key == "key"
        assert config.benchling_url == "https://example.benchling.com"
        workspace_dir = config.publish_root / "ws_test" / "1"
        workspace_dir.mkdir(parents=True)
        return SimpleNamespace(workspace_id="ws_test", workspace_version=1)

    with (
        patch("report_writing_collaborator.build_workspace", side_effect=fake_build),
        patch(
            "report_writing_agent.report_orchestrator.write_report",
            return_value="# Report\n",
        ) as write_report,
    ):
        result = runner.invoke(
            cli_main.app,
            [
                "--file",
                str(source_file),
                "--benchling-entry-id",
                "etr_123",
                "--skill",
                "custom-skill",
                "--template",
                "custom.md",
                "--model",
                "openai/gpt-4o",
                "--output",
                str(report_path),
            ],
            env={
                "BENCHLING_API_KEY": "key",
                "BENCHLING_URL": "https://example.benchling.com",
                "NO_COLOR": "1",
            },
        )

    assert result.exit_code == 0, result.output
    assert report_path.read_text(encoding="utf-8") == "# Report\n"
    assert "✓ Workspace built:" in result.stdout
    assert "✓ Report written:" in result.stdout
    assert isinstance(built_sources[0], FileSource)
    assert built_sources[0].path == source_file
    assert built_sources[0].source_instance_id == "file_01"
    assert isinstance(built_sources[1], ElnSource)
    assert built_sources[1].entry_id == "etr_123"
    assert built_sources[1].source_instance_id == "benchling_01"
    write_report.assert_called_once_with(
        workspaces_root / "ws_test" / "1",
        skill_name="custom-skill",
        template_name="custom.md",
        model="openai/gpt-4o",
    )


def test_cli_json_output_is_machine_readable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    source_file = tmp_path / "protocol.pdf"
    source_file.write_bytes(b"pdf")
    workspaces_root = tmp_path / ".workspaces"

    monkeypatch.setattr(cli_main, "_ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(cli_main, "_WORKSPACES_ROOT", workspaces_root)

    def fake_build(_sources, config):
        workspace_dir = config.publish_root / "ws_json" / "2"
        workspace_dir.mkdir(parents=True)
        return SimpleNamespace(workspace_id="ws_json", workspace_version=2)

    with (
        patch("report_writing_collaborator.build_workspace", side_effect=fake_build),
        patch("report_writing_agent.report_orchestrator.write_report", return_value="done\n"),
    ):
        result = runner.invoke(cli_main.app, ["--file", str(source_file), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {
        "ok": True,
        "data": {
            "workspace_id": "ws_json",
            "workspace_version": 2,
            "report_path": str(workspaces_root / "ws_json" / "2" / "report.md"),
        },
    }
    assert "✓" not in result.stdout


def test_cli_rejects_missing_input() -> None:
    runner = CliRunner()

    result = runner.invoke(cli_main.app, [])

    assert result.exit_code == 2
    assert "at least one --file or --benchling-entry-id is required" in result.stderr
    assert "Usage:" in result.stderr


def test_cli_rejects_missing_file(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(cli_main.app, ["--file", str(tmp_path / "missing.pdf")])

    assert result.exit_code == 1
    assert "File not found:" in result.stderr
    assert "Try: check the path and run again" in result.stderr


def test_cli_help_shows_examples() -> None:
    runner = CliRunner()

    result = runner.invoke(cli_main.app, ["--help"], env={"NO_COLOR": "1"})

    assert result.exit_code == 0
    assert "Examples:" in result.stdout
    assert "report-writing-agent --file protocol.pdf" in result.stdout
    assert "--benchling-entry-id etr_123" in result.stdout


def test_cli_version_uses_package_version() -> None:
    runner = CliRunner()

    result = runner.invoke(cli_main.app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "report-writing-agent/0.1.0"
