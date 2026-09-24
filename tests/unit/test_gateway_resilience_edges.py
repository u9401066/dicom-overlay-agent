from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import websockets

from dicom_overlay.infrastructure import openclaw_client as openclaw_client_module
from dicom_overlay.infrastructure.gateway_manager import GatewayManager
from dicom_overlay.infrastructure.openclaw_client import (
    BboxEvidenceError,
    OpenClawClient,
    _bbox_coordinates_digest,
    probe_openclaw_gateway,
)
from medical_image_harness.models import (
    AnalysisResult,
    Finding,
    Modality,
    RegionRect,
    Severity,
)


class _FakeProcess:
    def __init__(self, pid: int = 4321) -> None:
        self.pid = pid
        self.returncode: int | None = None
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_timeouts: list[float | None] = []

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.returncode = 0

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        self.wait_timeouts.append(timeout)
        return int(self.returncode or 0)


def test_gateway_health_probe_uses_public_connect_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SyncWebSocket:
        def __init__(self) -> None:
            self.sent: dict[str, Any] = {}

        def __enter__(self) -> SyncWebSocket:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def send(self, raw: str) -> None:
            self.sent = json.loads(raw)

        def recv(self, *, timeout: float) -> str:
            assert timeout > 0
            return json.dumps(
                {
                    "type": "res",
                    "id": self.sent["id"],
                    "ok": True,
                    "payload": {
                        "type": "hello-ok",
                        "protocol": 4,
                        "server": {"version": "2026.7.1-2"},
                    },
                }
            )

    websocket = SyncWebSocket()
    monkeypatch.setattr(
        "dicom_overlay.infrastructure.openclaw_client.sync_websocket_connect",
        lambda *_args, **_kwargs: websocket,
    )

    assert probe_openclaw_gateway(
        "ws://127.0.0.1:18789",
        gateway_token="test-token",
    )
    assert websocket.sent["method"] == "connect"
    assert websocket.sent["params"]["minProtocol"] == 3
    assert websocket.sent["params"]["maxProtocol"] == 4
    assert websocket.sent["params"]["auth"] == {"token": "test-token"}


def test_gateway_health_probe_rejects_generic_success_without_hello_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SyncWebSocket:
        def __init__(self) -> None:
            self.sent: dict[str, Any] = {}

        def __enter__(self) -> SyncWebSocket:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def send(self, raw: str) -> None:
            self.sent = json.loads(raw)

        def recv(self, *, timeout: float) -> str:
            assert timeout > 0
            return json.dumps(
                {
                    "type": "res",
                    "id": self.sent["id"],
                    "ok": True,
                    "payload": {"status": "connected"},
                }
            )

    monkeypatch.setattr(
        "dicom_overlay.infrastructure.openclaw_client.sync_websocket_connect",
        lambda *_args, **_kwargs: SyncWebSocket(),
    )

    assert not probe_openclaw_gateway("ws://127.0.0.1:18789")


@pytest.mark.parametrize(
    ("version", "protocol"),
    [
        ("2026.4.21", 3),
        ("mock-2026.7.1-2", 4),
        ("2026.7.1-2", 3),
        ("2026.9.3", 3),
    ],
)
def test_gateway_health_probe_rejects_unsafe_hello_receipt(
    monkeypatch: pytest.MonkeyPatch,
    version: str,
    protocol: int,
) -> None:
    class SyncWebSocket:
        def __init__(self) -> None:
            self.sent: dict[str, Any] = {}

        def __enter__(self) -> SyncWebSocket:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def send(self, raw: str) -> None:
            self.sent = json.loads(raw)

        def recv(self, *, timeout: float) -> str:
            assert timeout > 0
            return json.dumps(
                {
                    "type": "res",
                    "id": self.sent["id"],
                    "ok": True,
                    "payload": {
                        "type": "hello-ok",
                        "protocol": protocol,
                        "server": {"version": version},
                    },
                }
            )

    monkeypatch.setattr(
        "dicom_overlay.infrastructure.openclaw_client.sync_websocket_connect",
        lambda *_args, **_kwargs: SyncWebSocket(),
    )

    assert not probe_openclaw_gateway("ws://127.0.0.1:18789")


