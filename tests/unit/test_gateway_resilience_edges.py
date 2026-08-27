from __future__ import annotations

import asyncio
import json
import subprocess
from typing import TYPE_CHECKING, Any

import pytest
import websockets

if TYPE_CHECKING:
    from pathlib import Path

from dicom_overlay.domain.entities import (
    AnalysisResult,
    Finding,
    Modality,
    RegionRect,
    Severity,
)
from dicom_overlay.infrastructure import openclaw_client as openclaw_client_module
from dicom_overlay.infrastructure.gateway_manager import GatewayManager
from dicom_overlay.infrastructure.openclaw_client import (
    BboxEvidenceError,
    OpenClawClient,
    _bbox_coordinates_digest,
    probe_openclaw_gateway,
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
                    "payload": {"status": "connected"},
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
    assert websocket.sent["params"]["auth"] == {"token": "test-token"}


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


def test_reused_gateway_without_resolvable_pid_is_reprobed_on_start(
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

    manager.start()

    assert probe_calls == 1
    assert manager._reused_gateway is True
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
                    "payload": {"status": "connected"},
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
