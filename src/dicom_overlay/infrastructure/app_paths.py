"""Application base-directory resolution for portable (USB) deployment.

When the agent runs as a PyInstaller bundle, the user double-clicks
``DICOMOverlayAgent.exe`` from wherever the folder happens to live (a USB
drive, ``C:\\Tools``, the Desktop, ...). The current working directory in that
situation is **not** guaranteed to be the folder containing the executable —
depending on how Windows launches it, ``cwd`` can be ``C:\\Windows\\System32``.
Resolving writable runtime paths (``config.yaml``, ``openclaw-home``,
``data/jobs``, logs, settings overrides) against ``cwd`` would then read/write
the wrong location and break "plug-and-play" startup on a fresh machine.

To make the bundle portable, runtime paths must be anchored to the directory
that contains the executable, not to ``cwd``. In development (not frozen) we
keep using ``cwd`` so ``uv run`` and tests behave exactly as before.
"""

from __future__ import annotations

from pathlib import Path


def resolve_app_base_dir(
    *,
    frozen: bool,
    executable: str,
    cwd: Path,
) -> Path:
    """Return the base directory runtime paths should resolve against.

    Pure function so the portability rule is unit-testable without a real
    frozen build.

    - Frozen (PyInstaller bundle): the folder containing the executable, so the
      app finds its bundled ``config.yaml`` and writes ``openclaw-home`` /
      ``data`` next to itself regardless of the launch ``cwd``.
    - Not frozen (dev / tests): the current working directory, preserving the
      existing ``uv run`` behaviour.
    """
    if frozen:
        return Path(executable).resolve().parent
    return cwd


def app_base_dir() -> Path:
    """Resolve the application base directory for the current process."""
    import sys

    return resolve_app_base_dir(
        frozen=bool(getattr(sys, "frozen", False)),
        executable=sys.executable,
        cwd=Path.cwd(),
    )
