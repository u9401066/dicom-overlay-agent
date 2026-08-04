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


class TriggerMode(Enum):
    """How image changes trigger LLM analysis."""

    MANUAL = "manual"
    HYBRID = "hybrid"
    AUTO = "auto"


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
class UserRegionAnnotation:
    """Reviewer-authored context attached to one normalized manual region."""

    region: RegionRect
    question: str = ""
    answer: str = ""


@dataclass(frozen=True)
class Finding:
    """A single analysis finding (spec §3.3).

    ``notes`` accumulates extra provenance / discussion lines (e.g. follow-up
    chat that revises or confirms this finding). They are kept separate from the
    primary ``detail`` so a clinical discussion can be appended to an overlay
    marker without clobbering the original analysis text.
    """

    id: str
    regions: list[str]
    label: str
    detail: str
    severity: Severity
    bboxes: list[RegionRect] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Model-reported certainty is intentionally qualitative.  A low-confidence
    # finding can carry a short question that the UI surfaces for human review.
    confidence: str = ""
    question: str = ""
    # Audit provenance for exports and interactive review. Primary model output
    # defaults to ``ai``; reviewer-confirmed crop follow-ups use a distinct tag.
    source: str = "ai"


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
    image_quality: str | dict[str, object] = ""
    next_steps: list[str] = field(default_factory=list)
    incomplete: bool = False
    incomplete_reasons: list[str] = field(default_factory=list)
    # Structural/parser degradation is separate from a clinically honest
    # ``incomplete`` result (for example, cropped leads or unreadable scale).
    # Eval schema gates use this field so image limitations are not scored as
    # malformed model output.
    validation_warnings: list[str] = field(default_factory=list)
    # Advisory hints asking the user to manually zoom in their DICOM viewer and
    # re-capture, because a region is too small in the screen-captured pixels to
    # resolve any further by digital crop (screenshots cap at the screen
    # resolution, e.g. 4K). Set by the multi-pass orchestrator; rendered by the
    # overlay. Empty when no manual zoom is suggested.
    zoom_hints: list[str] = field(default_factory=list)
    # Clinical safety escalation: set by the data-driven clinical consistency
    # engine when the AI's *own* structured output is internally contradictory
    # or under-calls a can't-miss pattern (e.g. it describes ST elevation yet
    # reads "normal"). The engine only escalates severity (never downgrades) and
    # flags for human review — it never imposes a diagnosis. Each reason carries
    # the medical guideline citation so the physician sees *why* it was flagged.
    review_required: bool = False
    review_reasons: list[str] = field(default_factory=list)
    # Optional Step-0 layout declaration from the model (EKG): the recognized
    # format plus the lead inventory and, when present, the rhythm-strip
    # bounding box. Used by the rhythm-strip refinement pass to crop the strip
    # at higher resolution without assuming a fixed layout. Empty when the model
    # did not declare a layout (keeps non-EKG and legacy paths unchanged).
    layout: dict = field(default_factory=dict)
    # Auditable workflow facts for this interpretation: coarse/refine stages,
    # deterministic local image aids, crop coordinates, registered tool names,
    # and explicit refinement decisions. This intentionally excludes hidden
    # chain-of-thought and stores only information safe to show to a reviewer.
    analysis_trace: list[dict[str, object]] = field(default_factory=list)


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