def test_gateway_manager_does_not_reuse_gateway_below_version_floor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class OldGatewayWebSocket:
        def __init__(self) -> None:
            self.sent: dict[str, Any] = {}

        def __enter__(self) -> OldGatewayWebSocket:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def send(self, raw: str) -> None:
            self.sent = json.loads(raw)

        def recv(self, *, timeout: float) -> str:
            assert timeout > 0
            return json.dumps(
                {
                    "type": "res",
                    "id": self.sent["id"],
                    "ok": True,
                    "payload": {
                        "type": "hello-ok",
                        "protocol": 3,
                        "server": {"version": "2026.4.21"},
                    },
                }
            )

    monkeypatch.setenv("DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS", "1")
    monkeypatch.setattr(
        "dicom_overlay.infrastructure.openclaw_client.sync_websocket_connect",
        lambda *_args, **_kwargs: OldGatewayWebSocket(),
    )
    manager = GatewayManager(repo_root=tmp_path)
    monkeypatch.setattr(manager, "_port_occupant_pids", lambda: {321})

    with pytest.raises(RuntimeError, match="unhealthy or non-OpenClaw"):
        manager.start()

    assert manager._reused_gateway is False
    assert manager._process is None
    assert not (tmp_path / "data/tmp/openclaw-gateway.lock").exists()


def test_gateway_manager_probe_resolves_literal_config_token_without_logging_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)
    config_path = tmp_path / "openclaw/openclaw.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps({"gateway": {"auth": {"token": "literal-test-token"}}}),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def probe(url: str, **kwargs: object) -> bool:
        captured["url"] = url
        captured.update(kwargs)
        return True

    monkeypatch.setattr(openclaw_client_module, "probe_openclaw_gateway", probe)
    manager = GatewayManager(repo_root=tmp_path)

    assert manager._probe_existing_gateway() is True
    assert captured["gateway_token"] == "literal-test-token"


def test_gateway_reuses_authenticated_live_lock_without_terminating_owner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS", "1")
    lock_dir = tmp_path / "data/tmp/openclaw-gateway.lock"
    lock_dir.mkdir(parents=True)
    (lock_dir / "pid").write_text("321", encoding="utf-8")
    manager = GatewayManager(repo_root=tmp_path)
    manager._launch_lock_token = "peer-owner"
    (lock_dir / "owner").write_text("peer-owner", encoding="utf-8")
    manager._write_gateway_ownership_receipt(lock_dir, 321, listener_pid=321)
    manager._launch_lock_token = None
    monkeypatch.setattr(manager, "_probe_existing_gateway", lambda: True)
    monkeypatch.setattr(manager, "_pid_is_running", lambda pid: pid == 321)
    monkeypatch.setattr(manager, "_port_occupant_pids", lambda: {321})
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("healthy Gateway must be reused"),
    )

    manager.start()

    assert manager.is_running is True
    assert manager._process is None
    assert manager._reused_pid == 321
    manager.stop()
    assert lock_dir.exists()


@pytest.mark.parametrize("port", [18789, 49152, 65535])
def test_gateway_and_client_share_explicit_absolute_bbox_audit_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    port: int,
) -> None:
    monkeypatch.setenv("DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS", "1")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "not-written-to-receipt")
    captured: dict[str, Any] = {}
    process = _FakeProcess()
    explicit_path = Path("custom-audit") / "bbox.jsonl"
    manager = GatewayManager(
        repo_root=tmp_path,
        port=port,
        bbox_tool_audit_path=explicit_path,
    )
    client = OpenClawClient(
        gateway_token="not-written-to-receipt",
        base_dir=tmp_path,
        bbox_tool_audit_path=explicit_path,
    )
    monkeypatch.setattr(manager, "_probe_existing_gateway", lambda: False)
    monkeypatch.setattr(manager, "_port_occupant_pids", lambda: set())
    monkeypatch.setattr(manager, "_find_node", lambda: "node")
    monkeypatch.setattr(manager, "_gateway_script", lambda: tmp_path / "openclaw.mjs")
    monkeypatch.setattr(manager, "prepare_workspace", lambda: None)

    def capture_popen(command: list[str], **kwargs: Any) -> _FakeProcess:
        captured["command"] = command
        captured.update(kwargs)
        return process

    monkeypatch.setattr(subprocess, "Popen", capture_popen)

    manager.start()

    configured = json.loads(
        (tmp_path / "openclaw/openclaw.json").read_text(encoding="utf-8")
    )
    assert configured["plugins"]["entries"]["codex"] == {"enabled": False}
    assert "codex" not in configured["plugins"]["allow"]
    expected = (tmp_path / explicit_path).resolve()
    assert manager.bbox_tool_audit_path == expected
    assert client.bbox_tool_audit_path == expected
    assert captured["env"]["DICOM_BBOX_AUDIT_PATH"] == str(expected)
    assert captured["command"] == [
        "node",
        str(tmp_path / "openclaw.mjs"),
        "gateway",
        "run",
        "--port",
        str(port),
        "--bind",
        "loopback",
        "--verbose",
    ]
    receipt_text = (
        tmp_path / "data/tmp/openclaw-gateway.lock/ownership.json"
    ).read_text(encoding="utf-8")
    assert "not-written-to-receipt" not in receipt_text
    receipt = json.loads(receipt_text)
    assert receipt["status"] == "starting"
    assert receipt["supervisor_pid"] == process.pid
    assert receipt["listener_pid"] is None
    assert receipt["port"] == port
    assert receipt["bbox_audit_path"] == str(expected)
    assert len(receipt["token_sha256"]) == 64
    manager.stop()


