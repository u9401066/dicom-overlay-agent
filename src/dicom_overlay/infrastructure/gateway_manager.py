"""OpenClaw Gateway subprocess manager — starts/stops the Node.js gateway."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

import structlog

if TYPE_CHECKING:
    from collections.abc import Mapping

from dicom_overlay.infrastructure.env_file import read_env_file
from dicom_overlay.infrastructure.openclaw_runtime import (
    ensure_openclaw_runtime_supported,
)
from dicom_overlay.infrastructure.openclaw_settings import (
    DEFAULT_INFERENCE_TIMEOUT_SEC,
    DEFAULT_VISION_PROFILE_KEY,
    build_analysis_tool_policy,
    build_openclaw_config,
    default_provider_profiles,
    derive_openclaw_timeout_budget,
)

logger = structlog.get_logger(__name__)

# Relative paths from repo root
_OPENCLAW_MJS = Path("openclaw/node_modules/openclaw/openclaw.mjs")
_OPENCLAW_CONFIG = Path("openclaw/openclaw.json")
_OPENCLAW_HOME = Path("openclaw-home")
_SRC_SKILLS = Path("openclaw/workspace/skills")
_DST_SKILLS = _OPENCLAW_HOME / ".openclaw" / "workspace" / "skills"
_SRC_PLUGINS = Path("openclaw/workspace/plugins")
_DST_PLUGINS = _OPENCLAW_HOME / ".openclaw" / "workspace" / "plugins"
_HARNESS_PLUGIN = "dicom-overlay-agent-harness"
_ECG_FOUNDER_TOOL = "ecg_founder_analyze_waveform"
_GATEWAY_LAUNCH_LOCK = Path("data/tmp/openclaw-gateway.lock")


def ecg_founder_tool_enabled(environment: Mapping[str, str]) -> bool:
    """Return whether the authenticated loopback sidecar is configured."""
    return bool(
        environment.get("DICOM_ECGFOUNDER_ENDPOINT", "").strip()
        and environment.get("DICOM_ECGFOUNDER_TOKEN", "").strip()
    )


def _windows_pid_is_running(pid: int) -> bool:
    """Check process liveness without Windows' unreliable ``os.kill(pid, 0)``."""
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    access_denied = 5
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, wintypes.LPDWORD]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return ctypes.get_last_error() == access_denied
    exit_code = wintypes.DWORD()
    try:
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def pid_is_running(pid: int) -> bool:
    """Return whether a process is alive on the current platform."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _windows_pid_is_running(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


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

    def node_executable(self) -> str:
        """Return the Node.js binary this app would use for OpenClaw."""
        return self._find_node()

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

        package_root = self._resource_root() / "openclaw" / "node_modules" / "openclaw"
        bundled_skills = package_root / "skills"
        skill_count = sum(1 for _ in bundled_skills.glob("*/SKILL.md"))
        rows.append(
            (
                "openclaw_bundled_skills",
                skill_count > 0,
                f"{bundled_skills} ({skill_count} skill(s))",
            )
        )
        surface_dirs = (
            package_root / "dist" / "extensions",
            package_root / "dist" / "plugins",
            package_root / "dist" / "plugin-sdk",
        )
        missing_surfaces = [str(path) for path in surface_dirs if not path.is_dir()]
        rows.append(
            (
                "openclaw_plugin_surfaces",
                not missing_surfaces,
                (
                    str(package_root / "dist")
                    if not missing_surfaces
                    else f"missing: {', '.join(missing_surfaces)}"
                ),
            )
        )
        harness_root = self._resource_root() / _SRC_PLUGINS / _HARNESS_PLUGIN
        harness_files = (
            harness_root / "package.json",
            harness_root / "openclaw.plugin.json",
            harness_root / "index.js",
        )
        missing_harness_files = [
            str(path) for path in harness_files if not path.is_file()
        ]
        rows.append(
            (
                "harness_native_plugin",
                not missing_harness_files,
                (
                    str(harness_root)
                    if not missing_harness_files
                    else f"missing: {', '.join(missing_harness_files)}"
                ),
            )
        )

        try:
            with tempfile.TemporaryDirectory(
                prefix=".dicom-overlay-selfcheck-",
                dir=self._repo_root,
            ) as temp_text:
                workspace = Path(temp_text) / _OPENCLAW_HOME / ".openclaw" / "workspace"
                workspace.mkdir(parents=True)
                probe = workspace / "write-probe"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink()
            rows.append(("writable_base", True, str(self._repo_root)))
        except OSError as exc:
            rows.append(("writable_base", False, str(exc)))

        return rows

    def _sync_skills(self) -> None:
        """Mirror app-owned skills and the native harness plugin into state."""
        self._sync_skills_to(self._repo_root / _OPENCLAW_HOME)

    def _sync_skills_to(self, state_home: Path) -> None:
        workspace = state_home / ".openclaw" / "workspace"
        skills_dst = workspace / "skills"
        plugins_dst = workspace / "plugins"
        roots = (
            (self._resource_root() / _SRC_SKILLS, skills_dst),
            (self._resource_root() / _SRC_PLUGINS, plugins_dst),
        )
        for src, dst in roots:
            if not src.is_dir():
                raise FileNotFoundError(f"OpenClaw workspace source not found: {src}")
            dst.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                result = subprocess.run(
                    [
                        "robocopy",
                        str(src),
                        str(dst),
                        "/MIR",
                        "/NFL",
                        "/NDL",
                        "/NJH",
                        "/NJS",
                        "/NP",
                    ],
                    capture_output=True,
                    check=False,
                )
                if result.returncode >= 8:
                    raise RuntimeError(
                        f"robocopy failed ({result.returncode}) syncing {src}"
                    )
            else:
                subprocess.run(
                    ["rsync", "-a", "--delete", f"{src}/", f"{dst}/"],
                    capture_output=True,
                    check=True,
                )
            logger.info("Synced OpenClaw workspace assets to %s", dst)

        required = [
            skills_dst / name / filename
            for name in (
                "dicom-ekg-analysis",
                "dicom-cxr-analysis",
                "dicom-ct-brain-analysis",
            )
            for filename in ("SKILL.md", "schema.json")
        ]
        required.extend(
            plugins_dst / _HARNESS_PLUGIN / filename
            for filename in ("package.json", "openclaw.plugin.json", "index.js")
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise RuntimeError(
                "OpenClaw workspace sync incomplete: " + ", ".join(missing)
            )

    def _ensure_dirs(self) -> None:
        """Ensure openclaw-home directory structure exists."""
        home = self._repo_root / _OPENCLAW_HOME
        (home / ".openclaw" / "workspace").mkdir(parents=True, exist_ok=True)

    def prepare_workspace(self, *, state_home: Path | None = None) -> None:
        """Materialize the exact app-owned skills/plugins used by a Gateway.

        Experiment runners call this public boundary before launching their own
        Gateway process so they cannot accidentally evaluate stale state from a
        previous desktop session.
        """
        if state_home is None:
            self._ensure_dirs()
            self._sync_skills()
            return
        state_home = Path(state_home).resolve()
        (state_home / ".openclaw" / "workspace").mkdir(
            parents=True,
            exist_ok=True,
        )
        self._sync_skills_to(state_home)

    def _ensure_openclaw_config(self) -> Path:
        """Seed a secret-free vision profile and activate the bundled plugin."""
        config_path = self._repo_root / _OPENCLAW_CONFIG
        if config_path.exists():
            try:
                payload = json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Invalid OpenClaw config: {config_path}") from exc
            if not isinstance(payload, dict):
                raise RuntimeError(f"Invalid OpenClaw config root: {config_path}")
        else:
            profile = next(
                item
                for item in default_provider_profiles()
                if item.key == DEFAULT_VISION_PROFILE_KEY
            )
            payload = build_openclaw_config(profile)

        gateway = payload.get("gateway")
        if not isinstance(gateway, dict):
            gateway = {}
            payload["gateway"] = gateway
        gateway.setdefault("mode", "local")

        env_values = {
            **read_env_file(self._repo_root / ".env"),
            **os.environ,
        }
        if env_values.get("OPENCLAW_GATEWAY_TOKEN", "").strip():
            auth = gateway.setdefault("auth", {})
            if isinstance(auth, dict):
                auth.setdefault("token", "${OPENCLAW_GATEWAY_TOKEN}")
        elif (
            isinstance(gateway.get("auth"), dict)
            and gateway["auth"].get("token") == "${OPENCLAW_GATEWAY_TOKEN}"
        ):
            gateway.pop("auth", None)

        agents = payload.setdefault("agents", {})
        if not isinstance(agents, dict):
            agents = {}
            payload["agents"] = agents
        defaults = agents.setdefault("defaults", {})
        if not isinstance(defaults, dict):
            defaults = {}
            agents["defaults"] = defaults
        primary = defaults.get("model")
        configured_primary = (
            primary.get("primary") if isinstance(primary, dict) else primary
        )
        if not isinstance(configured_primary, str) or not configured_primary.strip():
            profile = next(
                item
                for item in default_provider_profiles()
                if item.key == DEFAULT_VISION_PROFILE_KEY
            )
            managed = build_openclaw_config(profile)
            defaults.update(managed["agents"]["defaults"])
            models = payload.setdefault("models", {})
            if not isinstance(models, dict):
                models = {}
                payload["models"] = models
            providers = models.setdefault("providers", {})
            if not isinstance(providers, dict):
                providers = {}
                models["providers"] = providers
            providers.setdefault(
                profile.provider_id,
                managed["models"]["providers"][profile.provider_id],
            )

        provider_timeout_sec, agent_timeout_sec = derive_openclaw_timeout_budget(
            DEFAULT_INFERENCE_TIMEOUT_SEC
        )
        defaults.setdefault("timeoutSeconds", agent_timeout_sec)
        primary = defaults.get("model")
        configured_primary = (
            primary.get("primary", "") if isinstance(primary, dict) else primary
        )
        if isinstance(configured_primary, str):
            provider_id = configured_primary.partition("/")[0]
            models = payload.get("models", {})
            providers = models.get("providers", {}) if isinstance(models, dict) else {}
            provider = (
                providers.get(provider_id) if isinstance(providers, dict) else None
            )
            if isinstance(provider, dict):
                provider.setdefault("timeoutSeconds", provider_timeout_sec)

        plugin_path = (self._repo_root / _DST_PLUGINS / _HARNESS_PLUGIN).resolve()
        plugins = payload.setdefault("plugins", {})
        if not isinstance(plugins, dict):
            plugins = {}
            payload["plugins"] = plugins
        allow = plugins.setdefault("allow", [])
        if not isinstance(allow, list):
            allow = []
            plugins["allow"] = allow
        if _HARNESS_PLUGIN not in allow:
            allow.append(_HARNESS_PLUGIN)
        load = plugins.setdefault("load", {})
        if not isinstance(load, dict):
            load = {}
            plugins["load"] = load
        paths = load.setdefault("paths", [])
        if not isinstance(paths, list):
            paths = []
            load["paths"] = paths
        plugin_path_text = str(plugin_path)
        if plugin_path_text not in paths:
            paths.append(plugin_path_text)
        entries = plugins.setdefault("entries", {})
        if not isinstance(entries, dict):
            entries = {}
            plugins["entries"] = entries
        entry = entries.setdefault(_HARNESS_PLUGIN, {})
        if not isinstance(entry, dict):
            entry = {}
            entries[_HARNESS_PLUGIN] = entry
        entry["enabled"] = True

        # Keep the model tool surface bounded. ECGFounder is exposed only when
        # an authenticated loopback sidecar is explicitly configured; normal
        # screenshot-only runs retain the single bbox validation tool.
        allowed_tools = ["dicom_bbox_validate"]
        if ecg_founder_tool_enabled(env_values):
            allowed_tools.append(_ECG_FOUNDER_TOOL)
        payload["tools"] = build_analysis_tool_policy(allowed_tools)

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return config_path

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
        return pid_is_running(pid)

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
                    logger.warning(
                        "Killing process %d occupying port %d", pid, self._port
                    )
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

            self.prepare_workspace()

            home = self._repo_root / _OPENCLAW_HOME
            config = self._ensure_openclaw_config()
            env = {
                **os.environ,
                **read_env_file(self._repo_root / ".env"),
                "OPENCLAW_STATE_DIR": str(home),
                "OPENCLAW_CONFIG_PATH": str(config),
                "HOME": str(home),
                "USERPROFILE": str(home),
                "DICOM_BBOX_AUDIT_PATH": str(
                    self._repo_root / "data" / "tmp" / "bbox-tool-audit.jsonl"
                ),
            }
            env.setdefault(
                "DICOM_ECGFOUNDER_AUDIT_PATH",
                str(self._repo_root / "data" / "tmp" / "ecgfounder-tool-audit.jsonl"),
            )
            Path(env["DICOM_BBOX_AUDIT_PATH"]).parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            Path(env["DICOM_ECGFOUNDER_AUDIT_PATH"]).parent.mkdir(
                parents=True,
                exist_ok=True,
            )
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
                logger.error(
                    "Gateway process exited with code %d", self._process.returncode
                )
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
