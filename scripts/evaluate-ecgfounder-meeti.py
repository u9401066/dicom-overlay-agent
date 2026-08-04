#!/usr/bin/env python3
"""Run the leakage-aware ECGFounder MEETI research evaluation."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _main() -> int:
    module = importlib.import_module("sidecars.ecgfounder.evaluate")
    return int(module.main())


if __name__ == "__main__":
    raise SystemExit(_main())
