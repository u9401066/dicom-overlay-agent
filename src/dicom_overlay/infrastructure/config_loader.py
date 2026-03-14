"""Configuration loader — reads config.yaml into AppConfig."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from dicom_overlay.domain.entities import (
    AppConfig,
    HotkeyConfig,
    MonitorConfig,
    OpenClawConfig,
    OverlayConfig,
    ROICrop,
)

logger = structlog.get_logger(__name__)

_DEFAULT_CONFIG_PATHS = [
    Path("config.yaml"),
    Path("config.yml"),
    Path.home() / ".dicom-overlay" / "config.yaml",
]


def load_config(path: Path | None = None) -> AppConfig:
    """Load configuration from YAML file.

    Tries the given path first, then falls back to default locations.
    Returns default AppConfig if no file is found.
    """
    config_path = _resolve_path(path)
    if config_path is None:
        logger.warning("No config file found, using defaults")
        return AppConfig()

    logger.info("Loading config from %s", config_path)
    with config_path.open(encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    return _parse_config(raw)


def _resolve_path(path: Path | None) -> Path | None:
    if path and path.exists():
        return path
    for p in _DEFAULT_CONFIG_PATHS:
        if p.exists():
            return p
    return None


def _parse_config(raw: dict[str, Any]) -> AppConfig:
    monitor_raw = raw.get("monitor", {})
    roi_raw = raw.get("phi_roi", {})
    oc_raw = raw.get("openclaw", {})
    overlay_raw = raw.get("overlay", {})
    hotkey_raw = raw.get("hotkeys", {})
    debug_raw = raw.get("debug", {})

    return AppConfig(
        monitor=MonitorConfig(
            window_title_keywords=monitor_raw.get(
                "window_title_keywords", ["DICOM", "影像", "Viewer"]
            ),
            polling_interval_ms=monitor_raw.get("polling_interval_ms", 500),
            hash_algorithm=monitor_raw.get("hash_algorithm", "ahash"),
            hash_threshold=monitor_raw.get("hash_threshold", 10),
            debounce_stable_sec=monitor_raw.get("debounce_stable_sec", 1.5),
        ),
        phi_roi=ROICrop(
            top=roi_raw.get("top", 60),
            bottom=roi_raw.get("bottom", 30),
            left=roi_raw.get("left", 0),
            right=roi_raw.get("right", 0),
        ),
        openclaw=OpenClawConfig(
            gateway_url=oc_raw.get("gateway_url", "ws://127.0.0.1:18789"),
            reconnect_interval_sec=oc_raw.get("reconnect_interval_sec", 5),
            timeout_sec=oc_raw.get("timeout_sec", 15),
        ),
        overlay=OverlayConfig(
            position=overlay_raw.get("position", "right"),
            summary_panel=overlay_raw.get("summary_panel", True),
            region_highlights=overlay_raw.get("region_highlights", True),
            display_duration_sec=overlay_raw.get("display_duration_sec", 30),
            critical_persist=overlay_raw.get("critical_persist", True),
            fade_duration_ms=overlay_raw.get("fade_duration_ms", 500),
            control_bar=overlay_raw.get("control_bar", True),
            control_bar_position=overlay_raw.get(
                "control_bar_position", "bottom_right"
            ),
            tts_enabled=overlay_raw.get("tts_enabled", True),
        ),
        hotkeys=HotkeyConfig(
            trigger_manual=hotkey_raw.get("trigger_manual", "ctrl+shift+a"),
            dismiss_overlay=hotkey_raw.get("dismiss_overlay", "ctrl+shift+d"),
            toggle_enable=hotkey_raw.get("toggle_enable", "ctrl+shift+e"),
        ),
        region_maps=raw.get("region_maps", {}),
        debug_save_screenshots=debug_raw.get("save_screenshots", False),
        log_level=debug_raw.get("log_level", "INFO"),
        log_file=debug_raw.get("log_file", "overlay_agent.log"),
    )


def save_roi_config(path: Path, roi: ROICrop) -> None:
    """Update only the phi_roi section in config.yaml."""
    if path.exists():
        with path.open(encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
    else:
        raw = {}

    raw["phi_roi"] = {
        "top": roi.top,
        "bottom": roi.bottom,
        "left": roi.left,
        "right": roi.right,
    }

    with path.open("w", encoding="utf-8") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True)

    logger.info("ROI config saved to %s", path)
