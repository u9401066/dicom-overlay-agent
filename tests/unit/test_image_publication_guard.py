import asyncio
import io

import pytest
from PIL import Image, PngImagePlugin, UnidentifiedImageError

from dicom_overlay.application.annotation_accumulator import AnnotationAccumulator
from dicom_overlay.application.overlay_agent import OverlayAgent
from dicom_overlay.domain.entities import AgentState, AppConfig, ROICrop, WindowRect
from dicom_overlay.domain.services import CaptureBlockedError
from dicom_overlay.infrastructure.screen_monitor import ImageProcessor
from tests.unit.test_agent import (
    BlockingVisionAnalyzer,
    MockImageProcessor,
    MockRegionMapper,
    MockScreenMonitor,
)


def _agent():
    monitor = MockScreenMonitor()
    monitor.window = WindowRect(30, 40, 1000, 700)
    analyzer = BlockingVisionAnalyzer()
    processor = MockImageProcessor()
    agent = OverlayAgent(
        config=AppConfig(
            phi_roi=ROICrop(configured=True, reference_width=1000, reference_height=700)
        ),
        screen_monitor=monitor,
        image_processor=processor,
        vision_analyzer=analyzer,
        region_mapper=MockRegionMapper(),
        annotation_accumulator=AnnotationAccumulator(),
    )
    return agent, monitor, analyzer, processor


@pytest.mark.parametrize("changed", [False, True])
async def test_identical_geometry_does_not_prove_current_image_identity(changed):
    agent, monitor, analyzer, _ = _agent()
    transitions, published = [], []
    agent.on_state_change = lambda _old, new: transitions.append(new)
    agent.on_analysis_result = published.append
    await agent.start()
    await agent.tick()
    task = asyncio.create_task(agent.trigger_manual())
    await analyzer.entered.wait()
    original = monitor.screenshot
    if changed:
        monitor.screenshot = b"different image, same window and same perceptual hash"
    analyzer.release.set()
    await task
    assert analyzer.analyze_calls == 1
    assert len(monitor.capture_rects) == 2
    assert monitor.capture_rects[0] == monitor.capture_rects[1]
    if changed:
        assert AgentState.DISPLAYING not in transitions
        assert not published
        assert agent.state is AgentState.MONITORING
        assert agent.pending_analysis
        assert agent.review_snapshot is None
        assert agent.last_result is None and agent.last_image_base64 == ""
        assert agent.last_capture_rect is None
        assert agent.last_withheld_review.reason == "image_changed_during_analysis"
        assert (
            agent.last_withheld_review.snapshot.result.summary
            == analyzer.result.summary
        )
        assert monitor.screenshot != original
    else:
        assert len(published) == 1 and agent.state is AgentState.DISPLAYING
        assert agent.last_withheld_review is None


@pytest.mark.parametrize("failure", ["precheck", "capture", "postcheck", "decode"])
async def test_unverifiable_final_roi_never_publishes(monkeypatch, failure):
    agent, monitor, analyzer, processor = _agent()
    published = []
    agent.on_analysis_result = published.append
    await agent.start()
    await agent.tick()
    task = asyncio.create_task(agent.trigger_manual())
    await analyzer.entered.wait()
    checks = 0

    def verify(_rect):
        nonlocal checks
        checks += 1
        if (failure == "precheck" and checks == 1) or (
            failure == "postcheck" and checks == 2
        ):
            raise CaptureBlockedError("occluded")

    def fail(*_args):
        raise ValueError("unverifiable")

    monkeypatch.setattr(monitor, "verify_capture_target", verify)
    if failure == "capture":
        monkeypatch.setattr(monitor, "capture_region", fail)
    if failure == "decode":
        monkeypatch.setattr(processor, "same_image_pixels", fail)
    analyzer.release.set()
    await task
    assert not published and agent.displayed_review_snapshot is None
    assert agent.last_withheld_review.reason == "viewer_unverifiable_before_publication"
    assert analyzer.analyze_calls == 1


async def test_pause_in_second_hide_beat_cannot_publish_or_recapture():
    agent, monitor, analyzer, _ = _agent()
    calls = []

    def hide():
        calls.append(agent.state)
        if len(calls) == 2:
            agent.pause()

    agent.on_before_capture = hide
    await agent.start()
    await agent.tick()
    analyzer.release.set()
    await agent.trigger_manual()
    assert calls == [AgentState.CAPTURING, AgentState.ANALYZING]
    assert agent.state is AgentState.PAUSED
    assert len(monitor.capture_rects) == 1
    assert agent.review_snapshot is None
    assert agent.last_withheld_review.reason == "state_changed_before_publication"


def _png(image, note=""):
    output = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("note", note)
    image.save(output, format="PNG", pnginfo=metadata)
    return output.getvalue()


def test_pixel_identity_ignores_metadata_but_not_one_changed_pixel():
    processor = ImageProcessor()
    original = Image.new("RGB", (64, 64), "white")
    encoded = _png(original, "first")
    assert processor.same_image_pixels(encoded, _png(original, "different metadata"))
    changed = original.copy()
    changed.putpixel((31, 31), (254, 255, 255))
    assert not processor.same_image_pixels(encoded, _png(changed))
    assert not processor.same_image_pixels(
        encoded, _png(Image.new("RGB", (32, 64), "white"))
    )
    with pytest.raises(UnidentifiedImageError):
        processor.same_image_pixels(encoded, b"invalid PNG")