@pytest.mark.asyncio
async def test_gateway_ready_binds_respawned_listener_pid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manager = GatewayManager(repo_root=tmp_path)
    process = _FakeProcess(pid=4321)
    lock_dir = manager._acquire_launch_lock()
    manager._process = process
    (lock_dir / "pid").write_text(str(process.pid), encoding="utf-8")
    manager._write_gateway_ownership_receipt(lock_dir, process.pid)
    monkeypatch.setattr(manager, "_probe_existing_gateway", lambda: True)
    monkeypatch.setattr(manager, "_port_occupant_pids", lambda: {9876})
    monkeypatch.setattr(manager, "_pid_is_running", lambda pid: pid in {4321, 9876})

    assert await manager.wait_ready(timeout_sec=0.1) is True

    assert (lock_dir / "pid").read_text(encoding="utf-8") == "4321"
    receipt = json.loads((lock_dir / "ownership.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "ready"
    assert receipt["supervisor_pid"] == 4321
    assert receipt["listener_pid"] == 9876
    assert manager._verified_gateway_owner_pid() == 9876
    manager.stop()


@pytest.mark.asyncio
async def test_gateway_ready_rejects_ambiguous_listener_ownership(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manager = GatewayManager(repo_root=tmp_path)
    process = _FakeProcess(pid=4321)
    lock_dir = manager._acquire_launch_lock()
    manager._process = process
    (lock_dir / "pid").write_text(str(process.pid), encoding="utf-8")
    manager._write_gateway_ownership_receipt(lock_dir, process.pid)
    monkeypatch.setattr(manager, "_probe_existing_gateway", lambda: True)
    monkeypatch.setattr(manager, "_port_occupant_pids", lambda: {9876, 9877})

    assert await manager.wait_ready(timeout_sec=0.1) is False
    assert (lock_dir / "pid").read_text(encoding="utf-8") == "4321"
    manager.stop()


@pytest.mark.parametrize(
    "mismatch",
    ["audit_path", "token_fingerprint", "pid", "port"],
)
def test_gateway_reuse_rejects_mismatched_ownership_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mismatch: str,
) -> None:
    monkeypatch.setenv("DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS", "1")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "expected-token")
    lock_dir = tmp_path / "data/tmp/openclaw-gateway.lock"
    lock_dir.mkdir(parents=True)
    (lock_dir / "pid").write_text("321", encoding="utf-8")
    (lock_dir / "owner").write_text("peer-owner", encoding="utf-8")
    manager = GatewayManager(repo_root=tmp_path)
    manager._launch_lock_token = "peer-owner"
    manager._write_gateway_ownership_receipt(lock_dir, 321, listener_pid=321)
    manager._launch_lock_token = None
    receipt_path = lock_dir / "ownership.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if mismatch == "audit_path":
        receipt["bbox_audit_path"] = str((tmp_path / "other.jsonl").resolve())
    elif mismatch == "token_fingerprint":
        receipt["token_sha256"] = "0" * 64
    elif mismatch == "pid":
        receipt["listener_pid"] = 322
    else:
        receipt["port"] = 18790
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    monkeypatch.setattr(manager, "_probe_existing_gateway", lambda: True)
    monkeypatch.setattr(manager, "_pid_is_running", lambda pid: pid == 321)
    monkeypatch.setattr(manager, "_port_occupant_pids", lambda: {321})

    with pytest.raises(RuntimeError, match="ownership receipt"):
        manager.start()

    assert manager._reused_gateway is False
    assert manager._reused_pid is None


def test_parse_attempt_history_survives_next_run_trace_begin(tmp_path: Path) -> None:
    client = OpenClawClient(gateway_token="test", base_dir=tmp_path)
    client._start_attempt_sequence()
    client._begin_run_trace("refine-first")
    client._last_run_id = "run-first"
    client._record_failed_attempt(
        BboxEvidenceError("receipt mismatch", kind="mismatched_receipt"),
        attempt=0,
    )
    client._last_parse_retry_count = 1

    client._begin_run_trace("refine-second")

    trace = client.last_run_trace()
    assert trace["session_key"] == "refine-second"
    assert trace["parse_retry_count"] == 1
    assert trace["attempts"][0]["session_key"] == "refine-first"
    assert trace["attempts"][0]["run_id"] == "run-first"
    assert trace["attempts"][0]["bbox_evidence_failure"] == ("mismatched_receipt")


@pytest.mark.asyncio
async def test_cancelled_gateway_wait_marks_trace_aborted_synchronously(
    tmp_path: Path,
) -> None:
    receive_started = asyncio.Event()
    abort_started = asyncio.Event()
    release_abort = asyncio.Event()

    class BlockingWebSocket:
        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []
            self.recv_count = 0

        async def recv(self) -> str:
            self.recv_count += 1
            if self.recv_count == 1:
                return json.dumps(_accepted("request-1", "run-cancelled"))
            receive_started.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        async def send(self, raw: str) -> None:
            frame = json.loads(raw)
            self.sent.append(frame)
            if frame.get("method") == "chat.abort":
                abort_started.set()
                await release_abort.wait()

    client = OpenClawClient(gateway_token="test", base_dir=tmp_path)
    websocket = BlockingWebSocket()
    client._ws = websocket
    client._connected = True
    client._start_attempt_sequence()
    client._begin_run_trace("refine-cancelled")
    task = asyncio.create_task(client._wait_for_chat_result("request-1"))
    await receive_started.wait()

    task.cancel()
    await abort_started.wait()
    assert client.last_run_trace()["turn_aborted"] is True

    # Simulate a subsequent turn beginning while the old turn's bounded abort
    # send is still in flight.  The abort frame must retain the old identity.
    client._begin_run_trace("refine-new")
    release_abort.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    abort = websocket.sent[-1]
    assert abort["method"] == "chat.abort"
    assert abort["params"] == {
        "sessionKey": "refine-cancelled",
        "runId": "run-cancelled",
    }
    assert client.last_run_trace()["session_key"] == "refine-new"
    assert client.last_run_trace()["turn_aborted"] is False


@pytest.mark.asyncio
async def test_cancel_during_chat_send_aborts_immutable_session(
    tmp_path: Path,
) -> None:
    send_started = asyncio.Event()

    class BlockingSendWebSocket:
        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []

        async def send(self, raw: str) -> None:
            frame = json.loads(raw)
            self.sent.append(frame)
            if frame.get("method") == "chat.send":
                send_started.set()
                await asyncio.Event().wait()

        async def recv(self) -> str:
            raise AssertionError("receive must not start while chat.send is blocked")

    client = OpenClawClient(gateway_token="test", base_dir=tmp_path)
    websocket = BlockingSendWebSocket()
    client._ws = websocket
    client._connected = True
    task = asyncio.create_task(client.chat("test-only message"))
    await send_started.wait()
    sent_session = websocket.sent[0]["params"]["sessionKey"]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert client.last_run_trace()["turn_aborted"] is True
    assert websocket.sent[-1]["method"] == "chat.abort"
    assert websocket.sent[-1]["params"] == {"sessionKey": sent_session}


@pytest.mark.asyncio
async def test_timeout_abort_cannot_target_newly_started_session(
    tmp_path: Path,
) -> None:
    abort_started = asyncio.Event()
    release_abort = asyncio.Event()

    class BlockingAbortWebSocket:
        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []

        async def recv(self) -> str:
            raise AssertionError("expired deadline must not receive")

        async def send(self, raw: str) -> None:
            frame = json.loads(raw)
            self.sent.append(frame)
            abort_started.set()
            await release_abort.wait()

    client = OpenClawClient(gateway_token="test", base_dir=tmp_path)
    websocket = BlockingAbortWebSocket()
    client._ws = websocket
    client._connected = True
    client._begin_run_trace("analysis-timed-out")
    task = asyncio.create_task(
        client._wait_for_chat_result(
            "request-timeout",
            deadline=-1.0,
            initial_run_id="run-timed-out",
            response_accepted=True,
        )
    )
    await abort_started.wait()
    assert client.last_run_trace()["turn_aborted"] is True

    client._begin_run_trace("analysis-new")
    release_abort.set()
    with pytest.raises(TimeoutError, match="Analysis timeout"):
        await task

    assert websocket.sent[-1]["params"] == {
        "sessionKey": "analysis-timed-out",
        "runId": "run-timed-out",
    }
    assert client.last_run_trace()["session_key"] == "analysis-new"
    assert client.last_run_trace()["turn_aborted"] is False


def test_reused_gateway_without_resolvable_pid_is_rejected_on_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS", "1")
    manager = GatewayManager(repo_root=tmp_path)
    manager._reused_gateway = True
    manager._reused_pid = None
    probe_calls = 0

    def probe() -> bool:
        nonlocal probe_calls
        probe_calls += 1
        return True

    monkeypatch.setattr(manager, "_probe_existing_gateway", probe)
    monkeypatch.setattr(manager, "_port_occupant_pids", lambda: set())

    with pytest.raises(RuntimeError, match="ownership receipt"):
        manager.start()

    assert probe_calls == 1
    assert manager._reused_gateway is False
    assert manager._reused_pid is None
    assert manager.is_running is False


def test_gateway_removes_dead_lock_and_records_new_owned_pid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS", "1")
    lock_dir = tmp_path / "data/tmp/openclaw-gateway.lock"
    lock_dir.mkdir(parents=True)
    (lock_dir / "pid").write_text("999", encoding="utf-8")
    process = _FakeProcess()
    manager = GatewayManager(repo_root=tmp_path)
    monkeypatch.setattr(manager, "_probe_existing_gateway", lambda: False)
    monkeypatch.setattr(manager, "_pid_is_running", lambda _pid: False)
    monkeypatch.setattr(manager, "_port_occupant_pids", lambda: set())
    monkeypatch.setattr(manager, "_find_node", lambda: "node")
    monkeypatch.setattr(manager, "_gateway_script", lambda: tmp_path / "openclaw.mjs")
    monkeypatch.setattr(manager, "prepare_workspace", lambda: None)
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)

    manager.start()

    assert (lock_dir / "pid").read_text(encoding="utf-8") == "4321"
    assert manager._process is process
    manager.stop()
    assert not lock_dir.exists()


