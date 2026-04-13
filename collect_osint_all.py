from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = [
    "build_source_registry.py",
    "collector_research_graph.py",
    "collector_entity_intel.py",
    "collector_opportunities.py",
]


def main() -> int:
    code = 0
    for script in SCRIPTS:
        print(f"\n== Running {script} ==")
        result = subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT)
        if result.returncode != 0:
            code = result.returncode
    return code


if __name__ == "__main__":
    raise SystemExit(main())
