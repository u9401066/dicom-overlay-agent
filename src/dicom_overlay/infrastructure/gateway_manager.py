"""OpenClaw Gateway subprocess manager — starts/stops the Node.js gateway."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TextIO

import structlog

logger = structlog.get_logger(__name__)

# Relative paths from repo root
_OPENCLAW_MJS = Path("openclaw/node_modules/openclaw/openclaw.mjs")
_OPENCLAW_CONFIG = Path("openclaw/openclaw.json")
_OPENCLAW_HOME = Path("openclaw-home")
_SRC_SKILLS = Path("openclaw/workspace/skills")
_DST_SKILLS = _OPENCLAW_HOME / ".openclaw" / "workspace" / "skills"


class GatewayManager:
    """Manages the OpenClaw Gateway Node.js subprocess lifecycle."""

    def __init__(self, repo_root: Path | None = None, port: int = 18789) -> None:
        self._repo_root = repo_root or Path.cwd()
        self._port = port
        self._process: subprocess.Popen | None = None
        self._gateway_log: TextIO | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _find_node(self) -> str:
        """Find node executable, preferring repo-local install."""
        node = shutil.which("node")
        if node is None:
            msg = (
                "Node.js not found on PATH. "
                "Install Node.js (https://nodejs.org) to run the OpenClaw Gateway."
            )
            raise FileNotFoundError(msg)
        return node

    def _gateway_script(self) -> Path:
        script = self._repo_root / _OPENCLAW_MJS
        if not script.exists():
            msg = (
                f"OpenClaw not found at {script}. "
                "Run scripts\\install-openclaw-local.bat first."
            )
            raise FileNotFoundError(msg)
        return script

    def _sync_skills(self) -> None:
        """Sync workspace skills to openclaw-home (mirrors sync-openclaw-workspace.bat)."""
        src = self._repo_root / _SRC_SKILLS
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

        # Kill any stale process occupying the port before starting
        self._kill_port_occupant()

        node = self._find_node()
        script = self._gateway_script()

        self._ensure_dirs()
        self._sync_skills()

        home = self._repo_root / _OPENCLAW_HOME
        config = self._repo_root / _OPENCLAW_CONFIG
        env = {
            **os.environ,
            "OPENCLAW_STATE_DIR": str(home),
            "OPENCLAW_CONFIG_PATH": str(config),
            "HOME": str(home),
            "USERPROFILE": str(home),
        }

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
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if sys.platform == "win32"
                else 0
            ),
        )
        logger.info("Gateway started (pid=%d)", self._process.pid)

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