def test_gateway_never_kills_unowned_unhealthy_port_listener(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS", "1")
    manager = GatewayManager(repo_root=tmp_path)
    monkeypatch.setattr(manager, "_probe_existing_gateway", lambda: False)
    monkeypatch.setattr(manager, "_port_occupant_pids", lambda: {777})
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("must not spawn into an occupied port"),
    )

    with pytest.raises(RuntimeError, match="refusing to terminate an unowned process"):
        manager.start()

    assert not (tmp_path / "data/tmp/openclaw-gateway.lock").exists()


def test_owned_gateway_shutdown_is_bounded_and_always_releases_lock(
    tmp_path: Path,
) -> None:
    class HungProcess(_FakeProcess):
        def terminate(self) -> None:
            self.terminate_calls += 1

        def kill(self) -> None:
            self.kill_calls += 1

        def wait(self, timeout: float | None = None) -> int:
            self.wait_timeouts.append(timeout)
            raise subprocess.TimeoutExpired("node", timeout)

    process = HungProcess()
    manager = GatewayManager(repo_root=tmp_path)
    lock_dir = tmp_path / "data/tmp/openclaw-gateway.lock"
    lock_dir.mkdir(parents=True)
    manager._process = process
    manager._launch_lock_dir = lock_dir

    manager.stop()

    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert process.wait_timeouts == [5, 3]
    assert manager._process is None
    assert not lock_dir.exists()


