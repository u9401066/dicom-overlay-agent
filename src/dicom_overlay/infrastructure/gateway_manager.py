"""OpenClaw Gateway subprocess manager — starts/stops the Node.js gateway."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, TextIO
from uuid import uuid4

import structlog

if TYPE_CHECKING:
    from collections.abc import Mapping

from dicom_overlay.infrastructure.codex_subscription_auth import (
    CODEX_MIGRATION_PLUGIN_VERSION,
    ensure_openclaw_subscription_auth,
    resolve_native_codex_home,
    uses_codex_subscription_transport,
)
from dicom_overlay.infrastructure.env_file import read_env_file
from dicom_overlay.infrastructure.openclaw_paths import resolve_bbox_tool_audit_path
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
_OPENAI_PROVIDER_PLUGIN = "openai"
_ECG_FOUNDER_TOOL = "ecg_founder_analyze_waveform"
_GATEWAY_LAUNCH_LOCK = Path("data/tmp/openclaw-gateway.lock")
_GATEWAY_OWNERSHIP_RECEIPT = "ownership.json"
_GATEWAY_OWNERSHIP_SCHEMA_VERSION = 2
_GATEWAY_STARTUP_REUSE_WAIT_SEC = 3.0
_GATEWAY_STARTUP_REUSE_POLL_SEC = 0.1
DEFAULT_GATEWAY_READY_TIMEOUT_SEC = 180.0


def ecg_founder_tool_enabled(environment: Mapping[str, str]) -> bool:
    """Return whether the authenticated loopback sidecar is configured."""
    return bool(
        environment.get("DICOM_ECGFOUNDER_ENDPOINT", "").strip()
        and environment.get("DICOM_ECGFOUNDER_TOKEN", "").strip()
    )


def _uses_openai_subscription_provider(config: Mapping[str, object]) -> bool:
    models = config.get("models")
    providers = models.get("providers") if isinstance(models, dict) else None
    openai = providers.get("openai") if isinstance(providers, dict) else None
    return bool(
        isinstance(openai, dict)
        and openai.get("api") == "openai-chatgpt-responses"
        and "apiKey" not in openai
        and "baseUrl" not in openai
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

    def __init__(
        self,
        repo_root: Path | None = None,
        port: int = 18789,
        *,
        ready_timeout_sec: float = DEFAULT_GATEWAY_READY_TIMEOUT_SEC,
        bbox_tool_audit_path: str | Path | None = None,
    ) -> None:
        if (
            isinstance(port, bool)
            or not isinstance(port, int)
            or not 1 <= port <= 65535
        ):
            raise ValueError("port must be an integer between 1 and 65535")
        if (
            isinstance(ready_timeout_sec, bool)
            or not isinstance(ready_timeout_sec, (int, float))
            or not 5 <= ready_timeout_sec <= 600
        ):
            raise ValueError("ready_timeout_sec must be between 5 and 600 seconds")
        self._repo_root = (repo_root or Path.cwd()).resolve()
        self._port = port
        self._bbox_tool_audit_path = resolve_bbox_tool_audit_path(
            self._repo_root,
            explicit_path=bbox_tool_audit_path,
        )
        self._ready_timeout_sec = float(ready_timeout_sec)
        self._process: subprocess.Popen | None = None
        self._gateway_log: TextIO | None = None
        self._launch_lock_dir: Path | None = None
        self._launch_lock_token: str | None = None
        self._reused_gateway = False
        self._reused_pid: int | None = None

    @property
    def is_running(self) -> bool:
        if self._process is not None:
            return self._process.poll() is None
        if not self._reused_gateway:
            return False
        return self._reused_pid is not None and self._pid_is_running(self._reused_pid)

    @property
    def bbox_tool_audit_path(self) -> Path:
        """Absolute receipt path passed to the Gateway plugin."""

        return self._bbox_tool_audit_path

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
        codex_migration = package_root / "dist" / "extensions" / "codex"
        try:
            codex_package = json.loads(
                (codex_migration / "package.json").read_text(encoding="utf-8")
            )
            codex_bundle = json.loads(
                (codex_migration / "migration-bundle.json").read_text(
                    encoding="utf-8-sig"
                )
            )
        except (OSError, json.JSONDecodeError):
            codex_package = {}
            codex_bundle = {}
        codex_migration_ready = bool(
            codex_package.get("name") == "@openclaw/codex"
            and codex_package.get("version") == CODEX_MIGRATION_PLUGIN_VERSION
            and codex_bundle.get("purpose") == "oauth_migration_only"
            and codex_bundle.get("codex_agent_runtime_dependencies_bundled") is False
            and (codex_migration / "dist" / "index.js").is_file()
            and not (codex_migration / "node_modules" / "@openai" / "codex").exists()
            and not (package_root.parent / "@openai" / "codex").exists()
        )
        rows.append(
            (
                "codex_oauth_migration_provider",
                codex_migration_ready,
                str(codex_migration),
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
        # Bind the selected workspace to the assets we actually synchronized;
        # do not depend on an upstream version's implicit HOME/state default.
        defaults["workspace"] = str(
            (self._repo_root / _OPENCLAW_HOME / ".openclaw" / "workspace").resolve()
        )
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
        plugins["allow"] = [item for item in allow if item != "codex"]
        allow = plugins["allow"]
        subscription_transport = _uses_openai_subscription_provider(payload)
        if subscription_transport and _OPENAI_PROVIDER_PLUGIN not in allow:
            allow.append(_OPENAI_PROVIDER_PLUGIN)
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
        # Absence is not a disable policy for a bundled default-on plugin.
        # OAuth migration temporarily enables its isolated provider, then
        # restores this explicit runtime boundary before Gateway startup.
        entries["codex"] = {"enabled": False}
        if subscription_transport:
            provider_entry = entries.setdefault(_OPENAI_PROVIDER_PLUGIN, {})
            if not isinstance(provider_entry, dict):
                provider_entry = {}
                entries[_OPENAI_PROVIDER_PLUGIN] = provider_entry
            provider_entry["enabled"] = True

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
        self._launch_lock_token = uuid4().hex
        try:
            (lock_dir / "owner").write_text(
                self._launch_lock_token,
                encoding="utf-8",
            )
        except OSError:
            shutil.rmtree(lock_dir, ignore_errors=True)
            self._launch_lock_dir = None
            self._launch_lock_token = None
            raise
        return lock_dir

    def _release_launch_lock(self) -> None:
        """Release the launch lock held by this manager, if any."""
        if self._launch_lock_dir is None:
            return
        if self._launch_lock_token is not None:
            try:
                current_token = (self._launch_lock_dir / "owner").read_text(
                    encoding="utf-8"
                )
            except OSError:
                current_token = ""
            if current_token != self._launch_lock_token:
                logger.warning(
                    "OpenClaw launch lock ownership changed; refusing to remove it",
                    lock_dir=str(self._launch_lock_dir),
                )
                self._launch_lock_dir = None
                self._launch_lock_token = None
                return
        shutil.rmtree(self._launch_lock_dir, ignore_errors=True)
        self._launch_lock_dir = None
        self._launch_lock_token = None

    def _read_lock_pid(self, lock_dir: Path) -> int | None:
        try:
            return int((lock_dir / "pid").read_text(encoding="utf-8").strip())
        except (FileNotFoundError, OSError, ValueError):
            return None

    def _resolved_gateway_token(self) -> str:
        from dicom_overlay.infrastructure.openclaw_client import (
            resolve_openclaw_gateway_token,
        )

        return resolve_openclaw_gateway_token(self._repo_root) or ""

    def _token_fingerprint(self) -> str:
        return hashlib.sha256(
            self._resolved_gateway_token().encode("utf-8")
        ).hexdigest()

    def _write_gateway_ownership_receipt(
        self,
        lock_dir: Path,
        supervisor_pid: int,
        *,
        listener_pid: int | None = None,
    ) -> None:
        """Write non-secret starting/ready ownership through an atomic replace."""

        if not self._launch_lock_token:
            raise RuntimeError("cannot write Gateway ownership without launch owner")
        receipt = {
            "schema_version": _GATEWAY_OWNERSHIP_SCHEMA_VERSION,
            "status": "ready" if listener_pid is not None else "starting",
            "supervisor_pid": supervisor_pid,
            "listener_pid": listener_pid,
            "port": self._port,
            "token_sha256": self._token_fingerprint(),
            "bbox_audit_path": str(self._bbox_tool_audit_path),
            "launch_owner_sha256": hashlib.sha256(
                self._launch_lock_token.encode("utf-8")
            ).hexdigest(),
        }
        pending = lock_dir / f"{_GATEWAY_OWNERSHIP_RECEIPT}.tmp"
        pending.write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        pending.replace(lock_dir / _GATEWAY_OWNERSHIP_RECEIPT)

    def _bind_gateway_listener_ownership(self) -> bool:
        """Publish the authenticated listener PID beside the supervisor PID.

        The public ``openclaw.mjs`` launcher may respawn itself to configure
        Node's compile cache.  In that case ``Popen.pid`` belongs to the
        supervising launcher while the child owns the Gateway port.  Reuse must
        be tied to the actual listener observed after a successful public
        ``connect`` handshake, not to an implementation assumption about the
        launcher's process topology.
        """

        lock_dir = self._launch_lock_dir
        launch_token = self._launch_lock_token
        if self._process is None or lock_dir is None or not launch_token:
            return False
        try:
            current_token = (lock_dir / "owner").read_text(encoding="utf-8")
        except OSError:
            return False
        if not hmac.compare_digest(current_token, launch_token):
            logger.error("Gateway launch ownership changed before listener binding")
            return False

        listener_pids = self._port_occupant_pids()
        if len(listener_pids) != 1:
            logger.error(
                "Expected exactly one authenticated Gateway listener on port %d; "
                "observed pids=%s",
                self._port,
                sorted(listener_pids),
            )
            return False
        listener_pid = next(iter(listener_pids))
        if not self._pid_is_running(listener_pid):
            logger.error(
                "Authenticated Gateway listener pid %d is not live", listener_pid
            )
            return False
        try:
            self._write_gateway_ownership_receipt(
                lock_dir,
                self._process.pid,
                listener_pid=listener_pid,
            )
        except OSError:
            logger.exception("Failed to bind Gateway ownership to listener pid")
            return False
        return True

    def _matching_gateway_ownership_receipt(
        self,
    ) -> tuple[str, int, int | None] | None:
        """Read a live peer's non-secret schema-v2 ownership contract."""

        lock_dir = self._repo_root / _GATEWAY_LAUNCH_LOCK
        lock_pid = self._read_lock_pid(lock_dir)
        try:
            owner = (lock_dir / "owner").read_text(encoding="utf-8")
            receipt = json.loads(
                (lock_dir / _GATEWAY_OWNERSHIP_RECEIPT).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(receipt, dict) or lock_pid is None:
            return None
        expected_keys = {
            "schema_version",
            "status",
            "supervisor_pid",
            "listener_pid",
            "port",
            "token_sha256",
            "bbox_audit_path",
            "launch_owner_sha256",
        }
        if set(receipt) != expected_keys or not owner:
            return None
        status = receipt.get("status")
        supervisor_pid = receipt.get("supervisor_pid")
        listener_pid = receipt.get("listener_pid")
        port = receipt.get("port")
        if (
            receipt.get("schema_version") != _GATEWAY_OWNERSHIP_SCHEMA_VERSION
            or status not in {"starting", "ready"}
            or isinstance(supervisor_pid, bool)
            or not isinstance(supervisor_pid, int)
            or supervisor_pid <= 0
            or supervisor_pid != lock_pid
            or isinstance(port, bool)
            or port != self._port
        ):
            return None
        if status == "starting":
            if listener_pid is not None:
                return None
        elif (
            isinstance(listener_pid, bool)
            or not isinstance(listener_pid, int)
            or listener_pid <= 0
        ):
            return None
        token_fingerprint = receipt.get("token_sha256")
        owner_fingerprint = receipt.get("launch_owner_sha256")
        if not isinstance(token_fingerprint, str) or not hmac.compare_digest(
            token_fingerprint,
            self._token_fingerprint(),
        ):
            return None
        expected_owner_fingerprint = hashlib.sha256(owner.encode("utf-8")).hexdigest()
        if not isinstance(owner_fingerprint, str) or not hmac.compare_digest(
            owner_fingerprint,
            expected_owner_fingerprint,
        ):
            return None
        raw_audit_path = receipt.get("bbox_audit_path")
        if not isinstance(raw_audit_path, str) or not raw_audit_path.strip():
            return None
        try:
            receipt_audit_path = Path(raw_audit_path).resolve()
        except OSError:
            return None
        if receipt_audit_path != self._bbox_tool_audit_path:
            return None
        if not self._pid_is_running(supervisor_pid):
            return None
        if listener_pid is not None and not self._pid_is_running(listener_pid):
            return None
        return status, supervisor_pid, listener_pid

    def _verified_gateway_owner_pid(self) -> int | None:
        """Return the listener PID only for a complete matching ownership receipt."""

        receipt = self._matching_gateway_ownership_receipt()
        if receipt is None:
            return None
        status, _supervisor_pid, listener_pid = receipt
        if (
            status != "ready"
            or listener_pid is None
            or listener_pid not in self._port_occupant_pids()
        ):
            return None
        return listener_pid

    def _startup_reuse_clock(self) -> float:
        """Monotonic clock seam for fast deterministic startup-race tests."""

        return time.monotonic()

    def _startup_reuse_sleep(self, delay_sec: float) -> None:
        """Sleep seam for the synchronous, bounded peer-startup wait."""

        time.sleep(delay_sec)

    def _wait_for_gateway_startup_owner(
        self,
        supervisor_pid: int,
        *,
        initial_probe_ready: bool,
    ) -> None:
        """Wait briefly for a verified live peer to publish its ready receipt.

        This path is intentionally read-only.  A second desktop instance may
        observe the launcher's atomic ``starting`` receipt before the public
        Gateway handshake is available, or may complete the handshake just
        before the launcher atomically replaces that receipt with ``ready``.
        Neither ordering grants this manager ownership of the peer's lock or
        process.
        """

        deadline = self._startup_reuse_clock() + _GATEWAY_STARTUP_REUSE_WAIT_SEC
        probe_ready = initial_probe_ready
        while True:
            receipt = self._matching_gateway_ownership_receipt()
            if receipt is None or receipt[1] != supervisor_pid:
                raise RuntimeError(
                    "OpenClaw Gateway startup ownership receipt became invalid or "
                    "changed; refusing to reuse or terminate the unowned process"
                )
            status = receipt[0]
            if probe_ready and status == "ready":
                self._mark_gateway_reused()
                return

            now = self._startup_reuse_clock()
            if now >= deadline:
                raise RuntimeError(
                    "OpenClaw Gateway startup owner did not become ready within "
                    f"{_GATEWAY_STARTUP_REUSE_WAIT_SEC:g}s; refusing to start a "
                    "second process or alter the live launch lock"
                )
            self._startup_reuse_sleep(
                min(_GATEWAY_STARTUP_REUSE_POLL_SEC, deadline - now)
            )
            probe_ready = self._probe_existing_gateway()

    def _pid_is_running(self, pid: int) -> bool:
        return pid_is_running(pid)

    def _probe_existing_gateway(self) -> bool:
        """Authenticate through public ``connect`` before reusing a listener."""

        from dicom_overlay.infrastructure.openclaw_client import (
            probe_openclaw_gateway,
            resolve_openclaw_gateway_token,
        )

        return probe_openclaw_gateway(
            f"ws://127.0.0.1:{self._port}",
            gateway_token=resolve_openclaw_gateway_token(self._repo_root),
            timeout_sec=1.5,
        )

    def _port_occupant_pids(self) -> set[int]:
        """Return listeners on the configured port without mutating processes."""

        if sys.platform != "win32":
            try:
                result = subprocess.run(
                    ["lsof", "-ti", f"tcp:{self._port}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except (FileNotFoundError, TypeError):
                return set()
            pids: set[int] = set()
            for value in result.stdout.split():
                try:
                    pids.add(int(value))
                except ValueError:
                    continue
            return pids

        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, TypeError):
            return set()
        pids = set()
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 5 or parts[0].upper() != "TCP":
                continue
            if parts[3].upper() != "LISTENING":
                continue
            _host, separator, port_text = parts[1].rpartition(":")
            if not separator or port_text != str(self._port):
                continue
            try:
                pids.add(int(parts[-1]))
            except ValueError:
                continue
        return pids

    def _mark_gateway_reused(self) -> None:
        self._reused_gateway = False
        self._reused_pid = None
        owner_pid = self._verified_gateway_owner_pid()
        if owner_pid is None:
            raise RuntimeError(
                "Healthy OpenClaw Gateway lacks a matching local ownership receipt; "
                "refusing external clinical reuse without verified pid, port, token "
                "fingerprint, and bbox audit path"
            )
        self._reused_pid = owner_pid
        self._reused_gateway = True
        logger.info(
            "Reusing healthy OpenClaw Gateway on port %d (pid=%s)",
            self._port,
            self._reused_pid,
        )

    def _kill_port_occupant(self) -> None:
        """Terminate only a port listener proven to be owned by this manager.

        Kept as a narrow compatibility hook for callers/tests.  Startup no
        longer uses it to kill arbitrary listeners.
        """

        if self._process is None or self._process.poll() is not None:
            return
        if self._process.pid not in self._port_occupant_pids():
            return
        self._process.terminate()

    def start(self) -> None:
        """Start the Gateway subprocess (non-blocking)."""
        if self.is_running:
            logger.info(
                "Gateway already running (pid=%s)",
                self._process.pid if self._process is not None else self._reused_pid,
            )
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

        # Validate the public protocol before touching a process or lock.  This
        # allows multiple desktop instances to share one healthy local Gateway
        # and, critically, never treats an arbitrary live listener as killable.
        probe_ready = self._probe_existing_gateway()
        if probe_ready and self._verified_gateway_owner_pid() is not None:
            self._mark_gateway_reused()
            return

        ownership = self._matching_gateway_ownership_receipt()
        if ownership is not None:
            self._wait_for_gateway_startup_owner(
                ownership[1],
                initial_probe_ready=probe_ready,
            )
            return
        if probe_ready:
            # Preserve the strict refusal for a healthy listener without a
            # matching app-owned receipt.  It is never safe to adopt or kill it.
            self._mark_gateway_reused()
            return

        lock_dir = self._acquire_launch_lock()
        try:
            # Close the acquire/probe race: a peer may have completed startup
            # immediately before this manager took the lock.
            if self._probe_existing_gateway():
                self._release_launch_lock()
                self._mark_gateway_reused()
                return
            occupant_pids = self._port_occupant_pids()
            if occupant_pids:
                raise RuntimeError(
                    "Port "
                    f"{self._port} is occupied by an unhealthy or non-OpenClaw "
                    "listener; refusing to terminate an unowned process "
                    f"(pid={','.join(str(pid) for pid in sorted(occupant_pids))})"
                )

            node = self._find_node()
            script = self._gateway_script()

            self.prepare_workspace()

            home = self._repo_root / _OPENCLAW_HOME
            config = self._ensure_openclaw_config()
            subscription_transport = uses_codex_subscription_transport(config)
            if subscription_transport:
                ensure_openclaw_subscription_auth(
                    node_executable=node,
                    openclaw_cli=script,
                    config_path=config,
                    state_home=home,
                    source_codex_home=resolve_native_codex_home(os.environ),
                    plugin_path=(
                        self._resource_root()
                        / "openclaw"
                        / "node_modules"
                        / "openclaw"
                        / "dist"
                        / "extensions"
                        / "codex"
                    ),
                    working_directory=self._repo_root,
                    audit_path=(
                        self._repo_root / "data" / "tmp" / "codex-auth-import.json"
                    ),
                )
            env = {
                **os.environ,
                **read_env_file(self._repo_root / ".env"),
                "OPENCLAW_STATE_DIR": str(home),
                "OPENCLAW_CONFIG_PATH": str(config),
                "HOME": str(home),
                "USERPROFILE": str(home),
                "DICOM_BBOX_AUDIT_PATH": str(self._bbox_tool_audit_path),
            }
            resolved_gateway_token = self._resolved_gateway_token()
            if resolved_gateway_token:
                # The ownership fingerprint and the spawned listener must refer
                # to the exact same effective credential even when .env and the
                # parent process contain different values.
                env["OPENCLAW_GATEWAY_TOKEN"] = resolved_gateway_token
            if subscription_transport:
                env.pop("OPENAI_API_KEY", None)
                env.pop("CODEX_HOME", None)
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

            # The listener must match the probe/client/ownership receipt even
            # when config or an inherited environment names a different port.
            # Use the public CLI override, and never expose the desktop Gateway
            # beyond loopback through an ambient bind setting.
            cmd = [
                node,
                str(script),
                "gateway",
                "run",
                "--port",
                str(self._port),
                "--bind",
                "loopback",
                "--verbose",
            ]
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
            self._reused_gateway = False
            self._reused_pid = None
            (lock_dir / "pid").write_text(str(self._process.pid), encoding="utf-8")
            self._write_gateway_ownership_receipt(lock_dir, self._process.pid)
            logger.info("Gateway started (pid=%d)", self._process.pid)
        except Exception:
            if self._process is not None:
                self.stop()
            else:
                self._release_launch_lock()
                if self._gateway_log is not None:
                    self._gateway_log.close()
                    self._gateway_log = None
            raise

    async def wait_ready(self, timeout_sec: float | None = None) -> bool:
        """Wait until the public Gateway ``connect`` handshake succeeds."""
        timeout_sec = (
            self._ready_timeout_sec if timeout_sec is None else float(timeout_sec)
        )
        deadline = asyncio.get_event_loop().time() + timeout_sec
        while asyncio.get_event_loop().time() < deadline:
            # Check subprocess hasn't crashed
            if self._process is not None and self._process.poll() is not None:
                logger.error(
                    "Gateway process exited with code %d", self._process.returncode
                )
                return False
            ready = await asyncio.to_thread(self._probe_existing_gateway)
            if ready:
                if self._process is not None and self._process.poll() is not None:
                    logger.error(
                        "Gateway died (code=%d) but port %d belongs to another Gateway",
                        self._process.returncode,
                        self._port,
                    )
                    return False
                if (
                    self._process is not None
                    and not self._bind_gateway_listener_ownership()
                ):
                    logger.error(
                        "Gateway authenticated but listener ownership could not be recorded"
                    )
                    return False
                logger.info("Gateway is ready on port %d", self._port)
                return True
            await asyncio.sleep(0.5)
        logger.error("Gateway did not become ready within %.0fs", timeout_sec)
        return False

    def stop(self) -> None:
        """Stop the Gateway subprocess."""
        if self._process is None:
            if self._reused_gateway:
                logger.info(
                    "Detaching from reused Gateway without terminating it (pid=%s)",
                    self._reused_pid,
                )
            self._reused_gateway = False
            self._reused_pid = None
            return
        if self._process.poll() is not None:
            logger.info("Gateway already stopped (code=%d)", self._process.returncode)
            self._process = None
            self._release_launch_lock()
            if self._gateway_log is not None:
                self._gateway_log.close()
                self._gateway_log = None
            return
        process = self._process
        logger.info("Stopping owned Gateway (pid=%d)...", process.pid)
        try:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Gateway did not stop gracefully, killing owned process")
                process.kill()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    logger.error(
                        "Owned Gateway did not report exit after kill; detaching",
                        pid=process.pid,
                    )
        finally:
            self._process = None
            self._reused_gateway = False
            self._reused_pid = None
            if self._gateway_log is not None:
                self._gateway_log.close()
                self._gateway_log = None
            self._release_launch_lock()
        logger.info("Gateway stopped")

    async def ensure_running(self) -> bool:
        """Check if the Gateway is alive; if not, restart it.

        Returns True if the Gateway is up and ready after this call.
        """
        if self._process is not None and self._process.poll() is None:
            return True
        if self._reused_gateway:
            if (
                self._verified_gateway_owner_pid() == self._reused_pid
                and await self.wait_ready(timeout_sec=min(5.0, self._ready_timeout_sec))
            ):
                return True
            logger.warning(
                "Previously reused Gateway is no longer healthy or ownership changed"
            )
            self._reused_gateway = False
            self._reused_pid = None

        exit_code = self._process.returncode if self._process else None
        logger.warning(
            "Gateway process is dead (exit_code=%s), restarting...",
            exit_code,
        )
        self._process = None

        try:
            self.start()
            return await self.wait_ready()
        except Exception:
            logger.exception("Gateway restart failed")
            return False
