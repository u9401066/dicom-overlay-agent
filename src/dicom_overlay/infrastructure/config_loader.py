"""Configuration loader — reads config.yaml into AppConfig."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from dicom_overlay.domain.entities import (
    AnalysisConfig,
    AppConfig,
    HotkeyConfig,
    MonitorConfig,
    OpenClawConfig,
    OverlayConfig,
    ROICrop,
    TriggerMode,
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
    analysis_raw = raw.get("analysis", {})
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
        phi_roi=_parse_roi_crop(roi_raw),
        openclaw=OpenClawConfig(
            gateway_url=oc_raw.get("gateway_url", "ws://127.0.0.1:18789"),
            reconnect_interval_sec=oc_raw.get("reconnect_interval_sec", 5),
            timeout_sec=oc_raw.get("timeout_sec", 15),
            gateway_start_timeout_sec=oc_raw.get(
                "gateway_start_timeout_sec", 180
            ),
            connect_timeout_sec=oc_raw.get("connect_timeout_sec"),
            inference_timeout_sec=oc_raw.get("inference_timeout_sec"),
            analyze_retries=oc_raw.get("analyze_retries", 1),
            analyze_retry_backoff_sec=oc_raw.get("analyze_retry_backoff_sec", 1.5),
            max_image_edge_px=oc_raw.get("max_image_edge_px", 1568),
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
        analysis=AnalysisConfig(
            trigger_mode=_parse_trigger_mode(
                analysis_raw.get("trigger_mode", TriggerMode.HYBRID.value)
            ),
            multi_pass_enabled=bool(analysis_raw.get("multi_pass_enabled", True)),
            multi_pass_max_zoom_targets=int(
                analysis_raw.get("multi_pass_max_zoom_targets", 2)
            ),
        ),
        region_maps=raw.get("region_maps", {}),
        modalities=raw.get("modalities"),
        debug_save_screenshots=debug_raw.get("save_screenshots", False),
        log_level=debug_raw.get("log_level", "INFO"),
        log_file=debug_raw.get("log_file", "overlay_agent.log"),
    )


def _parse_trigger_mode(value: object) -> TriggerMode:
    if isinstance(value, TriggerMode):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        for mode in TriggerMode:
            if mode.value == normalized:
                return mode
    logger.warning("Unknown trigger mode %r, using hybrid", value)
    return TriggerMode.HYBRID


def _parse_roi_crop(raw: object) -> ROICrop:
    """Parse only explicitly configured, viewer-relative ROI records.

    Older builds stored workstation-specific full-screen margins without a
    coordinate-space or reference-size marker. Treating those values as valid
    on another workstation could capture outside the DICOM viewer, so legacy
    records intentionally require one fresh ROI confirmation.
    """

    data = raw if isinstance(raw, dict) else {}
    return ROICrop(
        top=int(data.get("top", 0)),
        bottom=int(data.get("bottom", 0)),
        left=int(data.get("left", 0)),
        right=int(data.get("right", 0)),
        configured=data.get("configured") is True,
        coordinate_space=str(data.get("coordinate_space", "viewer")),
        reference_width=int(data.get("reference_width", 0)),
        reference_height=int(data.get("reference_height", 0)),
    )


def save_roi_config(path: Path, roi: ROICrop) -> None:
    """Update only the phi_roi section in config.yaml."""
    if (
        not roi.configured
        or roi.coordinate_space != "viewer"
        or roi.reference_width <= 0
        or roi.reference_height <= 0
    ):
        raise ValueError("ROI must be configured relative to a viewer window")
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
        "configured": True,
        "coordinate_space": "viewer",
        "reference_width": roi.reference_width,
        "reference_height": roi.reference_height,
    }

    with path.open("w", encoding="utf-8") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True)

    logger.info("ROI config saved to %s", path)
