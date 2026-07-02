from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DEFAULT_TEST_DIRS = ("tests/unit", "tests/smoke")
PYTEST_BASE_ARGS = ("-p", "no:cacheprovider")


def _looks_like_explicit_target(arg: str) -> bool:
    if arg.startswith("-"):
        return False

    normalized = arg.replace("\\", "/")
    return (
        "::" in normalized
        or normalized.endswith(".py")
        or normalized == "tests"
        or normalized.startswith("tests/")
    )


def _relative_test_file(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def collect_default_test_files(root: Path) -> list[str]:
    files: list[str] = []
    for test_dir in DEFAULT_TEST_DIRS:
        files.extend(
            _relative_test_file(path, root)
            for path in sorted((root / test_dir).glob("test_*.py"))
        )
    return files


def build_pytest_batches(args: list[str], *, root: Path) -> list[list[str]]:
    arg_list = list(args)
    force_single = os.environ.get("DICOM_OVERLAY_TEST_SINGLE_SESSION") == "1"

    if force_single or any(_looks_like_explicit_target(arg) for arg in arg_list):
        return [arg_list or list(DEFAULT_TEST_DIRS)]

    default_files = collect_default_test_files(root)
    if not default_files:
        return [list(DEFAULT_TEST_DIRS) + arg_list]

    return [[test_file, *arg_list] for test_file in default_files]


def _pytest_command(batch: list[str], *, batch_index: int) -> list[str]:
    command = [sys.executable, "-m", "pytest", *PYTEST_BASE_ARGS]
    basetemp = os.environ.get("PYTEST_BASETEMP")
    if basetemp:
        command.extend(["--basetemp", f"{basetemp}-{batch_index:03d}"])
    command.extend(batch)
    return command


def run(args: list[str], *, root: Path) -> int:
    batches = build_pytest_batches(args, root=root)
    for index, batch in enumerate(batches, start=1):
        print(
            f"[run-pytest-safe] batch {index}/{len(batches)}: {' '.join(batch)}",
            flush=True,
        )
        completed = subprocess.run(_pytest_command(batch, batch_index=index), cwd=root)
        if completed.returncode != 0:
            return completed.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    return run(sys.argv[1:] if argv is None else argv, root=root)


if __name__ == "__main__":
    raise SystemExit(main())