def test_gateway_does_not_remove_lock_reacquired_by_another_owner(
    tmp_path: Path,
) -> None:
    manager = GatewayManager(repo_root=tmp_path)
    lock_dir = tmp_path / "data/tmp/openclaw-gateway.lock"
    lock_dir.mkdir(parents=True)
    (lock_dir / "owner").write_text("peer-owner", encoding="utf-8")
    manager._launch_lock_dir = lock_dir
    manager._launch_lock_token = "original-owner"

    manager._release_launch_lock()

    assert lock_dir.exists()
    assert manager._launch_lock_dir is None


class _ScriptedWebSocket:
    def __init__(self, frames: list[dict[str, Any] | BaseException]) -> None:
        self.frames = list(frames)
        self.sent: list[dict[str, Any]] = []
        self.closed = False

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    async def recv(self) -> str:
        frame = self.frames.pop(0)
        if isinstance(frame, BaseException):
            raise frame
        return json.dumps(frame)

    async def close(self) -> None:
        self.closed = True


def _closed() -> websockets.ConnectionClosedError:
    return websockets.ConnectionClosedError(None, None)


def _accepted(request_id: str, run_id: str = "run-1") -> dict[str, Any]:
    return {
        "type": "res",
        "id": request_id,
        "ok": True,
        "payload": {"status": "accepted", "runId": run_id},
    }


def _final(run_id: str = "run-1", text: str = "done") -> dict[str, Any]:
    return {
        "type": "event",
        "payload": {
            "runId": run_id,
            "state": "final",
            "message": {"content": [{"type": "text", "text": text}]},
        },
    }


