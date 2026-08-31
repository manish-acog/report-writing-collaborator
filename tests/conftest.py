"""Makes src/report_writing_agent/ importable in tests.

It is packaged alongside report_writing_collaborator but remains the ADK
interface layer, matching ADK's own agent-project layout.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# src/report_writing_agent/agent.py builds a demo root_agent at import time
# (required for `adk run`/`adk web` discovery) from WORKSPACE_ROOT. Tests
# build their own agents via build_agent() against real tmp_path
# workspaces; this placeholder only lets the module import without crashing.
os.environ.setdefault("WORKSPACE_ROOT", str(Path(__file__).parent))
