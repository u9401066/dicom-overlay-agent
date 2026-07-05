from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _pytest_config() -> dict[str, object]:
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text("utf-8"))
    return pyproject["tool"]["pytest"]["ini_options"]


def _load_pytest_safe_runner():
    runner_path = _REPO_ROOT / "scripts" / "run_pytest_safe.py"
    spec = importlib.util.spec_from_file_location("run_pytest_safe", runner_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_safe_test_runner_cmd_avoids_powershell_for_oom_recovery() -> None:
    runner = (_REPO_ROOT / "scripts" / "run-tests-safe.cmd").read_text("utf-8")

    assert "set \"UV_CACHE_DIR=%REPO_ROOT%\\.uv-cache-codex\"" in runner
    assert "set \"UV_NO_PROGRESS=1\"" in runner
    assert "set \"UV_PYTHON_DOWNLOADS=never\"" in runner
    assert "set \"TMP=%REPO_ROOT%\\data\\tmp\\pytest-safe\"" in runner
    assert "set \"TEMP=%REPO_ROOT%\\data\\tmp\\pytest-safe\"" in runner
    assert "set \"DICOM_OVERLAY_TEST_DISABLE_REAL_OPENCLAW=1\"" in runner
    assert "set \"PYTHON_EXE=%REPO_ROOT%\\.venv\\Scripts\\python.exe\"" in runner
    assert "scripts\\run_pytest_safe.py" in runner
    assert "\"%PYTHON_EXE%\" -m pytest" not in runner
    assert "uv run" not in runner
    assert "PYTEST_ARGS=tests/unit tests/smoke" not in runner
    assert 'if not "%~1"=="" set "PYTEST_ARGS=%*"' not in runner
    assert "basetemp-%RANDOM%" in runner
    assert "PYTEST_RUN_LOCK=%REPO_ROOT%\\data\\tmp\\pytest-run.lock" in runner
    assert 'mkdir "%PYTEST_RUN_LOCK%"' in runner
    assert "Another pytest command is already running" in runner
    assert 'rmdir "%PYTEST_RUN_LOCK%"' in runner
    assert ".ps1" not in runner.lower()
    assert "powershell" not in runner.lower()


def test_safe_pytest_helper_batches_default_suite_when_only_options_are_passed() -> None:
    runner = _load_pytest_safe_runner()

    batches = runner.build_pytest_batches(["-q"], root=_REPO_ROOT)

    assert len(batches) >= 2
    assert all(batch[-1] == "-q" for batch in batches)
    assert any("tests/unit/test_agent.py" in batch[0].replace("\\", "/") for batch in batches)


def test_safe_pytest_helper_keeps_cache_and_temp_controls_in_child_pytest() -> None:
    helper = (_REPO_ROOT / "scripts" / "run_pytest_safe.py").read_text("utf-8")

    assert "no:cacheprovider" in helper
    assert "--basetemp" in helper
    assert "PYTEST_BASETEMP" in helper


def test_safe_pytest_helper_keeps_default_unit_and_smoke_scope() -> None:
    runner = _load_pytest_safe_runner()

    assert runner.DEFAULT_TEST_DIRS == ("tests/unit", "tests/smoke")


def test_safe_pytest_helper_keeps_explicit_targets_in_one_pytest_session() -> None:
    runner = _load_pytest_safe_runner()

    batches = runner.build_pytest_batches(
        ["tests/unit/test_test_runner_config.py", "-q"],
        root=_REPO_ROOT,
    )

    assert batches == [["tests/unit/test_test_runner_config.py", "-q"]]


def test_safe_pytest_helper_batches_explicit_test_directories() -> None:
    runner = _load_pytest_safe_runner()

    batches = runner.build_pytest_batches(["tests/unit", "-q"], root=_REPO_ROOT)

    assert len(batches) >= 2
    assert all(batch[-1] == "-q" for batch in batches)
    assert any("tests/unit/test_agent.py" in batch[0].replace("\\", "/") for batch in batches)
    assert all(batch[0].replace("\\", "/").startswith("tests/unit/") for batch in batches)


def test_safe_pytest_helper_batches_explicit_tests_tree() -> None:
    runner = _load_pytest_safe_runner()

    batches = runner.build_pytest_batches(["tests", "-q"], root=_REPO_ROOT)

    assert len(batches) >= 2
    assert all(batch[-1] == "-q" for batch in batches)
    assert any("tests/unit/test_agent.py" in batch[0].replace("\\", "/") for batch in batches)
    assert any("tests/smoke/test_mvp_smoke.py" in batch[0].replace("\\", "/") for batch in batches)


def test_safe_pytest_helper_batches_multiple_explicit_test_files() -> None:
    runner = _load_pytest_safe_runner()

    batches = runner.build_pytest_batches(
        [
            "tests/unit/test_agent.py",
            "tests/unit/test_annotation_exporter.py",
            "-q",
        ],
        root=_REPO_ROOT,
    )

    assert batches == [
        ["tests/unit/test_agent.py", "-q"],
        ["tests/unit/test_annotation_exporter.py", "-q"],
    ]


def test_safe_ruff_runner_cmd_avoids_appdata_and_serializes_uv() -> None:
    runner = (_REPO_ROOT / "scripts" / "run-ruff-safe.cmd").read_text("utf-8")

    assert "set \"UV_CACHE_DIR=%REPO_ROOT%\\.uv-cache-codex\"" in runner
    assert "set \"UV_NO_PROGRESS=1\"" in runner
    assert "set \"UV_PYTHON_DOWNLOADS=never\"" in runner
    assert "set \"TMP=%REPO_ROOT%\\data\\tmp\\uv\"" in runner
    assert "set \"TEMP=%REPO_ROOT%\\data\\tmp\\uv\"" in runner
    assert "RUFF_EXE=%REPO_ROOT%\\.venv\\Scripts\\ruff.exe" in runner
    assert "RUFF_RUN_LOCK=%REPO_ROOT%\\data\\tmp\\ruff-run.lock" in runner
    assert 'mkdir "%RUFF_RUN_LOCK%"' in runner
    assert "Another ruff command is already running" in runner
    assert 'rmdir "%RUFF_RUN_LOCK%"' in runner
    assert "\"%RUFF_EXE%\" %*" in runner
    assert "uv run" not in runner
    assert "AppData" not in runner
    assert ".ps1" not in runner.lower()
    assert "powershell" not in runner.lower()