def _connected_client(tmp_path: Path, websocket: _ScriptedWebSocket) -> OpenClawClient:
    client = OpenClawClient(
        gateway_token="test-token",
        base_dir=tmp_path,
        inference_timeout_sec=5,
    )
    client._ws = websocket
    client._connected = True
    return client


@pytest.mark.asyncio
async def test_preaccept_disconnect_replays_exact_same_frame_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = _ScriptedWebSocket([_closed()])
    second = _ScriptedWebSocket([])
    client = _connected_client(tmp_path, first)

    async def reconnect() -> None:
        client._ws = second
        client._connected = True

    monkeypatch.setattr(client, "connect", reconnect)
    request_id = "chat-1"
    second.frames.extend([_accepted(request_id), _final()])

    result = await client.chat("hello")

    assert result == "done"
    assert len(first.sent) == 1
    assert second.sent == first.sent
    assert (
        first.sent[0]["params"]["idempotencyKey"]
        == second.sent[0]["params"]["idempotencyKey"]
    )
    assert (
        first.sent[0]["params"]["sessionKey"] == second.sent[0]["params"]["sessionKey"]
    )


@pytest.mark.asyncio
async def test_postaccept_disconnect_reconnects_and_observes_run_without_replay(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = _ScriptedWebSocket([])
    second = _ScriptedWebSocket([_final()])
    client = _connected_client(tmp_path, first)

    async def reconnect() -> None:
        client._ws = second
        client._connected = True

    monkeypatch.setattr(client, "connect", reconnect)
    first.frames.extend([_accepted("chat-1"), _closed()])

    result = await client.chat("hello")

    assert result == "done"
    assert len(first.sent) == 1
    assert second.sent == []
    assert client.last_run_trace()["run_id"] == "run-1"


@pytest.mark.asyncio
async def test_postaccept_second_disconnect_fails_without_resubmitting_turn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = _ScriptedWebSocket([_accepted("chat-1"), _closed()])
    second = _ScriptedWebSocket([_closed()])
    client = _connected_client(tmp_path, first)

    async def reconnect() -> None:
        client._ws = second
        client._connected = True

    monkeypatch.setattr(client, "connect", reconnect)

    with pytest.raises(ConnectionError, match="accepted run run-1"):
        await client.chat("hello")

    assert len(first.sent) == 1
    assert second.sent == []
    assert client.is_connected() is False


@pytest.mark.asyncio
async def test_reconnect_handshake_preserves_final_event_for_accepted_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class HandshakeWebSocket:
        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []
            self.recv_count = 0

        async def send(self, raw: str) -> None:
            self.sent.append(json.loads(raw))

        async def recv(self) -> str:
            self.recv_count += 1
            if self.recv_count == 1:
                return json.dumps(_final())
            return json.dumps(
                {
                    "type": "res",
                    "id": self.sent[-1]["id"],
                    "ok": True,
                    "payload": {
                        "type": "hello-ok",
                        "protocol": 4,
                        "server": {"version": "2026.7.1-2"},
                    },
                }
            )

        async def close(self) -> None:
            return None

    websocket = HandshakeWebSocket()

    async def connect(*_args: object, **_kwargs: object) -> HandshakeWebSocket:
        return websocket

    monkeypatch.setattr(
        "dicom_overlay.infrastructure.openclaw_client.websockets.connect",
        connect,
    )
    client = OpenClawClient(gateway_token="test-token", base_dir=tmp_path)
    await client.connect()
    assert client.gateway_protocol_receipt() == {
        "verified": True,
        "advertised_min_protocol": 3,
        "advertised_max_protocol": 4,
        "negotiated_protocol": 4,
        "server_version": "2026.7.1-2",
    }
    client._begin_run_trace("accepted-session")

    result = await client._wait_for_chat_text(
        "chat-1",
        initial_run_id="run-1",
        response_accepted=True,
    )

    assert result == "done"
    assert websocket.recv_count == 2


@pytest.mark.asyncio
async def test_client_disconnect_is_bounded_when_close_handshake_hangs(
    tmp_path: Path,
) -> None:
    class HangingCloseWebSocket:
        async def close(self) -> None:
            await asyncio.Event().wait()

    client = OpenClawClient(gateway_token="test-token", base_dir=tmp_path)
    client._ws = HangingCloseWebSocket()
    client._connected = True
    client._close_timeout = 0.01

    await client.disconnect()

    assert client._ws is None
    assert client.is_connected() is False


@pytest.mark.asyncio
async def test_client_disconnect_swallows_transport_close_error_for_gui_shutdown(
    tmp_path: Path,
) -> None:
    class BrokenCloseWebSocket:
        async def close(self) -> None:
            raise OSError("test-only close failure")

    client = OpenClawClient(gateway_token="test-token", base_dir=tmp_path)
    client._ws = BrokenCloseWebSocket()
    client._connected = True

    await client.disconnect()

    assert client._ws is None
    assert client.is_connected() is False


def _analysis_with_box(box: RegionRect) -> AnalysisResult:
    return AnalysisResult(
        modality=Modality.EKG,
        summary="Public synthetic ECG result.",
        severity=Severity.WARNING,
        findings=[
            Finding(
                id="f1",
                regions=["lead_II"],
                label="Synthetic morphology",
                detail="Test-only structured finding.",
                severity=Severity.WARNING,
                bboxes=[box],
            )
        ],
        checklist={},
    )


def _client_with_receipt(tmp_path: Path, boxes: list[RegionRect]) -> OpenClawClient:
    client = OpenClawClient(gateway_token="test-token", base_dir=tmp_path)
    client._last_tool_audit_records = [
        {
            "tool": "dicom_bbox_validate",
            "accepted_boxes_sha256": _bbox_coordinates_digest(boxes),
            "accepted_count": len(boxes),
        }
    ]
    client._refresh_tool_audit = lambda: None  # type: ignore[method-assign]
    return client


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("schema_version", 1),
        ("details_sha256", "not-a-sha256"),
        ("evidence_nonce", "not-a-turn-nonce"),
        ("accepted_boxes_sha256", "not-a-coordinate-digest"),
        ("accepted_count", "1"),
    ],
)
def test_malformed_current_bbox_receipt_is_mismatch_not_missing(
    tmp_path: Path,
    field: str,
    bad_value: object,
) -> None:
    audit_path = tmp_path / "bbox-audit.jsonl"
    box = RegionRect(0.1, 0.2, 0.3, 0.1)
    result = _analysis_with_box(box)
    source_sha = "a" * 64
    evidence_nonce = "b" * 32
    client = OpenClawClient(
        gateway_token="test-token",
        base_dir=tmp_path,
        bbox_tool_audit_path=audit_path,
    )
    client._begin_run_trace(
        "analysis-malformed-receipt",
        bbox_evidence_nonce=evidence_nonce,
        source_image_sha256=source_sha,
    )
    receipt: dict[str, object] = {
        "schema_version": 2,
        "tool": "dicom_bbox_validate",
        "tool_call_id": "current-call",
        "accepted_count": 1,
        "rejected_count": 0,
        "source_image_sha256": source_sha,
        "evidence_nonce": evidence_nonce,
        "accepted_boxes_sha256": _bbox_coordinates_digest([box]),
        "details_sha256": "c" * 64,
    }
    receipt[field] = bad_value
    audit_path.write_text(f"{json.dumps(receipt)}\n", encoding="utf-8")

    with pytest.raises(BboxEvidenceError) as captured:
        client._require_bound_bbox_receipt(result)

    assert captured.value.kind == "mismatched_receipt"
    if field in {"schema_version", "details_sha256", "evidence_nonce"}:
        assert client._last_bbox_audit_observations == [
            {
                "receipt_valid": False,
                "failure": "invalid_receipt_schema",
            }
        ]


