from __future__ import annotations

import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _pytest_config() -> dict[str, object]:
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text("utf-8"))
    return pyproject["tool"]["pytest"]["ini_options"]


def test_local_pytest_defaults_avoid_heavy_integration_suite() -> None:
    config = _pytest_config()

    assert config["testpaths"] == ["tests/unit", "tests/smoke"]


def test_local_pytest_excludes_generated_and_vendored_trees() -> None:
    config = _pytest_config()
    excluded = set(config["norecursedirs"])

    assert {
        "data",
        "openclaw",
        "openclaw-home",
        ".uv-cache-codex",
        "node_modules",
        "dist",
        "build",
    } <= excluded


def test_local_pytest_output_stays_bounded_on_failures() -> None:
    config = _pytest_config()
    addopts = set(config["addopts"])

    assert "-v" not in addopts
    assert "--show-capture=no" in addopts
    assert "--tb=short" in addopts


def test_conftest_filters_structlog_debug_noise_by_default() -> None:
    conftest = (_REPO_ROOT / "tests" / "conftest.py").read_text("utf-8")

    assert "make_filtering_bound_logger(logging.WARNING)" in conftest


def test_safe_test_runner_pins_repo_local_cache_and_tmp_dirs() -> None:
    runner = (_REPO_ROOT / "scripts" / "run-tests-safe.ps1").read_text("utf-8")

    assert "UV_CACHE_DIR" in runner
    assert ".uv-cache-codex" in runner
    assert "UV_NO_PROGRESS" in runner
    assert "UV_PYTHON_DOWNLOADS" in runner
    assert "$env:TMP" in runner
    assert "$env:TEMP" in runner
    assert "--basetemp" in runner
    assert "-p" in runner
    assert "no:cacheprovider" in runner
    assert "tests/unit" in runner
    assert "tests/smoke" in runner
