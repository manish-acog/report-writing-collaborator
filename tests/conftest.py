"""Makes report_writing_agent/ importable in tests.

It isn't part of the installed report_writing_collaborator package (see
agent_execution_over_adk.md) — it's a plain top-level directory, matching
ADK's own agent-project layout.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# report_writing_agent/agent.py builds a demo root_agent at import time
# (required for `adk run`/`adk web` discovery) from WORKSPACE_ROOT. Tests
# build their own agents via build_agent() against real tmp_path
# workspaces; this placeholder only lets the module import without crashing.
os.environ.setdefault("WORKSPACE_ROOT", str(Path(__file__).parent))
