#!/usr/bin/env python3
"""CLI wrapper for repo-root ``noteval_index_preview.py``."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

runpy.run_path(str(_REPO_ROOT / "noteval_index_preview.py"), run_name="__main__")
