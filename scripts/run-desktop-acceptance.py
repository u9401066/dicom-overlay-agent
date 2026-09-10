"""Drive the real desktop App + harness viewer through an ordered case list.

This is the authorized real-machine acceptance path.  For every case the
driver:

1. Displays the exact image in the frameless ``DICOM Harness Viewer`` window
   (separate process, fixed position, 1:1 logical scale).
2. Lets the real desktop App capture its configured ROI through the real
   screen monitor, analyze it through the App-managed OpenClaw Gateway with
   the chosen provider profile, and export through the same code path as the
   control-bar Export button (``--auto-export``).
3. Records a per-case receipt row (case id, export directory, wall time,
   parsed severity/incomplete flags) so interrupted batches can resume.

No script-side model call, direct file upload, mock, or headless substitute
is used; the driver only orchestrates windows and watches the export folder.

Usage (from the repo root, inside ``uv run``):

    uv run python scripts/run-desktop-acceptance.py \
        --manifest data/eval-datasets/meeti-blind-v1/important-multi-128-v1.inference.json \
        --limit 1 --per-case-timeout-sec 600
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORT_ROOT = REPO_ROOT / "data" / "exports"
GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 18789
DEFAULT_PROFILE = "openai-codex-luna"
VIEWER_TITLE = "DICOM Harness Viewer"


@dataclass
class CaseReceipt:
    case_id: str
    image: str
    image_sha256: str
    status: str  # exported | timeout | error
    export_dir: str = ""
    wall_time_sec: float = 0.0
    severity: str = ""
    incomplete: bool | None = None
    review_required: bool | None = None
    findings: int = 0
    error: str = ""


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def _load_cases(manifest_path: Path) -> list[dict[str, str]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"Manifest has no cases: {manifest_path}")
    rows: list[dict[str, str]] = []
    for entry in cases:
        image = (manifest_path.parent / entry["image"]).resolve()
        if not image.is_file():
            raise FileNotFoundError(f"Case image missing: {image}")
        rows.append(
            {
                "case_id": str(entry.get("label") or image.stem),
                "image": str(image),
            }
        )
    return rows


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _gateway_port_in_use() -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(1.0)
    try:
        return probe.connect_ex((GATEWAY_HOST, GATEWAY_PORT)) == 0
    finally:
        probe.close()


def _apply_provider_profile(profile_key: str) -> None:
    from dicom_overlay.infrastructure.desktop_settings_store import (
        DesktopSettingsStore,
    )
    from dicom_overlay.infrastructure.openclaw_settings import (
        default_provider_profiles,
    )

    profile = next(
        (p for p in default_provider_profiles() if p.key == profile_key),
        None,
    )
    if profile is None:
        raise ValueError(f"Unknown provider profile: {profile_key}")
    store = DesktopSettingsStore(repo_root=REPO_ROOT)
    store.save_provider_profile(profile, api_key="", gateway_token="")


def _write_acceptance_config(run_dir: Path) -> Path:
    from dicom_overlay.presentation.harness_viewer import (
        DEFAULT_X,
        DEFAULT_Y,
        WINDOW_TITLE,
    )

    del DEFAULT_X, DEFAULT_Y  # positions are applied by the viewer, not config
    raw = yaml.safe_load((REPO_ROOT / "config.yaml").read_text(encoding="utf-8"))
    monitor = raw.setdefault("monitor", {})
    monitor["window_title_keywords"] = [WINDOW_TITLE]
    monitor["debounce_stable_sec"] = 1.0
    analysis = raw.setdefault("analysis", {})
    analysis["trigger_mode"] = "auto"
    overlay = raw.setdefault("overlay", {})
    overlay["tts_enabled"] = False
    debug = raw.setdefault("debug", {})
    debug["log_file"] = str(run_dir / "app.log")
    # The frameless viewer shows exactly the image; the ROI covers the whole
    # window content (margins 0) and scales with the actual window size.
    raw["phi_roi"] = {
        "configured": True,
        "coordinate_space": "viewer",
        "reference_width": 1000,
        "reference_height": 720,
        "top": 0,
        "bottom": 0,
        "left": 0,
        "right": 0,
    }
    config_path = run_dir / "config.acceptance.yaml"
    config_path.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return config_path


def _existing_exports() -> set[str]:
    if not EXPORT_ROOT.is_dir():
        return set()
    return {entry.name for entry in EXPORT_ROOT.iterdir() if entry.is_dir()}


def _wait_for_new_export(before: set[str], deadline: float) -> str:
    while time.monotonic() < deadline:
        current = _existing_exports() - before
        for name in sorted(current):
            result_file = EXPORT_ROOT / name / "result.json"
            if result_file.is_file() and result_file.stat().st_size > 0:
                return name
        time.sleep(2.0)
    return ""


def _wait_for_viewer_window(timeout_sec: float) -> bool:
    import win32gui

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if win32gui.FindWindow(None, VIEWER_TITLE):
            return True
        time.sleep(0.5)
    return False


def _capture_screen_evidence(export_dir: Path) -> None:
    """Best-effort external screenshot of the viewer area.

    The App's own top-most panels are excluded from external capture by
    design; this evidence pairs the visible viewer with the App-owned
    annotated ``review.png`` inside the export.
    """
    try:
        import mss
        import win32gui

        hwnd = win32gui.FindWindow(None, VIEWER_TITLE)
        if not hwnd:
            return
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        with mss.mss() as grabber:
            shot = grabber.grab(
                {
                    "left": left,
                    "top": top,
                    "width": max(1, right - left),
                    "height": max(1, bottom - top),
                }
            )
            mss.tools.to_png(shot.rgb, shot.size, output=str(export_dir / "screen.png"))
    except Exception as exc:
        print(f"[acceptance] screenshot skipped: {exc}", file=sys.stderr)


def _terminate(process: subprocess.Popen[bytes] | None, name: str) -> None:
    if process is None:
        return
    try:
        process.terminate()
        process.wait(timeout=15)
    except Exception:
        try:
            process.kill()
        except Exception:
            print(f"[acceptance] could not kill {name}", file=sys.stderr)


def _stop_owned_gateway() -> None:
    """Stop the Gateway this workspace launched, proven by its ownership receipt.

    Charge-safe rule: never terminate an unknown PID.  The receipt's
    ``listener_pid`` is only stopped after its command line proves it is this
    repository's own ``openclaw.mjs`` Node process.
    """
    receipt_path = REPO_ROOT / "data" / "tmp" / "openclaw-gateway.lock" / "ownership.json"
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        pid = int(receipt["listener_pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return
    try:
        import win32api
        import win32con
        import win32process

        handle = win32api.OpenProcess(
            win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_TERMINATE,
            False,
            pid,
        )
    except Exception:
        return  # already gone or not openable
    try:
        image = win32process.GetModuleFileNameEx(handle, 0)
        expected_node = str(REPO_ROOT / "node" / "node.exe")
        if not image.lower().endswith("node.exe") or not image.lower().startswith(
            str(REPO_ROOT).lower()
        ):
            print(
                f"[acceptance] refusing to stop PID {pid}: {image} is not the "
                f"bundled runtime ({expected_node})",
                file=sys.stderr,
            )
            return
        win32api.TerminateProcess(handle, 0)
    except Exception:
        print(f"[acceptance] owned Gateway PID {pid} did not stop", file=sys.stderr)
    finally:
        win32api.CloseHandle(handle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--per-case-timeout-sec", type=float, default=420.0)
    parser.add_argument("--first-case-timeout-sec", type=float, default=720.0)
    parser.add_argument("--profile-key", default=DEFAULT_PROFILE)
    parser.add_argument("--viewer-x", type=int, default=100)
    parser.add_argument("--viewer-y", type=int, default=100)
    parser.add_argument(
        "--receipt",
        type=Path,
        default=None,
        help="JSONL receipt path (default: <run-dir>/receipts.jsonl)",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Working directory (default: data/tmp/desktop-acceptance-<stamp>)",
    )
    parser.add_argument(
        "--screenshots",
        action="store_true",
        help="Capture an external viewer-area screenshot per exported case",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = args.run_dir or (
        REPO_ROOT / "data" / "tmp" / f"desktop-acceptance-{_utc_stamp()}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = args.receipt or (run_dir / "receipts.jsonl")

    cases = _load_cases(args.manifest)
    done: set[str] = set()
    if receipt_path.is_file():
        for line in receipt_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["case_id"])

    queue = [
        case
        for case in cases[args.start_index :]
        if case["case_id"] not in done
    ][: max(0, args.limit)]
    if not queue:
        print("[acceptance] nothing to do (already complete or empty selection)")
        return 0

    if _gateway_port_in_use():
        print(
            "[acceptance] Gateway port 18789 is already occupied; refusing to "
            "attach to or terminate an unknown listener. Close it and rerun.",
            file=sys.stderr,
        )
        return 2

    openclaw_config = REPO_ROOT / "openclaw" / "openclaw.json"
    config_snapshot = openclaw_config.read_bytes() if openclaw_config.is_file() else b""
    _apply_provider_profile(args.profile_key)
    acceptance_config = _write_acceptance_config(run_dir)
    swap_file = run_dir / "viewer-swap.txt"

    viewer: subprocess.Popen[bytes] | None = None
    app: subprocess.Popen[bytes] | None = None
    consecutive_failures = 0
    try:
        swap_file.write_text(queue[0]["image"], encoding="utf-8")
        viewer = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "dicom_overlay.presentation.harness_viewer",
                queue[0]["image"],
                "--x",
                str(args.viewer_x),
                "--y",
                str(args.viewer_y),
                "--swap-file",
                str(swap_file),
            ],
            cwd=REPO_ROOT,
        )
        if not _wait_for_viewer_window(20.0):
            print("[acceptance] viewer window never appeared", file=sys.stderr)
            return 3

        env = {key: value for key, value in os.environ.items() if key != "OPENAI_API_KEY"}
        app = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "dicom_overlay",
                "--config",
                str(acceptance_config),
                "--auto-export",
            ],
            cwd=REPO_ROOT,
            env=env,
        )

        with receipt_path.open("a", encoding="utf-8") as receipt_file:
            for index, case in enumerate(queue):
                started = time.monotonic()
                swap_file.write_text(case["image"], encoding="utf-8")
                before = _existing_exports()
                timeout = (
                    args.first_case_timeout_sec
                    if index == 0 and not done
                    else args.per_case_timeout_sec
                )
                export_name = _wait_for_new_export(before, started + timeout)
                receipt = CaseReceipt(
                    case_id=case["case_id"],
                    image=case["image"],
                    image_sha256=_sha256(Path(case["image"])),
                    status="exported" if export_name else "timeout",
                    wall_time_sec=round(time.monotonic() - started, 3),
                )
                if export_name:
                    export_dir = EXPORT_ROOT / export_name
                    receipt.export_dir = str(export_dir)
                    try:
                        result = json.loads(
                            (export_dir / "result.json").read_text(encoding="utf-8")
                        )
                        receipt.severity = str(result.get("severity", ""))
                        receipt.incomplete = result.get("incomplete")
                        receipt.review_required = result.get("review_required")
                        receipt.findings = len(result.get("findings") or [])
                    except Exception as exc:
                        receipt.status = "error"
                        receipt.error = f"result.json unreadable: {exc}"
                    if args.screenshots:
                        _capture_screen_evidence(export_dir)
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    receipt.error = f"no export within {timeout:.0f}s"
                receipt_file.write(
                    json.dumps(asdict(receipt), ensure_ascii=False) + "\n"
                )
                receipt_file.flush()
                print(
                    f"[acceptance] {index + 1}/{len(queue)} {case['case_id']}: "
                    f"{receipt.status} {receipt.wall_time_sec:.1f}s",
                    flush=True,
                )
                if consecutive_failures >= 3:
                    print(
                        "[acceptance] aborting after 3 consecutive failures",
                        file=sys.stderr,
                    )
                    return 4
        return 0
    finally:
        _terminate(app, "app")
        _terminate(viewer, "viewer")
        _stop_owned_gateway()
        if config_snapshot:
            openclaw_config.write_bytes(config_snapshot)


if __name__ == "__main__":
    raise SystemExit(main())
