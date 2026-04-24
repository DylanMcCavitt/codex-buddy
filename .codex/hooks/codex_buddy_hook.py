#!/usr/bin/env python3
"""Forward Codex hook events to the local Codex Buddy bridge.

This script is intentionally best-effort. It must never block or alter Codex
behavior if the bridge is not running.
"""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if SRC.exists():
    sys.path.insert(0, str(SRC))

from codex_buddy_bridge.hook import main


if __name__ == "__main__":
    raise SystemExit(main())
