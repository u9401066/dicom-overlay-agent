"""Packaging / portability smoke tests.

These verify the "USB plug-and-play" goal: the bundle can self-check that it
finds everything it needs to start (Node.js runtime, OpenClaw gateway script,
config, writable base) anchored to the executable folder — without launching
the GUI or contacting an LLM.

Two layers:
- ``test_selfcheck_reports_all_components`` runs the in-process self-check
  against the dev tree (fast, always runs). It proves the self-check wiring
  works and the config resolves; node/openclaw may legitimately be unstaged in
  CI, so those rows are reported but not hard-required here.
- ``test_built_bundle_selfcheck_exits_zero`` runs the *real built executable*
  with ``--selfcheck`` and requires exit code 0. It is **opt-in** via
  ``RUN_BUNDLE_SMOKE=1`` because (a) the ``dist/`` build may be stale relative
  to the source and (b) it spawns a windowed PyInstaller exe — neither belongs
  in the fast default suite. A release pipeline runs ``scripts/build-exe.bat``
  then sets ``RUN_BUNDLE_SMOKE=1`` to validate the freshly packaged bundle.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SMOKE_ERROR_MARKER = "PACKAGED_SMOKE_EXPECTED_AUTH_FAILURE"


@contextmanager
def _loopback_auth_failure_provider():
    requests: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            requests.append(
                {
                    "path": self.path,
                    "authorization": self.headers.get("Authorization", ""),
                    "body": body,
                }
            )
            payload = json.dumps(
                {
                    "error": {
                        "message": _SMOKE_ERROR_MARKER,
                        "type": "invalid_request_error",
                        "code": "invalid_api_key",
                    }
                }
            ).encode("utf-8")
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _write_loopback_smoke_config(root: Path, *, base_url: str) -> None:
    config = {
        "gateway": {"mode": "local"},
        "models": {
            "mode": "merge",
            "providers": {
                "packaging-smoke": {
                    "apiKey": {
                        "source": "env",
                        "provider": "default",
                        "id": "DICOM_OVERLAY_PACKAGING_SMOKE_API_KEY",
                    },
                    "baseUrl": base_url,
                    "api": "openai-responses",
                    "models": [
                        {
                            "id": "image-auth-failure",
                            "name": "Local packaging image smoke",
                            "input": ["text", "image"],
                            "reasoning": False,
                            "contextWindow": 128000,
                            "maxTokens": 4096,
                            "agentRuntime": {"id": "openclaw"},
                        }
                    ],
                }
            },
        },
        "agents": {
            "defaults": {
                "model": {
                    "primary": "packaging-smoke/image-auth-failure",
                    "fallbacks": [],
                },
                "models": {
                    "packaging-smoke/image-auth-failure": {
                        "alias": "Local packaging image smoke"
                    }
                },
                "imageMaxDimensionPx": 64,
                "timeoutSeconds": 30,
            }
        },
        "plugins": {
            "allow": ["dicom-overlay-agent-harness"],
            "entries": {"dicom-overlay-agent-harness": {"enabled": True}},
        },
        "tools": {"allow": ["dicom_bbox_validate"]},
    }
    path = root / "openclaw" / "openclaw.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _assert_clean_roi_seed(config_path: Path) -> None:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    roi = config["phi_roi"]
    assert roi["configured"] is False
    assert roi["coordinate_space"] == "viewer"
    assert roi["reference_width"] == 0
    assert roi["reference_height"] == 0
    assert all(roi[edge] == 0 for edge in ("top", "bottom", "left", "right"))


def test_shipped_config_requires_per_workstation_roi_setup():
    _assert_clean_roi_seed(_REPO_ROOT / "config.yaml")


def test_selfcheck_reports_all_components():
    from dicom_overlay.__main__ import _run_selfcheck

    config_path = _REPO_ROOT / "config.yaml"
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = _run_selfcheck(_REPO_ROOT, config_path)
    out = buffer.getvalue()

    # Every component the bundle needs is reported on.
    for component in (
        "base_dir",
        "config.yaml",
        "skills",
        "harness_plugin",
        "clinical_rules",
        "clinical_knowledge",
        "node",
        "openclaw",
        "openclaw_bundled_skills",
        "openclaw_plugin_surfaces",
        "openclaw_workspace_templates",
        "harness_native_plugin",
        "writable_base",
    ):
        assert component in out, f"self-check did not report {component}\n{out}"

    # Config + writable base must be OK in the dev tree (they ship in the repo);
    # node/openclaw may be unstaged in CI, so the overall code can be 0 or 1.
    assert "RESULT:" in out
    assert config_path.exists()
    assert code in (0, 1)


def test_windowed_selfcheck_and_rule_audit_do_not_require_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dicom_overlay.__main__ import _run_explain_rules, _run_selfcheck

    monkeypatch.setattr(sys, "stdout", None)

    assert _run_selfcheck(_REPO_ROOT, _REPO_ROOT / "config.yaml") in (0, 1)
    assert _run_explain_rules(_REPO_ROOT) == 0


def test_package_runtime_smoke_handles_windowed_logging_and_image_surfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dicom_overlay.infrastructure.package_runtime_smoke import (
        run_package_runtime_smoke,
    )

    # PyInstaller's windowed bootloader exposes no stderr. Logging must still
    # initialize, while the actual PNG/JPEG/font/review surfaces remain usable.
    monkeypatch.setattr(sys, "stderr", None)
    report = run_package_runtime_smoke(tmp_path)

    assert report == {
        "status": "ok",
        "checks": {
            "logging_init": True,
            "png_encode_decode": True,
            "jpeg_decode": True,
            "font_render": True,
            "review_export": True,
            "harness_contract": True,
        },
        "failures": [],
    }


def test_package_runtime_smoke_rejects_missing_harness_resources(tmp_path, monkeypatch):
    from dicom_overlay.infrastructure.package_runtime_smoke import (
        run_package_runtime_smoke,
    )
    from medical_image_harness import resources

    def missing_skill():
        raise FileNotFoundError("synthetic missing harness resource")

    monkeypatch.setattr(resources, "load_skill", missing_skill)
    report = run_package_runtime_smoke(tmp_path)
    assert report["status"] == "failed"
    assert report["checks"]["harness_contract"] is False
    assert any("harness_contract" in item for item in report["failures"])


def test_bootstrap_config_load_handles_windowed_process_streams(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("log_level: INFO\n", encoding="utf-8")
    code = """
