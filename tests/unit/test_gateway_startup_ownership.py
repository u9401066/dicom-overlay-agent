from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from dicom_overlay.infrastructure import gateway_manager as gateway_manager_module
from dicom_overlay.infrastructure.gateway_manager import GatewayManager

if TYPE_CHECKING:
    from pathlib import Path


def _write_peer_receipt(
    manager: GatewayManager,
    lock_dir: Path,
    *,
    supervisor_pid: int = 321,
    listener_pid: int | None = None,
    owner: str = "peer-owner",
) -> None:
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "pid").write_text(str(supervisor_pid), encoding="utf-8")
    (lock_dir / "owner").write_text(owner, encoding="utf-8")
    manager._launch_lock_token = owner
    try:
        manager._write_gateway_ownership_receipt(
            lock_dir,
            supervisor_pid,
            listener_pid=listener_pid,
        )
    finally:
        manager._launch_lock_token = None


def _forbid_spawn(*_args: object, **_kwargs: object) -> subprocess.Popen:
    raise AssertionError("a second Gateway must not be spawned")


def test_start_waits_for_live_starting_owner_then_reuses_ready_listener(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS", "1")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "race-test-secret")
    manager = GatewayManager(repo_root=tmp_path)
    lock_dir = tmp_path / "data/tmp/openclaw-gateway.lock"
    _write_peer_receipt(manager, lock_dir)
    clock = [0.0]
    probe_calls = 0

    def probe() -> bool:
        nonlocal probe_calls
        probe_calls += 1
        return probe_calls >= 2

    def publish_ready_and_advance(delay_sec: float) -> None:
        clock[0] += delay_sec
        _write_peer_receipt(manager, lock_dir, listener_pid=654)

    monkeypatch.setattr(manager, "_probe_existing_gateway", probe)
    monkeypatch.setattr(manager, "_pid_is_running", lambda pid: pid in {321, 654})
    monkeypatch.setattr(manager, "_port_occupant_pids", lambda: {654})
    monkeypatch.setattr(manager, "_startup_reuse_clock", lambda: clock[0])
    monkeypatch.setattr(manager, "_startup_reuse_sleep", publish_ready_and_advance)
    monkeypatch.setattr(subprocess, "Popen", _forbid_spawn)

    manager.start()

    assert manager.is_running is True
    assert manager._process is None
    assert manager._reused_pid == 654
    assert probe_calls == 2
    assert lock_dir.is_dir()
    receipt_text = (lock_dir / "ownership.json").read_text(encoding="utf-8")
    assert "race-test-secret" not in receipt_text
    manager.stop()
    assert lock_dir.is_dir()


def test_start_waits_when_probe_wins_race_before_receipt_becomes_ready(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS", "1")
    manager = GatewayManager(repo_root=tmp_path)
    lock_dir = tmp_path / "data/tmp/openclaw-gateway.lock"
    _write_peer_receipt(manager, lock_dir)
    clock = [0.0]

    def publish_ready_and_advance(delay_sec: float) -> None:
        clock[0] += delay_sec
        _write_peer_receipt(manager, lock_dir, listener_pid=654)

    monkeypatch.setattr(manager, "_probe_existing_gateway", lambda: True)
    monkeypatch.setattr(manager, "_pid_is_running", lambda pid: pid in {321, 654})
    monkeypatch.setattr(manager, "_port_occupant_pids", lambda: {654})
    monkeypatch.setattr(manager, "_startup_reuse_clock", lambda: clock[0])
    monkeypatch.setattr(manager, "_startup_reuse_sleep", publish_ready_and_advance)
    monkeypatch.setattr(subprocess, "Popen", _forbid_spawn)

    manager.start()

    assert manager._reused_gateway is True
    assert manager._reused_pid == 654
    assert (
        json.loads((lock_dir / "ownership.json").read_text(encoding="utf-8"))["status"]
        == "ready"
    )


def test_starting_owner_timeout_refuses_without_altering_live_lock_or_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS", "1")
    monkeypatch.setattr(gateway_manager_module, "_GATEWAY_STARTUP_REUSE_WAIT_SEC", 0.2)
    manager = GatewayManager(repo_root=tmp_path)
    lock_dir = tmp_path / "data/tmp/openclaw-gateway.lock"
    _write_peer_receipt(manager, lock_dir)
    original_files = {
        path.name: path.read_bytes() for path in lock_dir.iterdir() if path.is_file()
    }
    clock = [0.0]
    sleep_calls: list[float] = []

    def advance(delay_sec: float) -> None:
        sleep_calls.append(delay_sec)
        clock[0] += delay_sec

    monkeypatch.setattr(manager, "_probe_existing_gateway", lambda: False)
    monkeypatch.setattr(manager, "_pid_is_running", lambda pid: pid == 321)
    monkeypatch.setattr(manager, "_startup_reuse_clock", lambda: clock[0])
    monkeypatch.setattr(manager, "_startup_reuse_sleep", advance)
    monkeypatch.setattr(
        manager,
        "_kill_port_occupant",
        lambda: pytest.fail("an unowned process must not be terminated"),
    )
    monkeypatch.setattr(subprocess, "Popen", _forbid_spawn)

    with pytest.raises(RuntimeError, match="did not become ready"):
        manager.start()

    assert sleep_calls == pytest.approx([0.1, 0.1])
    assert manager._process is None
    assert manager._reused_gateway is False
    assert lock_dir.is_dir()
    assert {
        path.name: path.read_bytes() for path in lock_dir.iterdir() if path.is_file()
    } == original_files


def test_tampered_starting_receipt_is_never_waited_on_or_adopted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS", "1")
    manager = GatewayManager(repo_root=tmp_path)
    lock_dir = tmp_path / "data/tmp/openclaw-gateway.lock"
    _write_peer_receipt(manager, lock_dir)
    receipt_path = lock_dir / "ownership.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["token_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    tampered_bytes = receipt_path.read_bytes()

    monkeypatch.setattr(manager, "_probe_existing_gateway", lambda: False)
    monkeypatch.setattr(manager, "_pid_is_running", lambda pid: pid == 321)
    monkeypatch.setattr(
        manager,
        "_startup_reuse_sleep",
        lambda _delay: pytest.fail("a tampered receipt must not enter the wait path"),
    )
    monkeypatch.setattr(subprocess, "Popen", _forbid_spawn)

    with pytest.raises(RuntimeError, match="launch lock is already held"):
        manager.start()

    assert receipt_path.read_bytes() == tampered_bytes
    assert lock_dir.is_dir()
    assert manager._process is None
    assert manager._reused_gateway is False