def test_malformed_json_bbox_receipt_is_mismatch_after_record_boundary(
    tmp_path: Path,
) -> None:
    audit_path = tmp_path / "bbox-audit.jsonl"
    box = RegionRect(0.1, 0.2, 0.3, 0.1)
    result = _analysis_with_box(box)
    client = OpenClawClient(
        gateway_token="test-token",
        base_dir=tmp_path,
        bbox_tool_audit_path=audit_path,
    )
    client._begin_run_trace(
        "analysis-malformed-json",
        bbox_evidence_nonce="b" * 32,
        source_image_sha256="a" * 64,
    )
    audit_path.write_bytes(b'{"schema_version":2')

    with pytest.raises(BboxEvidenceError) as incomplete:
        client._require_bound_bbox_receipt(result)
    assert incomplete.value.kind == "missing_receipt"

    with audit_path.open("ab") as handle:
        handle.write(b",broken}\n")
    with pytest.raises(BboxEvidenceError) as complete:
        client._require_bound_bbox_receipt(result)

    assert complete.value.kind == "mismatched_receipt"
    assert client._last_bbox_audit_observations == [
        {"receipt_valid": False, "failure": "malformed_jsonl"}
    ]


def test_stale_malformed_bbox_line_does_not_change_absent_current_receipt(
    tmp_path: Path,
) -> None:
    audit_path = tmp_path / "bbox-audit.jsonl"
    audit_path.write_text("{not-json}\n", encoding="utf-8")
    box = RegionRect(0.1, 0.2, 0.3, 0.1)
    client = OpenClawClient(
        gateway_token="test-token",
        base_dir=tmp_path,
        bbox_tool_audit_path=audit_path,
    )
    client._begin_run_trace(
        "analysis-no-current-receipt",
        bbox_evidence_nonce="b" * 32,
        source_image_sha256="a" * 64,
    )

    with pytest.raises(BboxEvidenceError) as captured:
        client._require_bound_bbox_receipt(_analysis_with_box(box))

    assert captured.value.kind == "missing_receipt"
    assert client._last_bbox_audit_observations == []


