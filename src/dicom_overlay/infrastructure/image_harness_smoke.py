"""Executable smoke harness for the medical image interpretation loop."""

from __future__ import annotations

import contextlib
import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import websockets
from PIL import Image, ImageDraw, ImageFont

from dicom_overlay.application.overlay_agent import OverlayAgent
from dicom_overlay.domain.entities import AppConfig, TriggerMode, WindowRect
from dicom_overlay.domain.services import ScreenMonitorService
from dicom_overlay.infrastructure.openclaw_client import OpenClawClient
from dicom_overlay.infrastructure.openclaw_runtime import build_harness_manifest
from dicom_overlay.infrastructure.region_mapper import RegionMapper
from dicom_overlay.infrastructure.screen_monitor import ImageProcessor

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class ImageHarnessSmokeResult:
    """Result artifact paths and key assertions from the smoke harness."""

    ok: bool
    summary: str
    log_path: Path
    result_path: Path
    sample_image_path: Path
    request_count: int


class _HarnessScreenMonitor(ScreenMonitorService):
    def __init__(self, image_bytes: bytes) -> None:
        self._image_bytes = image_bytes
        self._hash = "1111111111111111"
        self._window = WindowRect(left=0, top=0, width=900, height=600)

    def find_target_window(self, _keywords: list[str]) -> WindowRect | None:
        return self._window

    def capture_region(self, _rect: WindowRect) -> bytes:
        return self._image_bytes

    def compute_hash(self, _image_data: bytes) -> str:
        return self._hash

    def has_changed(self, hash1: str, hash2: str, _threshold: int) -> bool:
        return hash1 != hash2

    def advance_image_hash(self) -> None:
        self._hash = "2222222222222222"


