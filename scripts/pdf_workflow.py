"""
Thin wrapper — canonical script: ``noteval_extractor/scripts/pdf_workflow.py``.

Keeps ``scripts/pdf_workflow.py`` working for older docs and habits.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_CANON = Path(__file__).resolve().parent.parent / "noteval_extractor" / "scripts" / "pdf_workflow.py"


def main() -> None:
    if not _CANON.is_file():
        print(
            f"ERROR: Missing {_CANON}\n"
            "Use noteval_extractor/scripts/pdf_workflow.py from the repo root.",
            file=sys.stderr,
        )
        sys.exit(1)
    raise SystemExit(subprocess.call([sys.executable, str(_CANON), *sys.argv[1:]]))


if __name__ == "__main__":
    main()