@pytest.mark.asyncio
async def test_malformed_bbox_receipt_retries_once_and_fails_closed(
    tmp_path: Path,
) -> None:
    audit_path = tmp_path / "bbox-audit.jsonl"
    box = RegionRect(0.1, 0.2, 0.3, 0.1)
    result = _analysis_with_box(box)
    client = OpenClawClient(
        gateway_token="test-token",
        base_dir=tmp_path,
        bbox_tool_audit_path=audit_path,
    )
    calls = 0

    async def malformed_turn(*_args: object, **_kwargs: object) -> AnalysisResult:
        nonlocal calls
        calls += 1
        client._begin_run_trace(
            f"analysis-malformed-{calls}",
            bbox_evidence_nonce="b" * 32,
            source_image_sha256="a" * 64,
        )
        with audit_path.open("a", encoding="utf-8") as handle:
            handle.write('{"schema_version":1,"tool":"dicom_bbox_validate"}\n')
        client._require_bound_bbox_receipt(result)
        raise AssertionError("malformed receipt must fail closed")

    client._do_analyze = malformed_turn  # type: ignore[method-assign]

    with pytest.raises(BboxEvidenceError) as captured:
        await client._analyze_with_parse_retry("image", Modality.EKG, ["lead_II"])

    assert captured.value.kind == "mismatched_receipt"
    assert calls == 2
    assert client.last_run_trace()["parse_retry_count"] == 1
    attempts = client.last_run_trace()["attempts"]
    assert [attempt["bbox_evidence_failure"] for attempt in attempts] == [
        "mismatched_receipt",
        "mismatched_receipt",
    ]


@pytest.mark.asyncio
async def test_finalization_decimal_drift_locks_to_exact_receipt_without_retry(
    tmp_path: Path,
) -> None:
    draft_box = RegionRect(0.1, 0.2, 0.3, 0.06325)
    model_box = RegionRect(0.1, 0.2, 0.3, 0.063)
    draft = _analysis_with_box(draft_box)
    final = _analysis_with_box(model_box)
    client = _client_with_receipt(tmp_path, [draft_box])
    client._last_parse_retry_count = 0
    calls = 0

    async def finalize_once(*_args: object, **_kwargs: object) -> AnalysisResult:
        nonlocal calls
        calls += 1
        return client._lock_finalization_geometry(draft, final)

    client._do_finalize = finalize_once  # type: ignore[method-assign]

    result = await client._finalize_with_parse_retry(
        "image",
        Modality.EKG,
        ["lead_II"],
        draft=draft,
        refinement_trace=[],
    )

    assert calls == 1
    assert client._last_parse_retry_count == 0
    assert result.findings[0].bboxes == [draft_box]
    lock_trace = result.analysis_trace[-1]
    assert lock_trace["model_bbox_drift_count"] == 1
    assert lock_trace["model_bbox_max_coordinate_drift"] == pytest.approx(0.00025)
    assert lock_trace["digest_tolerance_applied"] is False


@pytest.mark.asyncio
async def test_finalization_wrong_receipt_retries_then_fails_closed(
    tmp_path: Path,
) -> None:
    draft_box = RegionRect(0.1, 0.2, 0.3, 0.06325)
    draft = _analysis_with_box(draft_box)
    final = _analysis_with_box(RegionRect(0.1, 0.2, 0.3, 0.063))
    client = _client_with_receipt(
        tmp_path,
        [RegionRect(0.5, 0.5, 0.1, 0.1)],
    )
    client._last_parse_retry_count = 0
    calls = 0

    async def bad_finalize(*_args: object, **_kwargs: object) -> AnalysisResult:
        nonlocal calls
        calls += 1
        return client._lock_finalization_geometry(draft, final)

    client._do_finalize = bad_finalize  # type: ignore[method-assign]

    with pytest.raises(BboxEvidenceError):
        await client._finalize_with_parse_retry(
            "image",
            Modality.EKG,
            ["lead_II"],
            draft=draft,
            refinement_trace=[],
        )

    assert calls == 2
    assert client._last_parse_retry_count == 1
