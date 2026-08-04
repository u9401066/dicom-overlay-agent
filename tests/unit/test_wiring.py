"""Wiring guard: every application-layer orchestrator must be reachable.

A recurring failure mode in this codebase is the *orphan feature*: a class is
built, tested, and documented, but never actually wired into the runtime entry
point (``__main__.py``). The product then advertises a capability it never
runs.

This guard enumerates the public *orchestrator* classes in the application layer
and asserts that each one is either:

* **WIRED** — its name appears in ``__main__.py`` source (proven reachable), or
* **DEFERRED** — explicitly registered in :data:`DEFERRED_WIRING` with a reason.

A new orchestrator that is neither wired nor registered fails this test,
forcing an honest decision instead of a silent orphan. Pure value objects
(``@dataclass``) and structural interfaces (``Protocol``) are not orchestrators
and are excluded.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import pkgutil
from pathlib import Path

import dicom_overlay.application as application_pkg

# Orchestrators that are intentionally NOT wired yet. Each MUST carry a reason
# explaining why and what unblocks it. Keep this list short and honest — it is
# the project's ledger of known gaps, not a place to silence the guard.
DEFERRED_WIRING: dict[str, str] = {}


def _main_source() -> str:
    main_path = Path(application_pkg.__file__).resolve().parent.parent / "__main__.py"
    return main_path.read_text(encoding="utf-8")


def _is_orchestrator(obj: type) -> bool:
    """Public, non-DTO, non-Protocol class = an orchestrator we must account for."""
    if obj.__name__.startswith("_"):
        return False
    if dataclasses.is_dataclass(obj):
        return False
    return not getattr(obj, "_is_protocol", False)


def _application_orchestrators() -> dict[str, type]:
    found: dict[str, type] = {}
    for mod_info in pkgutil.iter_modules(application_pkg.__path__):
        module = importlib.import_module(f"{application_pkg.__name__}.{mod_info.name}")
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # Only classes actually defined in this module (skip imports).
            if obj.__module__ != module.__name__:
                continue
            if _is_orchestrator(obj):
                found[name] = obj
    return found


def test_every_application_orchestrator_is_wired_or_deferred() -> None:
    source = _main_source()
    orchestrators = _application_orchestrators()
    assert orchestrators, "no orchestrators discovered — guard would be vacuous"

    orphans: list[str] = []
    for name in orchestrators:
        wired = name in source
        deferred = name in DEFERRED_WIRING
        if not wired and not deferred:
            orphans.append(name)

    assert not orphans, (
        "Orphan orchestrator(s) found — built/tested but never wired into "
        f"__main__.py and not registered as deferred: {sorted(orphans)}. "
        "Either wire them into the runtime or add a DEFERRED_WIRING entry "
        "with a reason."
    )


def test_deferred_entries_have_reasons() -> None:
    for name, reason in DEFERRED_WIRING.items():
        assert reason.strip(), f"DEFERRED_WIRING['{name}'] needs a non-empty reason"


def test_deferred_entries_are_real_orchestrators() -> None:
    """A deferred name must be an actual current orchestrator, not stale."""
    orchestrators = _application_orchestrators()
    stale = [name for name in DEFERRED_WIRING if name not in orchestrators]
    assert not stale, (
        f"DEFERRED_WIRING lists symbols that are no longer application "
        f"orchestrators (remove them): {stale}"
    )


def test_multi_pass_is_wired() -> None:
    """Regression: the multi-pass interpreter must stay reachable from __main__."""
    source = _main_source()
    assert "MultiPassInterpreter" in source
    assert "MultiPassAnalyzer" in source
    assert "openclaw_client.refine" in source
    assert "review_region_about_image_with_trace" in source