import sys
from pathlib import Path
from dicom_overlay.infrastructure.config_loader import load_config
from dicom_overlay.infrastructure.logging_config import setup_bootstrap_logging
sys.stdout = None
sys.stderr = None
setup_bootstrap_logging()
config = load_config(Path(sys.argv[1]))
raise SystemExit(0 if config.log_level == "INFO" else 2)
"""

    result = subprocess.run(
        [sys.executable, "-c", code, str(config_path)],
        cwd=_REPO_ROOT,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0


def test_gateway_image_smoke_rejects_real_credentials_and_non_loopback_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dicom_overlay.__main__ import _packaging_smoke_configuration_error

    for name in (
        "OPENAI_API_KEY",
        "CODEX_HOME",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        "DICOM_OVERLAY_PACKAGING_SMOKE_MODE",
        "loopback-provider-auth-failure-v1",
    )
    monkeypatch.setenv(
        "DICOM_OVERLAY_PACKAGING_SMOKE_API_KEY",
        "invalid-packaging-smoke-key",
    )
    _write_loopback_smoke_config(tmp_path, base_url="http://127.0.0.1:9/v1")

    assert _packaging_smoke_configuration_error(tmp_path) == ""

    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    assert "real provider credentials" in _packaging_smoke_configuration_error(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY")
    _write_loopback_smoke_config(tmp_path, base_url="https://api.openai.com/v1")
    assert "loopback" in _packaging_smoke_configuration_error(tmp_path)


def _built_exe() -> Path | None:
    if sys.platform != "win32":
        return None
    bundle = Path(
        os.environ.get("DICOM_TEST_BUNDLE", str(_REPO_ROOT / "dist/DICOMOverlayAgent"))
    ).resolve()
    exe = bundle / "DICOMOverlayAgent.exe"
    return exe if exe.exists() else None


@pytest.mark.parametrize(
    "error_text,run_id,templates,expected",
    [
        ("expected", "synthetic-run", True, 0),
        ("expected", "synthetic-run", "without-bootstrap", 0),
        ("expected", "", True, 1),
        ("expected", "synthetic-run", False, 1),
        ("HTTP 401", "synthetic-run", True, 1),
        ("PACKAGED_SMOKE_EXPECTED_AUTH_FAILURE", "synthetic-run", True, 1),
        ("Authentication failed for a different provider", "synthetic-run", True, 1),
        ("Missing bootstrap template", "synthetic-run", True, 1),
        ("", "synthetic-run", True, 1),
        (None, "synthetic-run", True, 1),
    ],
)
def test_gateway_smoke_requires_exact_public_auth_error_and_run_receipts(
    tmp_path, monkeypatch, error_text, run_id, templates, expected
):
    from dicom_overlay import __main__ as app
    from dicom_overlay.domain.entities import AppConfig

    events = []

    class Gateway:
        def start(self):
            events.append("start")

        async def wait_ready(self):
            return True

        def stop(self):
            events.append("stop")

    class Client:
        async def connect(self):
            events.append("connect")

        async def chat_about_image(self, _prompt, *, image_base64):
            assert image_base64 == app._PACKAGING_SMOKE_PNG_BASE64
            if error_text is not None:
                raise RuntimeError(
                    app._PACKAGING_SMOKE_AUTH_ERROR
                    if error_text == "expected"
                    else error_text
                )
            return "unexpected successful inference"

        async def disconnect(self):
            events.append("disconnect")

        def last_run_trace(self):
            return {"run_id": run_id}

    monkeypatch.setattr(app, "_packaging_smoke_configuration_error", lambda _: "")
    monkeypatch.setattr(
        app.DesktopSettingsStore,
        "ensure_gateway_token",
        lambda _: "synthetic-gateway-token",
    )
    monkeypatch.setattr(app, "_configured_gateway", lambda *_: Gateway())
    monkeypatch.setattr(app, "OpenClawClient", lambda **_: Client())
    if templates:
        workspace = tmp_path / "openclaw-home/.openclaw/workspace"
        workspace.mkdir(parents=True)
        for name in app._OPENCLAW_RUNTIME_TEMPLATE_PATHS:
            if templates == "without-bootstrap" and name == "BOOTSTRAP.md":
                continue
            (workspace / name).write_text("Synthetic bootstrap", encoding="utf-8")
    assert (
        app._run_gateway_smoke(tmp_path, tmp_path / "config.yaml", AppConfig())
        == expected
    )
    assert events == ["start", "connect", "disconnect", "stop"]


@pytest.mark.skipif(
    os.environ.get("RUN_BUNDLE_SMOKE") != "1" or _built_exe() is None,
    reason=(
        "Opt-in: set RUN_BUNDLE_SMOKE=1 after scripts/build-exe.bat to validate "
        "the freshly built dist/ bundle"
    ),
)
def test_built_bundle_selfcheck_exits_zero():
    exe = _built_exe()
    assert exe is not None
    bundle = exe.parent
    _assert_clean_roi_seed(bundle / "config.yaml")
    assert not (bundle / "overlay_agent.log").exists()
    assert not (bundle / "openclaw-home").exists()
    result = subprocess.run(
        [str(exe), "--selfcheck"],
        cwd=str(exe.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    # A complete portable bundle finds node + openclaw + config + writable base.
    assert result.returncode == 0, (
        f"bundle self-check failed (exit {result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}"
    )
    assert not (bundle / "overlay_agent.log").exists()
    assert not (bundle / "openclaw-home").exists()


@pytest.mark.skipif(
    os.environ.get("RUN_BUNDLE_SMOKE") != "1" or _built_exe() is None,
    reason=(
        "Opt-in: set RUN_BUNDLE_SMOKE=1 after scripts/build-exe.bat to validate "
        "the freshly built frozen codecs, logging, fonts, and review export"
    ),
)
def test_built_bundle_package_runtime_smoke_exits_zero():
    exe = _built_exe()
    assert exe is not None
    bundle = exe.parent
    result = subprocess.run(
        [str(exe), "--package-runtime-smoke"],
        cwd=str(bundle),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    assert result.returncode == 0, (
        f"bundle package-runtime smoke failed (exit {result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}"
    )
    assert not (bundle / "runtime-smoke.log").exists()
    assert not (bundle / "review").exists()


@pytest.mark.skipif(
    os.environ.get("RUN_GATEWAY_BUNDLE_SMOKE") != "1" or _built_exe() is None,
    reason=(
        "Opt-in: set RUN_GATEWAY_BUNDLE_SMOKE=1 after scripts/build-exe.bat "
        "to start and authenticate to the packaged Gateway"
    ),
)
def test_built_bundle_gateway_smoke_isolated(tmp_path: Path):
    exe = _built_exe()
    assert exe is not None
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        gateway_port = reservation.getsockname()[1]
    isolated = shutil.copytree(exe.parent, tmp_path / "DICOMOverlayAgent")
    isolated_exe = isolated / exe.name
    config_path = isolated / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["openclaw"]["gateway_url"] = f"ws://127.0.0.1:{gateway_port}"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    env = os.environ.copy()
    for name in (
        "OPENCLAW_GATEWAY_TOKEN",
        "OPENAI_API_KEY",
        "CODEX_HOME",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        env.pop(name, None)
    env.update(
        {
            "DICOM_OVERLAY_PACKAGING_SMOKE_MODE": ("loopback-provider-auth-failure-v1"),
            "DICOM_OVERLAY_PACKAGING_SMOKE_API_KEY": ("invalid-packaging-smoke-key"),
        }
    )

    with _loopback_auth_failure_provider() as (base_url, provider_requests):
        _write_loopback_smoke_config(isolated, base_url=base_url)
        result = subprocess.run(
            [str(isolated_exe), "--gateway-smoke"],
            cwd=isolated,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )

    gateway_log = (isolated / "gateway.log").read_text(
        encoding="utf-8", errors="replace"
    )
    assert result.returncode == 0, (
        f"packaged Gateway smoke failed (exit {result.returncode}):\n"
        f"{result.stdout}\n{result.stderr}\n{gateway_log}"
    )
    assert "OPENCLAW_GATEWAY_TOKEN=" in (isolated / ".env").read_text(encoding="utf-8")
    assert "[gateway] ready" in gateway_log
    assert provider_requests, "image turn never reached the loopback provider"
    assert all(
        request["authorization"] == "Bearer invalid-packaging-smoke-key"
        for request in provider_requests
    )
    from dicom_overlay.__main__ import _PACKAGING_SMOKE_PNG_BASE64

    expected_image = "data:image/png;base64," + _PACKAGING_SMOKE_PNG_BASE64
    images = [
        part["image_url"]
        for request in provider_requests
        for message in json.loads(request["body"])["input"]
        for part in message.get("content", [])
        if isinstance(part, dict) and part.get("type") == "input_image"
    ]
    assert images and all(image == expected_image for image in images), (
        "loopback provider request did not contain the exact synthetic PNG"
    )
    assert "Registered plugin command: /codex" not in gateway_log
    assert "[plugins] loading codex " not in gateway_log
    app_log = (isolated / "overlay_agent.log").read_text(
        encoding="utf-8", errors="replace"
    )
    assert "packaged_gateway_image_turn_smoke" in app_log
    assert "template_count=4" in app_log
    assert "packaged_template_count=5" in app_log
    assert "image_attachment=True" in app_log
    workspace = isolated / "openclaw-home" / ".openclaw" / "workspace"
    assert all(
        (workspace / name).is_file()
        for name in (
            "AGENTS.md",
            "SOUL.md",
            "IDENTITY.md",
            "USER.md",
        )
    )
    deadline = time.monotonic() + 15
    while _port_open(gateway_port) and time.monotonic() < deadline:
        time.sleep(0.25)
    assert not _port_open(gateway_port), (
        "packaged Gateway process remained after smoke exit"
    )


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False
