#!/usr/bin/env python3
"""Smoke-tests write_report() against a real PDF and a real model.

Builds a persistent published workspace from one PDF, runs the full
general-report-writing pipeline against it, prints where write_report()
archived every artifact under .tasks/<task_id>/, and prints the rendered
report itself. Loads src/report_writing_collaborator/agent/.env for
credentials if present, so a `uv run` with no setup is enough once that
file has real values (see src/report_writing_collaborator/agent/.env.example).

Usage:
    uv run python scripts/smoke_test_report.py
    uv run python scripts/smoke_test_report.py --pdf path/to/file.pdf --model openai/gpt-4o
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

_ENV_PATH = _REPO_ROOT / "src" / "report_writing_collaborator" / "agent" / ".env"
_DEFAULT_PDF = _REPO_ROOT / "examples" / "pdfs" / "somatosensory.pdf"
_WORKSPACES_ROOT = _REPO_ROOT / ".workspaces"
_SEPARATOR = "=" * 72


def _load_env(path: Path) -> None:
    """Loads KEY=VALUE lines from a .env file without overriding the shell's own."""
    if not path.is_file():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf", type=Path, default=_DEFAULT_PDF, help="Source PDF to build a workspace from."
    )
    parser.add_argument(
        "--skill", default="general-report-writing", help="Report skill to run, under skills/."
    )
    parser.add_argument("--template", default="report.md", help="Template file to render.")
    parser.add_argument(
        "--model", default=None, help="LiteLLM model string. Defaults to REPORT_AGENT_MODEL."
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    # report_writing_collaborator.agent.agent builds a demo root_agent at import time (needed for
    # `adk run`/`adk web` discovery); a placeholder unblocks the import here,
    # since the real workspace built below is passed to write_report() directly.
    # Set before _load_env so a blank WORKSPACE_ROOT= line in .env doesn't win.
    os.environ["WORKSPACE_ROOT"] = os.environ.get("WORKSPACE_ROOT") or str(_REPO_ROOT)
    _load_env(_ENV_PATH)

    import canonical_workspace as cw
    from report_writing_collaborator.agent import report_orchestrator

    publish_root = _WORKSPACES_ROOT
    publish_root.mkdir(parents=True, exist_ok=True)
    manifest = cw.build_workspace(
        [cw.FileSource(path=args.pdf, source_instance_id="source_01")],
        cw.WorkspaceConfig(publish_root=publish_root),
    )
    workspace_dir = publish_root / manifest.workspace_id / str(manifest.workspace_version)
    print(f"Workspace: {workspace_dir}")

    result = report_orchestrator.write_report(
        workspace_dir,
        skill_name=args.skill,
        template_name=args.template,
        model=args.model,
    )
    print(f"Report: {result.report_path}")
    print(f"\n{_SEPARATOR}\n")
    print(result.text)


if __name__ == "__main__":
    main()
