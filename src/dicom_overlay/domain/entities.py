"""Domain entities for DICOM Overlay Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from medical_image_harness.models import (
    AnalysisResult,
    ChecklistItem,
    ClaimType,
    Evidence,
    Finding,
    Modality,
    Observation,
    Polarity,
    RegionRect,
    Severity,
    UserRegionAnnotation,
    VerificationStatus,
)

__all__ = [
    "AgentState",
    "AnalysisConfig",
    "AnalysisResult",
    "AppConfig",
    "ChecklistItem",
    "ClaimType",
    "DisplayFrame",
    "Evidence",
    "Finding",
    "FindingDelta",
    "FindingOp",
    "HotkeyConfig",
    "Modality",
    "MonitorConfig",
    "Observation",
    "OpenClawConfig",
    "OverlayConfig",
    "Polarity",
    "ROICrop",
    "RegionRect",
    "Severity",
    "TriggerMode",
    "UserRegionAnnotation",
    "VerificationStatus",
    "WindowRect",
]


class AgentState(Enum):
    """Agent state machine states (spec §3.5)."""

    INIT = auto()
    SETUP = auto()
    WAITING = auto()
    MONITORING = auto()
    CAPTURING = auto()
    ANALYZING = auto()
    DISPLAYING = auto()
    PAUSED = auto()
    ERROR = auto()
    RECONNECTING = auto()


class TriggerMode(Enum):
    """How image changes trigger LLM analysis."""

    MANUAL = "manual"
    HYBRID = "hybrid"
    AUTO = "auto"


class FindingOp(Enum):
    """Semantic operation a :class:`FindingDelta` applies to the overlay set.

    Lets a multi-pass agent turn *or* a human-guided chat turn write back into
    the accumulated overlay markers in a determinate, auditable way:

    - ``ADD``: contribute a new finding (deduplicated against existing markers).
    - ``REVISE``: update an existing finding (by id) — may change severity or
      append a note. This is an *explicit* decision, so it is the only path that
      may downgrade severity; geometric dedup never downgrades.
    - ``RETRACT``: remove an existing finding (by id) — e.g. the physician
      determines a flagged region is not a true finding.
    """

    ADD = "add"
    REVISE = "revise"
    RETRACT = "retract"


@dataclass(frozen=True)
class FindingDelta:
    """A single change to the accumulated overlay markers.

    Produced by a multi-pass interpretation turn or by a chat follow-up that the
    physician uses to guide / correct the reading. The application-layer
    accumulator applies it deterministically; presentation never decides merges.

    For ``RETRACT`` only ``op`` and ``finding.id`` are meaningful. For ``ADD`` /
    ``REVISE`` the ``finding`` carries the payload; ``note`` is an optional
    discussion line appended to the target finding's ``notes``.
    """

    op: FindingOp
    finding: Finding
    note: str = ""


@dataclass(frozen=True)
class WindowRect:
    """Screen coordinates of a window."""

    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


@dataclass(frozen=True)
class DisplayFrame:
    """Physical-pixel bounds and identity of one desktop display."""

    physical_rect: WindowRect
    device_name: str = ""
    monitor_index: int = 0
    is_primary: bool = False


@dataclass(frozen=True)
class ROICrop:
    """PHI-safe crop margins relative to the detected viewer window.

    A clean install is deliberately unconfigured.  The reference dimensions
    let the app scale a reviewer-selected safe area when the viewer is resized
    while keeping every capture inside that viewer's current bounds.
    """

    top: int = 0
    bottom: int = 0
    left: int = 0
    right: int = 0
    configured: bool = False
    coordinate_space: str = "viewer"
    reference_width: int = 0
    reference_height: int = 0


@dataclass
class MonitorConfig:
    """Screen monitor configuration (spec §3.1)."""

    window_title_keywords: list[str] = field(
        default_factory=lambda: ["DICOM", "影像", "Viewer"]
    )
    polling_interval_ms: int = 500
    hash_algorithm: str = "ahash"
    hash_threshold: int = 5
    debounce_stable_sec: float = 1.5


@dataclass
class OpenClawConfig:
    """OpenClaw Gateway configuration (spec §3.3)."""

    gateway_url: str = "ws://127.0.0.1:18789"
    reconnect_interval_sec: int = 5
    timeout_sec: int = 15
    # Portable OpenClaw can spend over a minute on first-run migrations and
    # antivirus scanning. This is separate from the WebSocket handshake timeout.
    gateway_start_timeout_sec: int = 180
    # Split timeouts: handshake is fast, inference can be slow on big images.
    # ``None`` means "fall back to timeout_sec" for backward compatibility.
    connect_timeout_sec: int | None = None
    inference_timeout_sec: int | None = None
    # Analysis transient-failure retry (e.g. a single inference timeout).
    analyze_retries: int = 1
    analyze_retry_backoff_sec: float = 1.5
    # Cap the longest image edge before sending to the gateway (0 disables).
    max_image_edge_px: int = 1568


@dataclass
class OverlayConfig:
    """Overlay rendering configuration (spec §3.4)."""

    position: str = "right"
    summary_panel: bool = True
    region_highlights: bool = True
    display_duration_sec: int = 30
    critical_persist: bool = True
    fade_duration_ms: int = 500
    control_bar: bool = True
    control_bar_position: str = "bottom_right"
    tts_enabled: bool = True


@dataclass
class HotkeyConfig:
    """Hotkey configuration (spec §5)."""

    trigger_manual: str = "ctrl+shift+a"
    dismiss_overlay: str = "ctrl+shift+d"
    toggle_enable: str = "ctrl+shift+e"


@dataclass
class AnalysisConfig:
    """Analysis trigger behavior configuration."""

    trigger_mode: TriggerMode = TriggerMode.HYBRID
    # Multi-pass interpretation: after a coarse first read, re-examine abnormal
    # regions at full ROI resolution to refine bounding boxes. Keep the number
    # of follow-up crops bounded so the desktop default remains predictable.
    multi_pass_enabled: bool = True
    multi_pass_max_zoom_targets: int = 2


@dataclass
class AppConfig:
    """Root application configuration."""

    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    phi_roi: ROICrop = field(default_factory=ROICrop)
    openclaw: OpenClawConfig = field(default_factory=OpenClawConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    region_maps: dict = field(default_factory=dict)
    # Optional per-modality profile overrides/additions (see ModalityRegistry).
    modalities: object = None
    debug_save_screenshots: bool = False
    log_level: str = "INFO"
    log_file: str = "overlay_agent.log"
