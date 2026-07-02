"""OpenClaw Gateway subprocess manager — starts/stops the Node.js gateway."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TextIO

import structlog

from dicom_overlay.infrastructure.env_file import read_env_file
from dicom_overlay.infrastructure.openclaw_runtime import (
    ensure_openclaw_runtime_supported,
)

logger = structlog.get_logger(__name__)

# Relative paths from repo root
_OPENCLAW_MJS = Path("openclaw/node_modules/openclaw/openclaw.mjs")
_OPENCLAW_CONFIG = Path("openclaw/openclaw.json")
_OPENCLAW_HOME = Path("openclaw-home")
_SRC_SKILLS = Path("openclaw/workspace/skills")
_DST_SKILLS = _OPENCLAW_HOME / ".openclaw" / "workspace" / "skills"
_GATEWAY_LAUNCH_LOCK = Path("data/tmp/openclaw-gateway.lock")


class GatewayManager:
    """Manages the OpenClaw Gateway Node.js subprocess lifecycle."""

    def __init__(self, repo_root: Path | None = None, port: int = 18789) -> None:
        self._repo_root = repo_root or Path.cwd()
        self._port = port
        self._process: subprocess.Popen | None = None
        self._gateway_log: TextIO | None = None
        self._launch_lock_dir: Path | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _find_node(self) -> str:
        """Find the node executable, preferring a repo-local / bundled binary.

        Resolution order (Core 4 "zero-install" goal):
        1. Bundled portable node next to the app/runtime (``node/node.exe`` under
           the PyInstaller resource root or the repo root). Lets the portable
           bundle run with no system Node.js installed.
        2. System ``node`` on PATH (developer machines).
        """
        exe_name = "node.exe" if sys.platform == "win32" else "node"
        for root in (self._resource_root(), self._repo_root):
            candidate = root / "node" / exe_name
            if candidate.exists():
                logger.info("Using bundled Node.js runtime: %s", candidate)
                return str(candidate)

        node = shutil.which("node")
        if node is None:
            msg = (
                "Node.js not found. Bundle a portable runtime with "
                "scripts\\fetch-node.ps1 (creates node\\node.exe) or install "
                "Node.js (https://nodejs.org) to run the OpenClaw Gateway."
            )
            raise FileNotFoundError(msg)
        logger.info("Using system Node.js runtime: %s", node)
        return node

    def _resource_root(self) -> Path:
        """Return bundled read-only resource root or repo root in dev mode."""
        if getattr(sys, "frozen", False):
            bundle_root = getattr(sys, "_MEIPASS", None)
            if bundle_root:
                return Path(str(bundle_root))
        return self._repo_root

    def _gateway_script(self) -> Path:
        resource_root = self._resource_root()
        version = ensure_openclaw_runtime_supported(resource_root)
        logger.info("OpenClaw runtime version accepted: %s", version)
        script = resource_root / _OPENCLAW_MJS
        if not script.exists():
            msg = (
                f"OpenClaw not found at {script}. "
                "Run scripts\\install-openclaw-local.bat first."
            )
            raise FileNotFoundError(msg)
        return script

    def verify_runtime(self) -> list[tuple[str, bool, str]]:
        """Self-check that the portable bundle can start, without launching.

        Returns a list of ``(component, ok, detail)`` rows covering the pieces a
        fresh machine (e.g. a USB plug-and-play target) needs: Node.js runtime,
        the OpenClaw gateway script, and a writable base directory. Used by the
        ``--selfcheck`` CLI flag and the packaging smoke test so "does the
        installer start correctly?" is answerable in CI without a real GUI/LLM.
        """
        rows: list[tuple[str, bool, str]] = []

        try:
            node = self._find_node()
            rows.append(("node", True, node))
        except FileNotFoundError as exc:
            rows.append(("node", False, str(exc)))

        try:
            script = self._gateway_script()
            rows.append(("openclaw", True, str(script)))
        except (FileNotFoundError, RuntimeError) as exc:
            rows.append(("openclaw", False, str(exc)))

        home = self._repo_root / _OPENCLAW_HOME
        try:
            (home / ".openclaw" / "workspace").mkdir(parents=True, exist_ok=True)
            probe = home / ".selfcheck_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            rows.append(("writable_base", True, str(self._repo_root)))
        except OSError as exc:
            rows.append(("writable_base", False, str(exc)))

        return rows

    def _sync_skills(self) -> None:
        """Sync workspace skills to openclaw-home (mirrors sync-openclaw-workspace.bat)."""
        src = self._resource_root() / _SRC_SKILLS
        dst = self._repo_root / _DST_SKILLS
        if not src.exists():
            logger.warning("Skill source not found: %s", src)
            return
        dst.mkdir(parents=True, exist_ok=True)

        # Mirror sync: copy all files, remove extras in dst
        if sys.platform == "win32":
            subprocess.run(
                ["robocopy", str(src), str(dst), "/MIR", "/NFL", "/NDL", "/NJH", "/NJS", "/NP"],
                capture_output=True,
                check=False,  # robocopy returns 0-7 for success
            )
        else:
            subprocess.run(
                ["rsync", "-a", "--delete", f"{src}/", f"{dst}/"],
                capture_output=True,
                check=True,
            )
        logger.info("Synced workspace skills to %s", dst)

    def _ensure_dirs(self) -> None:
        """Ensure openclaw-home directory structure exists."""
        home = self._repo_root / _OPENCLAW_HOME
        (home / ".openclaw" / "workspace").mkdir(parents=True, exist_ok=True)

    def _acquire_launch_lock(self) -> Path:
        """Take a repo-local lock so only one OpenClaw Gateway is spawned."""
        lock_dir = self._repo_root / _GATEWAY_LAUNCH_LOCK
        lock_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock_dir.mkdir()
        except FileExistsError:
            pid = self._read_lock_pid(lock_dir)
            if pid is not None and self._pid_is_running(pid):
                raise RuntimeError(
                    "OpenClaw Gateway launch lock is already held by pid "
                    f"{pid}: {lock_dir}"
                ) from None
            logger.warning("Removing stale OpenClaw Gateway launch lock: %s", lock_dir)
            shutil.rmtree(lock_dir, ignore_errors=True)
            lock_dir.mkdir()
        self._launch_lock_dir = lock_dir
        return lock_dir

    def _release_launch_lock(self) -> None:
        """Release the launch lock held by this manager, if any."""
        if self._launch_lock_dir is None:
            return
        shutil.rmtree(self._launch_lock_dir, ignore_errors=True)
        self._launch_lock_dir = None

    def _read_lock_pid(self, lock_dir: Path) -> int | None:
        try:
            return int((lock_dir / "pid").read_text(encoding="utf-8").strip())
        except (FileNotFoundError, OSError, ValueError):
            return None

    def _pid_is_running(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def _kill_port_occupant(self) -> None:
        """Kill any process occupying the Gateway port.

        This handles the case where a previous Gateway process is still alive
        (e.g., from a previous app run that wasn't shut down cleanly).
        """
        if sys.platform != "win32":
            # On Linux/macOS, use lsof
            try:
                result = subprocess.run(
                    ["lsof", "-ti", f"tcp:{self._port}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                pids = result.stdout.strip().split()
                for pid_str in pids:
                    pid = int(pid_str)
                    logger.warning("Killing process %d occupying port %d", pid, self._port)
                    os.kill(pid, 15)  # SIGTERM
            except (FileNotFoundError, ValueError):
                pass
            return

        # Windows: use netstat to find PID on the port
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in result.stdout.splitlines():
                if f":{self._port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = int(parts[-1])
                    # Don't kill our own process
                    if self._process is not None and pid == self._process.pid:
                        continue
                    logger.warning(
                        "Killing stale process (pid=%d) occupying port %d",
                        pid,
                        self._port,
                    )
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True,
                        check=False,
                    )
        except (FileNotFoundError, ValueError, IndexError):
            pass

    def start(self) -> None:
        """Start the Gateway subprocess (non-blocking)."""
        if self.is_running:
            logger.info("Gateway already running (pid=%d)", self._process.pid)  # type: ignore[union-attr]
            return

        if (
            os.environ.get("DICOM_OVERLAY_TEST_DISABLE_REAL_OPENCLAW") == "1"
            and os.environ.get("DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS") != "1"
        ):
            raise RuntimeError(
                "OpenClaw Gateway startup is disabled during OOM-safe tests. "
                "Set DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS=1 only for an "
                "explicit real Gateway integration run."
            )

        lock_dir = self._acquire_launch_lock()
        # Kill any stale process occupying the port before starting
        try:
            self._kill_port_occupant()

            node = self._find_node()
            script = self._gateway_script()

            self._ensure_dirs()
            self._sync_skills()

            home = self._repo_root / _OPENCLAW_HOME
            config = self._repo_root / _OPENCLAW_CONFIG
            if not config.exists():
                # OpenClaw 2026.5.x refuses to start when gateway.mode is missing
                # ("Gateway start blocked: existing config is missing gateway.mode").
                # A bare "{}" placeholder is therefore not enough — seed the minimal
                # valid local-gateway shape so a first run before the user has saved
                # a provider profile still boots instead of hard-failing.
                config.parent.mkdir(parents=True, exist_ok=True)
                config.write_text(
                    json.dumps({"gateway": {"mode": "local"}}, indent=2),
                    encoding="utf-8",
                )
            env = {
                **os.environ,
                **read_env_file(self._repo_root / ".env"),
                "OPENCLAW_STATE_DIR": str(home),
                "OPENCLAW_CONFIG_PATH": str(config),
                "HOME": str(home),
                "USERPROFILE": str(home),
            }
            # Do NOT disable bundled plugins by default: the agent harness depends
            # on OpenClaw's bundled plugin surfaces (e.g. speech-core/runtime-api),
            # and disabling them makes every agent run fail with
            # "Unable to resolve bundled plugin public surface ...". Only honour the
            # flag if the operator explicitly set it in their environment.
            disable_plugins = os.environ.get("OPENCLAW_DISABLE_BUNDLED_PLUGINS")
            if disable_plugins is not None:
                env["OPENCLAW_DISABLE_BUNDLED_PLUGINS"] = disable_plugins

            cmd = [node, str(script), "gateway", "run", "--verbose"]
            logger.info("Starting OpenClaw Gateway: %s", " ".join(cmd))

            # Write Gateway output to a log file for debugging
            self._gateway_log = (self._repo_root / "gateway.log").open(
                "w", encoding="utf-8"
            )
            self._process = subprocess.Popen(
                cmd,
                cwd=str(self._repo_root),
                env=env,
                stdout=self._gateway_log,
                stderr=subprocess.STDOUT,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                ),
            )
            (lock_dir / "pid").write_text(str(self._process.pid), encoding="utf-8")
            logger.info("Gateway started (pid=%d)", self._process.pid)
        except Exception:
            self._release_launch_lock()
            if self._gateway_log is not None:
                self._gateway_log.close()
                self._gateway_log = None
            raise

    async def wait_ready(self, timeout_sec: float = 15.0) -> bool:
        """Wait until the Gateway WebSocket port is accepting connections."""
        deadline = asyncio.get_event_loop().time() + timeout_sec
        while asyncio.get_event_loop().time() < deadline:
            # Check subprocess hasn't crashed
            if self._process is not None and self._process.poll() is not None:
                logger.error("Gateway process exited with code %d", self._process.returncode)
                return False
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", self._port),
                    timeout=1.0,
                )
                writer.close()
                await writer.wait_closed()
                # Double-check our process is still alive after TCP succeeds.
                # If our process died but port is reachable, another process
                # (e.g., stale Gateway) is on the port — that's a false positive.
                if self._process is not None and self._process.poll() is not None:
                    logger.error(
                        "Gateway died (code=%d) but port %d reachable by another process",
                        self._process.returncode,
                        self._port,
                    )
                    return False
                logger.info("Gateway is ready on port %d", self._port)
                return True
            except (ConnectionRefusedError, OSError, TimeoutError):
                await asyncio.sleep(0.5)
        logger.error("Gateway did not become ready within %.0fs", timeout_sec)
        return False

    def stop(self) -> None:
        """Stop the Gateway subprocess."""
        if self._process is None:
            return
        if self._process.poll() is not None:
            logger.info("Gateway already stopped (code=%d)", self._process.returncode)
            self._process = None
            self._release_launch_lock()
            if self._gateway_log is not None:
                self._gateway_log.close()
                self._gateway_log = None
            return
        logger.info("Stopping Gateway (pid=%d)...", self._process.pid)
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Gateway did not stop gracefully, killing")
            self._process.kill()
            self._process.wait(timeout=3)
        self._process = None
        if self._gateway_log is not None:
            self._gateway_log.close()
            self._gateway_log = None
        self._release_launch_lock()
        logger.info("Gateway stopped")

    async def ensure_running(self) -> bool:
        """Check if the Gateway is alive; if not, restart it.

        Returns True if the Gateway is up and ready after this call.
        """
        if self.is_running:
            return True

        exit_code = self._process.returncode if self._process else None
        logger.warning(
            "Gateway process is dead (exit_code=%s), restarting...",
            exit_code,
        )
        self._process = None

        try:
            self.start()
            return await self.wait_ready(timeout_sec=15.0)
        except Exception:
            logger.exception("Gateway restart failed")
            return False
