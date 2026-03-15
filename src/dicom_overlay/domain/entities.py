"""Domain entities for DICOM Overlay Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


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


class Modality(Enum):
    """Supported imaging modalities."""

    EKG = "EKG"
    CXR = "CXR"
    CT_BRAIN = "CT_BRAIN"
    AUTO = "auto"


class Severity(Enum):
    """Finding severity levels (spec §3.4)."""

    CRITICAL = "critical"
    WARNING = "warning"
    NORMAL = "normal"
    INFO = "info"


@dataclass(frozen=True)
class RegionRect:
    """Percentage-based rectangle relative to ROI-cropped image."""

    x: float
    y: float
    w: float
    h: float

    def __post_init__(self) -> None:
        for attr in ("x", "y", "w", "h"):
            val = getattr(self, attr)
            if not 0.0 <= val <= 1.0:
                raise ValueError(f"{attr} must be in [0, 1], got {val}")


@dataclass(frozen=True)
class Finding:
    """A single analysis finding (spec §3.3)."""

    id: str
    regions: list[str]
    label: str
    detail: str
    severity: Severity
    bboxes: list[RegionRect] = field(default_factory=list)


@dataclass(frozen=True)
class ChecklistItem:
    """A single checklist entry."""

    value: str
    status: Severity


@dataclass
class AnalysisResult:
    """Complete analysis result from Vision API (spec §3.3)."""

    modality: Modality
    summary: str
    severity: Severity
    findings: list[Finding]
    checklist: dict[str, ChecklistItem]
    analysis_time_ms: int = 0
    model_used: str = ""


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
class ROICrop:
    """PHI ROI crop settings in pixels (spec §3.2)."""

    top: int = 60
    bottom: int = 30
    left: int = 0
    right: int = 0


@dataclass
class MonitorConfig:
    """Screen monitor configuration (spec §3.1)."""

    window_title_keywords: list[str] = field(
        default_factory=lambda: ["DICOM", "影像", "Viewer"]
    )
    polling_interval_ms: int = 500
    hash_algorithm: str = "phash"
    hash_threshold: int = 5
    debounce_stable_sec: float = 1.5


@dataclass
class OpenClawConfig:
    """OpenClaw Gateway configuration (spec §3.3)."""

    gateway_url: str = "ws://127.0.0.1:18789"
    reconnect_interval_sec: int = 5
    timeout_sec: int = 15


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
class AppConfig:
    """Root application configuration."""

    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    phi_roi: ROICrop = field(default_factory=ROICrop)
    openclaw: OpenClawConfig = field(default_factory=OpenClawConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    region_maps: dict = field(default_factory=dict)
    debug_save_screenshots: bool = False
    log_level: str = "INFO"
    log_file: str = "overlay_agent.log"