async def run_image_harness_smoke(
    *,
    output_dir: Path,
    show_viewer: bool = False,
) -> ImageHarnessSmokeResult:
    """Run the full image-display -> OpenClaw Gateway -> overlay-agent loop."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_image_path = output_dir / "sample-ekg.png"
    log_path = output_dir / "harness_smoke.log"
    result_path = output_dir / "result.json"

    image_bytes = create_sample_ekg_image(sample_image_path)
    viewer = _maybe_show_viewer(sample_image_path) if show_viewer else None
    received_messages: list[dict[str, Any]] = []
    result_payload = _mock_result_payload()

    async def handler(websocket: Any) -> None:
        connect_raw = await websocket.recv()
        connect_request = json.loads(connect_raw)
        received_messages.append(connect_request)
        await websocket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": connect_request["id"],
                    "ok": True,
                    "payload": {"status": "connected"},
                }
            )
        )

        chat_raw = await websocket.recv()
        chat_request = json.loads(chat_raw)
        received_messages.append(chat_request)
        run_id = str(uuid4())
        await websocket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": chat_request["id"],
                    "ok": True,
                    "payload": {"status": "accepted", "runId": run_id},
                }
            )
        )
        await websocket.send(
            json.dumps(
                {
                    "type": "event",
                    "payload": {
                        "runId": run_id,
                        "state": "final",
                        "message": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(result_payload),
                                }
                            ]
                        },
                    },
                }
            )
        )

    server = await websockets.serve(handler, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        config = _build_smoke_config(f"ws://127.0.0.1:{port}")
        monitor = _HarnessScreenMonitor(image_bytes)
        agent = OverlayAgent(
            config=config,
            screen_monitor=monitor,
            image_processor=ImageProcessor(),
            vision_analyzer=OpenClawClient(gateway_url=config.openclaw.gateway_url),
            region_mapper=RegionMapper(config.region_maps),
            screen_width=900,
            screen_height=600,
        )

        results: list[Any] = []
        errors: list[str] = []
        agent.on_analysis_result = results.append
        agent.on_error = errors.append

        await agent.start()
        await agent.tick()
        await agent.tick()
        monitor.advance_image_hash()
        await agent.tick()

        _process_viewer_events(viewer)

        if not results:
            raise RuntimeError(f"Harness produced no result; errors={errors}")

        result = results[0]
        artifact = {
            "ok": not errors,
            "summary": result.summary,
            "severity": result.severity.value,
            "findings": [
                {
                    "id": finding.id,
                    "label": finding.label,
                    "detail": finding.detail,
                    "severity": finding.severity.value,
                    "regions": finding.regions,
                    "bboxes": [
                        {"x": box.x, "y": box.y, "w": box.w, "h": box.h}
                        for box in finding.bboxes
                    ],
                }
                for finding in result.findings
            ],
            "model_used": result.model_used,
            "harness_manifest": build_harness_manifest(),
        }
        result_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        log_path.write_text(
            "\n".join(
                [
                    "DICOM Overlay image harness smoke",
                    f"sample_image={sample_image_path}",
                    f"viewer_displayed={show_viewer}",
                    f"requests={len(received_messages)}",
                    f"summary={result.summary}",
                    f"errors={errors}",
                    "gateway_frames=",
                    json.dumps(_redact_gateway_frames(received_messages), indent=2),
                ]
            ),
            encoding="utf-8",
        )
        return ImageHarnessSmokeResult(
            ok=not errors,
            summary=result.summary,
            log_path=log_path,
            result_path=result_path,
            sample_image_path=sample_image_path,
            request_count=len(received_messages),
        )
    finally:
        server.close()
        await server.wait_closed()
        _close_viewer(viewer)


def create_sample_ekg_image(path: Path) -> bytes:
    """Create a deterministic synthetic EKG-like image for smoke testing."""
    width, height = 900, 600
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    for x in range(0, width, 25):
        draw.line((x, 0, x, height), fill=(238, 220, 220), width=1)
    for y in range(0, height, 25):
        draw.line((0, y, width, y), fill=(238, 220, 220), width=1)
    for x in range(0, width, 125):
        draw.line((x, 0, x, height), fill=(220, 185, 185), width=1)
    for y in range(0, height, 125):
        draw.line((0, y, width, y), fill=(220, 185, 185), width=1)

    font = ImageFont.load_default()
    leads = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
    cell_w = width // 4
    cell_h = height // 3
    for index, lead in enumerate(leads):
        col = index % 4
        row = index // 4
        x0 = col * cell_w + 18
        y0 = row * cell_h + 22
        draw.text((x0, y0), f"Lead {lead}", fill=(30, 30, 30), font=font)
        baseline = y0 + 85
        points: list[tuple[int, int]] = []
        for step in range(0, cell_w - 40, 12):
            x = x0 + step
            y = baseline
            if step % 60 == 24:
                y -= 38
            elif step % 60 == 36:
                y += 28
            elif lead == "I" and 72 <= step <= 132:
                y -= 22
            points.append((x, y))
        draw.line(points, fill=(15, 15, 15), width=2)

    draw.rectangle((42, 58, 205, 150), outline=(220, 53, 69), width=5)
    draw.text((48, 154), "Harness target: lead_I ST elevation", fill=(180, 20, 35), font=font)

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return path.read_bytes()


def _build_smoke_config(gateway_url: str) -> AppConfig:
    config = AppConfig()
    config.analysis.trigger_mode = TriggerMode.AUTO
    config.openclaw.gateway_url = gateway_url
    config.monitor.debounce_stable_sec = 0
    config.monitor.window_title_keywords = ["DICOM Harness Viewer"]
    config.region_maps = {
        "EKG": {
            "layout": "standard_4x3",
            "regions": {
                "lead_I": {"x": 0.0, "y": 0.0, "w": 0.25, "h": 0.27},
                "lead_II": {"x": 0.0, "y": 0.27, "w": 0.25, "h": 0.27},
            },
        }
    }
    return config


def _mock_result_payload() -> dict[str, Any]:
    return {
        "modality": "EKG",
        "summary": "Harness detected the marked lead I ST-elevation region.",
        "severity": "warning",
        "model_used": "mock-openclaw-harness",
        "image_quality": "synthetic smoke image; diagnostic content is simulated",
        "next_steps": ["Inspect the red boxed lead I area first."],
        "findings": [
            {
                "id": "f1",
                "regions": ["lead_I"],
                "label": "ST elevation marker",
                "detail": "Synthetic target finding localized to lead I.",
                "severity": "warning",
                "bboxes": [{"x": 0.047, "y": 0.096, "w": 0.181, "h": 0.153}],
            }
        ],
        "checklist": {
            "image_quality": {"value": "synthetic smoke image", "status": "info"},
            "lead_I": {"value": "target marker present", "status": "warning"},
        },
    }


def _redact_gateway_frames(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    redacted = cast("list[dict[str, Any]]", json.loads(json.dumps(frames)))
    for frame in redacted:
        params = frame.get("params")
        if not isinstance(params, dict):
            continue
        attachments = params.get("attachments")
        if not isinstance(attachments, list):
            continue
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            content = attachment.get("content")
            if isinstance(content, str):
                attachment["contentLength"] = len(content)
                attachment["contentSha256"] = hashlib.sha256(
                    content.encode("ascii")
                ).hexdigest()
                attachment["content"] = "<redacted>"
    return redacted


def _maybe_show_viewer(sample_image_path: Path) -> Any:
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtWidgets import QApplication, QLabel

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    label = QLabel()
    label.setWindowTitle("DICOM Harness Viewer")
    label.setPixmap(QPixmap(str(sample_image_path)))
    label.resize(900, 600)
    label.show()
    app.processEvents()
    return label


def _process_viewer_events(viewer: Any) -> None:
    if viewer is None:
        return
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def _close_viewer(viewer: Any) -> None:
    if viewer is not None:
        with contextlib.suppress(RuntimeError):
            viewer.close()
