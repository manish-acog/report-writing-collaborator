from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import patch

from typer.testing import CliRunner

from canonical_workspace import ElnSource, FileSource
from report_writing_collaborator.cli import main as cli_main

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_file_sources_pairs_roles_by_position(tmp_path: Path) -> None:
    paths = [tmp_path / "a.pdf", tmp_path / "b.pdf"]

    sources = cli_main._file_sources(paths, ["protocol", "sop"])

    assert [s.source_role for s in sources] == ["protocol", "sop"]
    assert [s.source_instance_id for s in sources] == ["file_01", "file_02"]


def test_file_sources_leaves_remainder_unset_when_fewer_roles(tmp_path: Path) -> None:
    paths = [tmp_path / "a.pdf", tmp_path / "b.pdf"]

    sources = cli_main._file_sources(paths, ["protocol"])

    assert [s.source_role for s in sources] == ["protocol", None]


def test_file_sources_defaults_to_no_roles(tmp_path: Path) -> None:
    sources = cli_main._file_sources([tmp_path / "a.pdf"], [])

    assert sources[0].source_role is None


def test_eln_sources_pairs_roles_by_position() -> None:
    sources = cli_main._eln_sources(["etr_1", "etr_2"], ["dosing_records", "necropsy_findings"])

    assert [s.source_role for s in sources] == ["dosing_records", "necropsy_findings"]


def test_eln_sources_leaves_remainder_unset_when_fewer_roles() -> None:
    sources = cli_main._eln_sources(["etr_1", "etr_2"], ["dosing_records"])

    assert [s.source_role for s in sources] == ["dosing_records", None]


def test_cli_wires_file_and_benchling_roles_by_position(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    source_file = tmp_path / "protocol.pdf"
    source_file.write_bytes(b"pdf")
    workspaces_root = tmp_path / ".workspaces"
    built_sources: list[FileSource | ElnSource] = []

    monkeypatch.setattr(cli_main, "_ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(cli_main, "_WORKSPACES_ROOT", workspaces_root)

    def fake_build(sources, config):
        built_sources.extend(sources)
        workspace_dir = config.publish_root / "ws_role" / "1"
        workspace_dir.mkdir(parents=True)
        return SimpleNamespace(workspace_id="ws_role", workspace_version=1)

    fake_result = SimpleNamespace(
        text="# Report\n",
        report_path=workspaces_root / "ws_role" / ".tasks" / "task_1" / "report.md",
    )

    with (
        patch("canonical_workspace.build_workspace", side_effect=fake_build),
        patch(
            "report_writing_collaborator.agent.report_orchestrator.write_report",
            return_value=fake_result,
        ),
    ):
        result = runner.invoke(
            cli_main.app,
            [
                "--file",
                str(source_file),
                "--file-role",
                "protocol",
                "--benchling-entry-id",
                "etr_1",
                "--benchling-entry-id",
                "etr_2",
                "--benchling-role",
                "dosing_records",
                "--benchling-role",
                "necropsy_findings",
            ],
            env={
                "BENCHLING_API_KEY": "key",
                "BENCHLING_URL": "https://example.benchling.com",
                "NO_COLOR": "1",
            },
        )

    assert result.exit_code == 0, result.output
    assert [s.source_role for s in built_sources] == [
        "protocol",
        "dosing_records",
        "necropsy_findings",
    ]


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

    fake_result = SimpleNamespace(
        text="# Report\n",
        report_path=workspaces_root / "ws_test" / ".tasks" / "task_1" / "custom.md",
    )
    with (
        patch("canonical_workspace.build_workspace", side_effect=fake_build),
        patch(
            "report_writing_collaborator.agent.report_orchestrator.write_report",
            return_value=fake_result,
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

    task_report_path = workspaces_root / "ws_json" / ".tasks" / "task_2" / "report.md"
    fake_result = SimpleNamespace(text="done\n", report_path=task_report_path)

    with (
        patch("canonical_workspace.build_workspace", side_effect=fake_build),
        patch(
            "report_writing_collaborator.agent.report_orchestrator.write_report",
            return_value=fake_result,
        ),
    ):
        result = runner.invoke(cli_main.app, ["--file", str(source_file), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {
        "ok": True,
        "data": {
            "workspace_id": "ws_json",
            "workspace_version": 2,
            "report_path": str(task_report_path),
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


def test_cli_rerender_task_uses_persisted_task_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    workspaces_root = tmp_path / ".workspaces"
    task_dir = workspaces_root / "ws_test" / ".tasks" / "task_1"
    task_dir.mkdir(parents=True)
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "workspace_id": "ws_test",
                "workspace_version": 1,
                "skill_name": "general-report-writing",
                "template_name": "report.md",
                "model": "anthropic/claude-sonnet-5",
                "started_at": "2026-01-01T00:00:00+00:00",
                "completed_at": "2026-01-01T00:00:01+00:00",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli_main, "_ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(cli_main, "_WORKSPACES_ROOT", workspaces_root)

    fake_result = SimpleNamespace(text="<h1>Report</h1>", report_path=task_dir / "report.html")

    with patch(
        "report_writing_collaborator.agent.report_orchestrator.rerender_task",
        return_value=fake_result,
    ) as rerender_task:
        result = runner.invoke(
            cli_main.app,
            ["--rerender-task", "task_1", "--template", "report.html", "--json"],
        )

    assert result.exit_code == 0, result.output
    rerender_task.assert_called_once_with(
        task_dir,
        workspaces_root / "ws_test" / "1",
        skill_name="general-report-writing",
        template_name="report.html",
    )
    payload = json.loads(result.stdout)
    assert payload == {
        "ok": True,
        "data": {
            "workspace_id": "ws_test",
            "workspace_version": 1,
            "report_path": str(task_dir / "report.html"),
        },
    }


def test_cli_rejects_rerender_task_combined_with_file(tmp_path: Path) -> None:
    runner = CliRunner()
    source_file = tmp_path / "protocol.pdf"
    source_file.write_bytes(b"pdf")

    result = runner.invoke(
        cli_main.app, ["--rerender-task", "task_1", "--file", str(source_file)]
    )

    assert result.exit_code == 2
    assert "cannot be combined with --file" in result.stderr


def test_cli_rejects_unknown_rerender_task_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    workspaces_root = tmp_path / ".workspaces"
    workspaces_root.mkdir()
    monkeypatch.setattr(cli_main, "_ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(cli_main, "_WORKSPACES_ROOT", workspaces_root)

    result = runner.invoke(cli_main.app, ["--rerender-task", "no-such-task"])

    assert result.exit_code == 1
    assert "No task found with id: no-such-task" in result.stderr
