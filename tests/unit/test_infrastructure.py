"""Unit tests for infrastructure — config loader and region mapper."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from PIL import Image

from dicom_overlay.domain.entities import Modality, ROICrop, TriggerMode, WindowRect
from dicom_overlay.infrastructure.app_paths import resolve_app_base_dir
from dicom_overlay.infrastructure.config_loader import load_config, save_roi_config
from dicom_overlay.infrastructure.desktop_settings_store import DesktopSettingsStore
from dicom_overlay.infrastructure.env_file import read_env_file
from dicom_overlay.infrastructure.gateway_manager import GatewayManager
from dicom_overlay.infrastructure.openclaw_runtime import (
    MIN_SAFE_OPENCLAW_VERSION,
    OpenClawRuntimeError,
    build_harness_manifest,
    build_openclaw_chat_frame,
    ensure_openclaw_runtime_supported,
    is_openclaw_version_supported,
    read_installed_openclaw_version,
)
from dicom_overlay.infrastructure.openclaw_settings import (
    ProviderProfile,
    ProviderType,
    build_openclaw_config,
    default_provider_profiles,
)
from dicom_overlay.infrastructure.region_mapper import RegionMapper
from dicom_overlay.infrastructure.screen_monitor import ScreenMonitor
from dicom_overlay.infrastructure.vision_probe import VisionSmokeTester
from tests.unit.test_agent import MockVisionAnalyzer


class TestConfigLoader:
    def test_load_defaults_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "dicom_overlay.infrastructure.config_loader._DEFAULT_CONFIG_PATHS", []
        )
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.monitor.polling_interval_ms == 500
        assert config.phi_roi.top == 0
        assert config.phi_roi.configured is False
        assert config.analysis.trigger_mode == TriggerMode.HYBRID

    def test_load_from_file(self, tmp_path):
        config_data = {
            "monitor": {"polling_interval_ms": 250, "hash_threshold": 15},
            "phi_roi": {"top": 100, "bottom": 50, "left": 10, "right": 10},
            "openclaw": {"gateway_url": "ws://localhost:9999"},
            "analysis": {"trigger_mode": "manual"},
        }
        config_file = tmp_path / "config.yaml"
        with config_file.open("w") as f:
            yaml.dump(config_data, f)

        config = load_config(config_file)
        assert config.monitor.polling_interval_ms == 250
        assert config.monitor.hash_threshold == 15
        assert config.phi_roi.top == 100
        assert config.phi_roi.configured is False
        assert config.openclaw.gateway_url == "ws://localhost:9999"
        assert config.openclaw.gateway_start_timeout_sec == 180
        assert config.analysis.trigger_mode == TriggerMode.MANUAL

    def test_save_roi_config(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        initial = {"monitor": {"polling_interval_ms": 500}}
        with config_file.open("w") as f:
            yaml.dump(initial, f)

        roi = ROICrop(
            top=80,
            bottom=40,
            left=5,
            right=5,
            configured=True,
            reference_width=1920,
            reference_height=1080,
        )
        save_roi_config(config_file, roi)

        with config_file.open() as f:
            raw = yaml.safe_load(f)
        assert raw["phi_roi"]["top"] == 80
        assert raw["phi_roi"]["bottom"] == 40
        assert raw["phi_roi"]["configured"] is True
        assert raw["phi_roi"]["coordinate_space"] == "viewer"
        assert raw["phi_roi"]["reference_width"] == 1920
        assert raw["phi_roi"]["reference_height"] == 1080
        # Original data preserved
        assert raw["monitor"]["polling_interval_ms"] == 500

    def test_explicit_viewer_roi_loads_as_configured(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.safe_dump(
                {
                    "phi_roi": {
                        "configured": True,
                        "coordinate_space": "viewer",
                        "reference_width": 1200,
                        "reference_height": 800,
                        "top": 40,
                        "bottom": 20,
                        "left": 10,
                        "right": 10,
                    }
                }
            ),
            encoding="utf-8",
        )

        config = load_config(config_file)

        assert config.phi_roi.configured is True
        assert config.phi_roi.reference_width == 1200
        assert config.phi_roi.reference_height == 800


class TestOpenClawSettings:
    def test_default_provider_profiles_include_requested_desktop_options(self):
        profiles = default_provider_profiles()
        keys = {p.key for p in profiles}
        assert "openai-codex" in keys
        assert "openrouter" in keys
        assert "github-copilot-byok" in keys
        openrouter = next(p for p in profiles if p.key == "openrouter")
        assert openrouter.model == "minimax/minimax-m3"
        assert openrouter.model_ref == "openrouter/minimax/minimax-m3"

    def test_openai_codex_profile_uses_openai_provider_and_vision_model(self):
        profile = next(
            p for p in default_provider_profiles() if p.key == "openai-codex"
        )
        assert profile.provider_id == "openai"
        assert profile.provider_type == ProviderType.OPENAI
        assert profile.model
        assert profile.requires_vision_check

    def test_build_openclaw_config_uses_secret_refs_and_model_allowlist(self):
        profile = ProviderProfile(
            key="openrouter",
            label="OpenRouter",
            provider_id="openrouter",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            model="minimax/minimax-m3",
            api_key_env="OPENROUTER_API_KEY",
            base_url="https://openrouter.ai/api/v1",
        )

        config = build_openclaw_config(profile)

        provider = config["models"]["providers"]["openrouter"]
        assert provider["apiKey"] == {
            "source": "env",
            "provider": "default",
            "id": "OPENROUTER_API_KEY",
        }
        assert provider["baseUrl"] == "https://openrouter.ai/api/v1"
        # OpenClaw 2026.5.x blocks startup unless gateway.mode is set.
        assert config["gateway"]["mode"] == "local"
        assert config["agents"]["defaults"]["model"]["primary"] == (
            "openrouter/minimax/minimax-m3"
        )
        assert (
            "openrouter/minimax/minimax-m3" in (config["agents"]["defaults"]["models"])
        )
        assert config["agents"]["defaults"]["imageMaxDimensionPx"] == 1568
        assert provider["timeoutSeconds"] == 165
        assert config["agents"]["defaults"]["timeoutSeconds"] == 175

    def test_default_vision_profile_declares_gpt54_mini_image_capabilities(self):
        profile = next(
            item for item in default_provider_profiles() if item.key == "openai-vision"
        )

        config = build_openclaw_config(profile)
        provider = config["models"]["providers"]["openai"]
        model = provider["models"][0]

        assert provider["api"] == "openai-responses"
        assert model["id"] == "gpt-5.4-mini"
        assert model["input"] == ["text", "image"]
        assert model["contextWindow"] == 400_000
        assert model["maxTokens"] == 128_000
        assert model["agentRuntime"] == {"id": "openclaw"}
        assert config["tools"] == {
            "allow": ["dicom_bbox_validate"],
            "web": {
                "search": {"enabled": False},
                "fetch": {"enabled": False},
            },
        }

    def test_luna_profile_remains_available_as_an_explicit_option(self):
        profile = next(
            item for item in default_provider_profiles() if item.key == "openai-luna"
        )

        assert profile.model_ref == "openai/gpt-5.6-luna"
        assert profile.input_modalities == ("text", "image")
        assert profile.context_window == 1_050_000


class TestOpenClawRuntimeCompatibility:
    def test_gateway_ready_timeout_is_bounded(self, tmp_path):
        manager = GatewayManager(repo_root=tmp_path, ready_timeout_sec=120)

        assert manager._ready_timeout_sec == 120.0

        with pytest.raises(ValueError, match="between 5 and 600"):
            GatewayManager(repo_root=tmp_path, ready_timeout_sec=1)

    def test_safe_version_floor_matches_claw_chain_patch_boundary(self):
        assert MIN_SAFE_OPENCLAW_VERSION == "2026.4.22"
        assert not is_openclaw_version_supported("2026.4.21")
        assert is_openclaw_version_supported("2026.4.22")
        assert is_openclaw_version_supported("2026.5.27")
        assert is_openclaw_version_supported("2026.5.24-beta.2")

    def test_reads_installed_openclaw_version_from_node_package(self, tmp_path):
        package = tmp_path / "openclaw" / "node_modules" / "openclaw"
        package.mkdir(parents=True)
        (package / "package.json").write_text(
            '{"version": "2026.5.27"}',
            encoding="utf-8",
        )

        assert read_installed_openclaw_version(tmp_path) == "2026.5.27"

    def test_unsupported_openclaw_runtime_raises_actionable_error(self, tmp_path):
        package = tmp_path / "openclaw" / "node_modules" / "openclaw"
        package.mkdir(parents=True)
        (package / "package.json").write_text(
            '{"version": "2026.4.1"}',
            encoding="utf-8",
        )

        with pytest.raises(OpenClawRuntimeError, match=r"2026\.4\.22"):
            ensure_openclaw_runtime_supported(tmp_path)

    def test_builds_plugin_like_harness_manifest_without_private_sdk_paths(self):
        manifest = build_harness_manifest()

        assert manifest["name"] == "dicom-overlay-agent-harness"
        assert manifest["compatibility"]["minimumOpenClaw"] == "2026.4.22"
        assert manifest["compatibility"]["gatewayProtocol"]["methods"] == [
            "connect",
            "chat.send",
        ]
        assert manifest["capabilities"]["bboxCropReanalysis"] is True
        assert manifest["capabilities"]["coordinateDriftCalibration"] is True
        assert manifest["capabilities"]["imageTurnBoundBboxReceipts"] is True
        assert manifest["capabilities"]["ecgFounderWaveformAssist"] is True
        assert manifest["capabilities"]["noScreenshotToWaveformInference"] is True
        assert (
            "ecg_founder_analyze_waveform" in manifest["capabilities"]["openClawTools"]
        )
        assert manifest["capabilities"]["gatewayOnlyDesktopBoundary"] is True
        assert "plugin-sdk" not in yaml.safe_dump(manifest)

    def test_builds_gateway_chat_frame_with_stable_image_attachment_schema(self):
        frame = build_openclaw_chat_frame(
            request_id="chat-1",
            session_key="main",
            message="Analyze this.",
            idempotency_key="idem-1",
            image_base64="ZmFrZQ==",
        )

        assert frame["method"] == "chat.send"
        assert frame["params"]["sessionKey"] == "main"
        assert frame["params"]["message"] == "Analyze this."
        assert frame["params"]["attachments"] == [
            {
                "type": "image",
                "mimeType": "image/png",
                "content": "ZmFrZQ==",
            }
        ]

    def test_gateway_manager_reads_bundled_openclaw_runtime_when_frozen(
        self, monkeypatch, tmp_path
    ):
        bundled = tmp_path / "_internal"
        package = bundled / "openclaw" / "node_modules" / "openclaw"
        package.mkdir(parents=True)
        (package / "package.json").write_text(
            '{"version": "2026.5.27"}',
            encoding="utf-8",
        )
        script = package / "openclaw.mjs"
        script.write_text("console.log('gateway')", encoding="utf-8")
        monkeypatch.setattr("sys.frozen", True, raising=False)
        monkeypatch.setattr("sys._MEIPASS", str(bundled), raising=False)

        manager = GatewayManager(repo_root=tmp_path / "app")

        assert manager._gateway_script() == script

    def test_find_node_prefers_bundled_runtime_over_path(self, monkeypatch, tmp_path):
        bundled = tmp_path / "_internal"
        node_dir = bundled / "node"
        node_dir.mkdir(parents=True)
        exe_name = "node.exe" if sys.platform == "win32" else "node"
        node_exe = node_dir / exe_name
        node_exe.write_text("", encoding="utf-8")
        monkeypatch.setattr("sys.frozen", True, raising=False)
        monkeypatch.setattr("sys._MEIPASS", str(bundled), raising=False)
        monkeypatch.setattr(
            "dicom_overlay.infrastructure.gateway_manager.shutil.which",
            lambda _name: "C:/system/node.exe",
        )

        manager = GatewayManager(repo_root=tmp_path / "app")

        assert manager._find_node() == str(node_exe)

    def test_find_node_falls_back_to_system_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr("sys.frozen", False, raising=False)
        monkeypatch.setattr(
            "dicom_overlay.infrastructure.gateway_manager.shutil.which",
            lambda _name: "/usr/bin/node",
        )

        manager = GatewayManager(repo_root=tmp_path / "app")

        assert manager._find_node() == "/usr/bin/node"

    def test_find_node_raises_actionable_error_when_missing(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr("sys.frozen", False, raising=False)
        monkeypatch.setattr(
            "dicom_overlay.infrastructure.gateway_manager.shutil.which",
            lambda _name: None,
        )

        manager = GatewayManager(repo_root=tmp_path / "app")

        with pytest.raises(FileNotFoundError, match="fetch-node"):
            manager._find_node()

    def test_gateway_manager_takes_repo_local_launch_lock(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS", "1")

        class FakeProcess:
            pid = 1234
            returncode = None

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = 0

            def wait(self, timeout=None):
                return 0

            def kill(self):
                self.returncode = -9

        monkeypatch.setattr(GatewayManager, "_kill_port_occupant", lambda self: None)
        monkeypatch.setattr(GatewayManager, "_find_node", lambda self: "node")
        monkeypatch.setattr(
            GatewayManager,
            "_gateway_script",
            lambda self: tmp_path / "openclaw.mjs",
        )
        monkeypatch.setattr(GatewayManager, "_sync_skills", lambda self: None)
        monkeypatch.setattr(
            "dicom_overlay.infrastructure.gateway_manager.subprocess.Popen",
            lambda *args, **kwargs: FakeProcess(),
        )
        manager = GatewayManager(repo_root=tmp_path)

        manager.start()

        lock_dir = tmp_path / "data" / "tmp" / "openclaw-gateway.lock"
        assert lock_dir.exists()
        assert (lock_dir / "pid").read_text(encoding="utf-8") == "1234"

        manager.stop()

        assert not lock_dir.exists()

    def test_gateway_manager_refuses_second_live_launch_lock(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("DICOM_OVERLAY_ALLOW_REAL_OPENCLAW_IN_TESTS", "1")
        lock_dir = tmp_path / "data" / "tmp" / "openclaw-gateway.lock"
        lock_dir.mkdir(parents=True)
        (lock_dir / "pid").write_text("999", encoding="utf-8")
        monkeypatch.setattr(
            GatewayManager,
            "_pid_is_running",
            lambda self, pid: True,
            raising=False,
        )
        monkeypatch.setattr(GatewayManager, "_kill_port_occupant", lambda self: None)
        monkeypatch.setattr(GatewayManager, "_find_node", lambda self: "node")
        monkeypatch.setattr(
            GatewayManager,
            "_gateway_script",
            lambda self: tmp_path / "openclaw.mjs",
        )
        monkeypatch.setattr(GatewayManager, "_sync_skills", lambda self: None)

        def _unexpected_popen(*args, **kwargs):
            raise AssertionError("must not spawn a second OpenClaw Gateway")

        monkeypatch.setattr(
            "dicom_overlay.infrastructure.gateway_manager.subprocess.Popen",
            _unexpected_popen,
        )
        manager = GatewayManager(repo_root=tmp_path)

        with pytest.raises(RuntimeError, match="OpenClaw Gateway launch lock"):
            manager.start()

    def test_gateway_pid_check_rejects_a_reaped_child_process(self, tmp_path):
        manager = GatewayManager(repo_root=tmp_path)
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait(timeout=5)

        assert manager._pid_is_running(os.getpid()) is True
        assert manager._pid_is_running(child.pid) is False

    def test_gateway_manager_refuses_real_start_in_oom_safe_tests(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("DICOM_OVERLAY_TEST_DISABLE_REAL_OPENCLAW", "1")

        def _unexpected_popen(*args, **kwargs):
            raise AssertionError("must not spawn OpenClaw during guarded tests")

        monkeypatch.setattr(
            "dicom_overlay.infrastructure.gateway_manager.subprocess.Popen",
            _unexpected_popen,
        )
        manager = GatewayManager(repo_root=tmp_path)

        with pytest.raises(RuntimeError, match="disabled during OOM-safe tests"):
            manager.start()

        assert not (tmp_path / "data" / "tmp" / "openclaw-gateway.lock").exists()

    def test_gateway_runtime_selfcheck_leaves_no_state_directory(self, tmp_path):
        manager = GatewayManager(repo_root=tmp_path)

        rows = manager.verify_runtime()

        assert ("writable_base", True, str(tmp_path)) in rows
        assert not (tmp_path / "openclaw-home").exists()
        assert not list(tmp_path.glob(".dicom-overlay-selfcheck-*"))

    def test_gateway_manager_seeds_vision_model_and_native_plugin(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)
        monkeypatch.delenv("DICOM_ECGFOUNDER_ENDPOINT", raising=False)
        monkeypatch.delenv("DICOM_ECGFOUNDER_TOKEN", raising=False)
        manager = GatewayManager(repo_root=tmp_path)

        path = manager._ensure_openclaw_config()

        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["gateway"]["mode"] == "local"
        assert "auth" not in payload["gateway"]
        assert payload["agents"]["defaults"]["model"]["primary"] == (
            "openai/gpt-5.4-mini"
        )
        assert payload["models"]["providers"]["openai"]["apiKey"]["id"] == (
            "OPENAI_API_KEY"
        )
        assert payload["models"]["providers"]["openai"]["timeoutSeconds"] == 165
        assert payload["agents"]["defaults"]["timeoutSeconds"] == 175
        plugin_path = str(
            (
                tmp_path / "openclaw-home/.openclaw/workspace/plugins/"
                "dicom-overlay-agent-harness"
            ).resolve()
        )
        assert plugin_path in payload["plugins"]["load"]["paths"]
        assert payload["plugins"]["entries"]["dicom-overlay-agent-harness"] == {
            "enabled": True
        }
        assert payload["plugins"]["allow"] == ["dicom-overlay-agent-harness"]
        assert payload["tools"] == {
            "allow": ["dicom_bbox_validate"],
            "web": {
                "search": {"enabled": False},
                "fetch": {"enabled": False},
            },
        }

    def test_gateway_manager_enables_ecg_founder_only_with_endpoint_and_token(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv(
            "DICOM_ECGFOUNDER_ENDPOINT",
            "http://127.0.0.1:18790/v1/analyze",
        )
        monkeypatch.delenv("DICOM_ECGFOUNDER_TOKEN", raising=False)
        manager = GatewayManager(repo_root=tmp_path)

        path = manager._ensure_openclaw_config()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["tools"] == {
            "allow": ["dicom_bbox_validate"],
            "web": {
                "search": {"enabled": False},
                "fetch": {"enabled": False},
            },
        }

        monkeypatch.setenv("DICOM_ECGFOUNDER_TOKEN", "test-only-token")
        path = manager._ensure_openclaw_config()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["tools"] == {
            "allow": [
                "dicom_bbox_validate",
                "ecg_founder_analyze_waveform",
            ],
            "web": {
                "search": {"enabled": False},
                "fetch": {"enabled": False},
            },
        }

    def test_pyinstaller_spec_uses_staged_openclaw_runtime(self):
        spec = Path("dicom-overlay-agent.spec").read_text(encoding="utf-8")

        assert "build/openclaw-runtime/openclaw" in spec
        assert 'optional_tree("clinical_rules", "clinical_rules")' in spec
        assert "collect_data_files(" in spec
        assert '"medical_image_harness"' in spec
        assert '"skills/**/*"' in spec
        assert '"schemas/**/*"' in spec
        assert 'optional_tree("openclaw/node_modules/openclaw"' not in spec

    def test_pyinstaller_spec_bundles_portable_node_and_prunes_qt(self):
        spec = Path("dicom-overlay-agent.spec").read_text(encoding="utf-8")

        # Core 4: portable node is bundled when present (zero-install path).
        assert 'optional_file("node/node.exe", "node")' in spec
        # Core 4: heavy unused Qt modules are excluded to keep the bundle lean.
        assert "PyQt6.QtWebEngineCore" in spec
        assert "opengl32sw.dll" in spec


class TestAppBaseDir:
    def test_frozen_uses_executable_dir_not_cwd(self, tmp_path):
        exe = tmp_path / "bundle" / "DICOMOverlayAgent.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("", encoding="utf-8")
        other_cwd = tmp_path / "somewhere" / "else"
        other_cwd.mkdir(parents=True)

        base = resolve_app_base_dir(frozen=True, executable=str(exe), cwd=other_cwd)

        # Portable USB rule: anchored to the exe folder, NOT the launch cwd.
        assert base == exe.parent.resolve()
        assert base != other_cwd

    def test_not_frozen_uses_cwd(self, tmp_path):
        base = resolve_app_base_dir(
            frozen=False, executable="/usr/bin/python", cwd=tmp_path
        )

        assert base == tmp_path


class TestDesktopSettingsStore:
    def test_creates_and_reuses_local_gateway_token(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)
        store = DesktopSettingsStore(repo_root=tmp_path)

        first = store.ensure_gateway_token()
        second = store.ensure_gateway_token()

        assert first == second
        assert len(first) >= 32
        assert (tmp_path / ".env").read_text(encoding="utf-8").count(
            "OPENCLAW_GATEWAY_TOKEN="
        ) == 1

    def test_load_model_ref_reads_active_primary_without_credentials(self, tmp_path):
        config_path = tmp_path / "openclaw" / "openclaw.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(
            json.dumps(
                {
                    "agents": {
                        "defaults": {"model": {"primary": "openai/gpt-5.4-mini"}}
                    },
                    "models": {"providers": {"openai": {"apiKey": "secret"}}},
                }
            ),
            encoding="utf-8",
        )

        store = DesktopSettingsStore(repo_root=tmp_path)

        assert store.load_model_ref() == "openai/gpt-5.4-mini"

    def test_ecg_founder_configuration_requires_endpoint_and_token(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.delenv("DICOM_ECGFOUNDER_ENDPOINT", raising=False)
        monkeypatch.delenv("DICOM_ECGFOUNDER_TOKEN", raising=False)
        store = DesktopSettingsStore(repo_root=tmp_path)

        assert store.ecg_founder_configured() is False
        (tmp_path / ".env").write_text(
            "DICOM_ECGFOUNDER_ENDPOINT=http://127.0.0.1:18790/v1/analyze\n"
            "DICOM_ECGFOUNDER_TOKEN=test-only-token\n",
            encoding="utf-8",
        )
        assert store.ecg_founder_configured() is True

    def test_save_provider_profile_writes_env_and_openclaw_config(self, tmp_path):
        profile = ProviderProfile(
            key="openrouter",
            label="OpenRouter",
            provider_id="openrouter",
            provider_type=ProviderType.OPENROUTER,
            model="minimax/minimax-m3",
            api_key_env="OPENROUTER_API_KEY",
            base_url="https://openrouter.ai/api/v1",
        )
        store = DesktopSettingsStore(repo_root=tmp_path)

        store.save_provider_profile(profile, api_key="sk-test", gateway_token="gw-test")

        env_text = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "OPENROUTER_API_KEY=sk-test" in env_text
        assert "OPENCLAW_GATEWAY_TOKEN=gw-test" in env_text

        config = yaml.safe_load(
            (tmp_path / "openclaw" / "openclaw.json").read_text(encoding="utf-8")
        )
        assert (
            config["models"]["providers"]["openrouter"]["apiKey"]["id"]
            == "OPENROUTER_API_KEY"
        )
        assert config["agents"]["defaults"]["model"]["primary"] == (
            "openrouter/minimax/minimax-m3"
        )

    def test_save_provider_profile_preserves_unmanaged_openclaw_sections(
        self, tmp_path
    ):
        config_path = tmp_path / "openclaw" / "openclaw.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(
            yaml.safe_dump({"channels": {"telegram": {"enabled": True}}}),
            encoding="utf-8",
        )
        profile = ProviderProfile(
            key="openai-codex",
            label="OpenAI Codex",
            provider_id="openai",
            provider_type=ProviderType.OPENAI,
            model="gpt-5.2-codex",
            api_key_env="OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",
        )
        store = DesktopSettingsStore(repo_root=tmp_path)

        store.save_provider_profile(profile, api_key="sk-openai", gateway_token="")

        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert config["channels"]["telegram"]["enabled"] is True
        assert config["models"]["providers"]["openai"]["apiKey"]["id"] == (
            "OPENAI_API_KEY"
        )

    def test_save_trigger_mode_updates_config_yaml_without_dropping_roi(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.safe_dump({"phi_roi": {"top": 12, "bottom": 34}}),
            encoding="utf-8",
        )
        store = DesktopSettingsStore(repo_root=tmp_path, config_path=config_path)

        store.save_trigger_mode(TriggerMode.AUTO)

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert raw["analysis"]["trigger_mode"] == "auto"
        assert raw["phi_roi"]["top"] == 12
        assert raw["phi_roi"]["bottom"] == 34

    def test_save_analysis_settings_preserves_other_analysis_values(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(
                {
                    "analysis": {"trigger_mode": "hybrid"},
                    "phi_roi": {"top": 12},
                }
            ),
            encoding="utf-8",
        )
        store = DesktopSettingsStore(repo_root=tmp_path, config_path=config_path)

        store.save_analysis_settings(
            multi_pass_enabled=True,
            max_zoom_targets=2,
        )

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert raw["analysis"] == {
            "trigger_mode": "hybrid",
            "multi_pass_enabled": True,
            "multi_pass_max_zoom_targets": 2,
        }
        assert raw["phi_roi"]["top"] == 12

    def test_read_env_file_ignores_comments_and_preserves_values(self, tmp_path):
        env_path = tmp_path / ".env"
        env_path.write_text(
            "# comment\nOPENAI_API_KEY=sk-test\nEMPTY=\nNAME=value=with=equals\n",
            encoding="utf-8",
        )

        values = read_env_file(env_path)

        assert values == {
            "OPENAI_API_KEY": "sk-test",
            "EMPTY": "",
            "NAME": "value=with=equals",
        }


class TestScreenMonitorHashing:
    @staticmethod
    def _pattern_png(invert: bool = False) -> bytes:
        image = Image.new("RGB", (16, 16), "black")
        for x in range(16):
            for y in range(16):
                left_half = x < 8
                white = left_half if not invert else not left_half
                if white:
                    image.putpixel((x, y), (255, 255, 255))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_average_hash_is_lightweight_and_stable(self):
        monitor = ScreenMonitor("ahash")
        image = self._pattern_png()

        first = monitor.compute_hash(image)
        second = monitor.compute_hash(image)

        assert first == second
        assert len(first) == 16
        assert not monitor.has_changed(first, second, threshold=0)

    def test_hash_change_detection_uses_hamming_distance(self):
        monitor = ScreenMonitor("ahash")
        first = monitor.compute_hash(self._pattern_png())
        second = monitor.compute_hash(self._pattern_png(invert=True))

        assert monitor.has_changed(first, second, threshold=0)

    def test_legacy_phash_setting_falls_back_to_lightweight_hash(self):
        monitor = ScreenMonitor("phash")

        assert len(monitor.compute_hash(self._pattern_png())) == 16

    def test_invalid_hash_is_treated_as_changed(self):
        monitor = ScreenMonitor("ahash")

        assert monitor.has_changed("not-hex", "0", threshold=64)

    def test_display_for_window_returns_physical_monitor_frame(self, monkeypatch):
        from dicom_overlay.infrastructure import screen_monitor

        class FakeWin32Api:
            @staticmethod
            def MonitorFromRect(rect, default):
                assert rect == (-1800, 100, -200, 900)
                assert default == 2
                return "secondary"

            @staticmethod
            def GetMonitorInfo(handle):
                assert handle == "secondary"
                return {
                    "Monitor": (-1920, 0, 0, 1080),
                    "Device": r"\\.\DISPLAY2",
                    "Flags": 0,
                }

            @staticmethod
            def EnumDisplayMonitors(_hdc, _clip):
                return [("primary", None, None), ("secondary", None, None)]

        class FakeWin32Con:
            MONITOR_DEFAULTTONEAREST = 2
            MONITORINFOF_PRIMARY = 1

        monkeypatch.setattr(screen_monitor, "HAS_WIN32", True)
        monkeypatch.setattr(screen_monitor, "win32api", FakeWin32Api)
        monkeypatch.setattr(screen_monitor, "win32con", FakeWin32Con)

        frame = ScreenMonitor().display_for_window(
            WindowRect(left=-1800, top=100, width=1600, height=800)
        )

        assert frame is not None
        assert frame.physical_rect == WindowRect(-1920, 0, 1920, 1080)
        assert frame.monitor_index == 1
        assert frame.device_name == r"\\.\DISPLAY2"
        assert frame.is_primary is False


class TestVisionSmokeTester:
    @pytest.mark.asyncio
    async def test_probe_calls_analyzer_with_tiny_png(self):
        analyzer = MockVisionAnalyzer()
        tester = VisionSmokeTester(analyzer)

        result = await tester.probe()

        assert result.ok
        assert result.supports_image
        assert analyzer.analyze_calls == 1

    @pytest.mark.asyncio
    async def test_probe_reports_image_input_failure(self):
        class FailingAnalyzer(MockVisionAnalyzer):
            async def analyze(self, image_base64, modality, valid_regions):
                raise RuntimeError("image input unsupported")

        tester = VisionSmokeTester(FailingAnalyzer())

        result = await tester.probe()

        assert not result.ok
        assert not result.supports_image
        assert "image input unsupported" in result.message


class TestRegionMapper:
    @pytest.fixture()
    def mapper(self) -> RegionMapper:
        region_maps = {
            "EKG": {
                "layout": "standard_4x3",
                "regions": {
                    "lead_I": {"x": 0.0, "y": 0.0, "w": 0.25, "h": 0.27},
                    "lead_V4": {"x": 0.75, "y": 0.0, "w": 0.25, "h": 0.27},
                    "rhythm_strip": {"x": 0.0, "y": 0.81, "w": 1.0, "h": 0.19},
                },
            },
            "CXR": {
                "layout": "standard_pa",
                "regions": {
                    "right_upper_lung": {"x": 0.05, "y": 0.08, "w": 0.30, "h": 0.22},
                },
            },
        }
        return RegionMapper(region_maps)

    def test_get_valid_regions(self, mapper: RegionMapper):
        regions = mapper.get_valid_regions(Modality.EKG)
        assert "lead_I" in regions
        assert "lead_V4" in regions
        assert "rhythm_strip" in regions
        assert len(regions) == 3

    def test_get_region_rect(self, mapper: RegionMapper):
        rect = mapper.get_region_rect("lead_I", Modality.EKG)
        assert rect is not None
        assert rect.x == 0.0
        assert rect.w == 0.25

    def test_get_region_rect_unknown(self, mapper: RegionMapper):
        rect = mapper.get_region_rect("unknown_region", Modality.EKG)
        assert rect is None

    def test_get_region_rect_wrong_modality(self, mapper: RegionMapper):
        rect = mapper.get_region_rect("lead_I", Modality.CXR)
        assert rect is None

    def test_to_screen_rect(self, mapper: RegionMapper):
        from dicom_overlay.domain.entities import RegionRect

        region = RegionRect(x=0.0, y=0.0, w=0.25, h=0.27)
        window = WindowRect(left=100, top=200, width=1000, height=800)
        sx, sy, sw, sh = mapper.to_screen_rect(region, window)

        assert sx == 100  # left + 0.0 * 1000
        assert sy == 200  # top + 0.0 * 800
        assert sw == 250  # 0.25 * 1000
        assert sh == 216  # 0.27 * 800

    def test_cxr_regions(self, mapper: RegionMapper):
        regions = mapper.get_valid_regions(Modality.CXR)
        assert "right_upper_lung" in regions
