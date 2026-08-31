from __future__ import annotations

from argparse import Namespace
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import patch

from scripts import smoke_test_report

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_main_persists_report_in_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspaces_root = tmp_path / ".workspaces"
    source_pdf = tmp_path / "source.pdf"
    source_pdf.write_bytes(b"pdf")
    args = Namespace(
        pdf=source_pdf,
        skill="general-report-writing",
        template="report.md",
        model=None,
    )
    monkeypatch.setattr(smoke_test_report, "_parse_args", lambda: args)
    monkeypatch.setattr(smoke_test_report, "_WORKSPACES_ROOT", workspaces_root)

    def fake_build(_sources, config):
        workspace_dir = config.publish_root / "ws_test" / "1"
        workspace_dir.mkdir(parents=True)
        (workspace_dir / "manifest.json").write_text("{}\n", encoding="utf-8")
        return SimpleNamespace(workspace_id="ws_test", workspace_version=1)

    with (
        patch("canonical_workspace.build_workspace", side_effect=fake_build),
        patch(
            "report_writing_collaborator.agent.report_orchestrator.write_report",
            return_value="# Persisted report\n",
        ),
    ):
        smoke_test_report.main()

    report_path = workspaces_root / "ws_test" / "1" / "report.md"
    assert report_path.read_text(encoding="utf-8") == "# Persisted report\n"
    assert (report_path.parent / "manifest.json").is_file()
    assert "# Persisted report" in capsys.readouterr().out
