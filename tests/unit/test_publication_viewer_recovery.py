"""Retain paid scientific output only while the original source can be recovered."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from dicom_overlay.domain.entities import AgentState, ROICrop, WindowRect
from dicom_overlay.domain.services import CaptureBlockedError
from tests.unit.test_scientific_desktop_publication import (
    changed_pixels,
    configured,
)
from tests.unit.test_scientific_desktop_publication import (
    draft_request as draft_request,
)
from tests.unit.test_scientific_desktop_publication import inputs as inputs
from tests.unit.test_scientific_desktop_publication import replies as replies


@pytest.mark.parametrize(
    "state",
    [
        AgentState.ANALYZING,
        AgentState.PAUSED,
        AgentState.DISPLAYING,
        AgentState.MONITORING,
    ],
)
def test_queued_wait_status_cannot_overwrite_newer_ui_state(state):
    path = Path(__file__).resolve().parents[2] / "src/dicom_overlay/__main__.py"
    tree = ast.parse(path.read_text("utf-8"))
    slot = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "on_publication_status"
    )
    messages = []
    scope = {
        "agent": SimpleNamespace(state=state),
        "AgentState": AgentState,
        "control_bar": SimpleNamespace(set_status=messages.append),
    }
    exec(compile(ast.Module(body=[slot], type_ignores=[]), str(path), "exec"), scope)
    scope["on_publication_status"]("synthetic wait status")
    assert messages == (
        ["synthetic wait status"] if state is AgentState.ANALYZING else []
    )


@pytest.fixture
def recovering(tmp_path, replies, monkeypatch):
    agent, monitor, legacy, gateway, readers, published = configured(tmp_path, replies)
    original_window = monitor.window
    identity = [55, 66, "SyntheticClass"]
    monkeypatch.setattr(monitor, "capture_target_identity", lambda: tuple(identity))
    ready = asyncio.Event()
    statuses = []

    def status(text):
        statuses.append(text)
        ready.set()

    agent.on_publication_status = status
    original_factory = agent._scientific_reader_factory

    def factory(raw, modality):
        reader = original_factory(raw, modality)
        original_prepare = reader.prepare

        async def prepare():
            result = await original_prepare()
            monitor.window = None
            return result

        reader.prepare = prepare
        return reader

    agent._scientific_reader_factory = factory
    return (
        agent,
        monitor,
        legacy,
        gateway,
        readers,
        published,
        original_window,
        identity,
        ready,
        statuses,
    )


async def begin(recovering):
    agent, _, _, gateway, _, published, _, _, ready, _ = recovering
    await agent.start()
    await agent.tick()
    task = asyncio.create_task(agent.trigger_manual())
    await asyncio.wait_for(ready.wait(), 3)
    assert len(gateway.sent) == 5 and not published
    assert agent.state is AgentState.ANALYZING
    assert agent.displayed_review_snapshot is None
    return task


@pytest.mark.parametrize("changed", [False, True])
async def test_restore_same_window_checks_pixels_without_repeating_model(
    recovering, changed
):
    agent, monitor, legacy, gateway, readers, published, window, _, _, statuses = (
        recovering
    )
    task = await begin(recovering)
    await (
        agent.trigger_manual()
    )  # Duplicate Analyze during waiting is not another request.
    assert len(monitor.capture_rects) == 1
    if changed:
        monitor.screenshot = changed_pixels()
    monitor.window = window
    await asyncio.wait_for(task, 3)
    assert len(gateway.sent) == 5 and legacy.analyze_calls == 0
    assert len(statuses) == 2 and all("不重送判讀" in text for text in statuses)
    if changed:
        assert not published and agent.last_result is None
        assert agent.last_withheld_review.reason == "image_changed_during_analysis"
        assert len(readers[0].session.records) == 7
    else:
        assert agent.state is AgentState.DISPLAYING and len(published) == 1
        assert len(readers[0].session.records) == 8
        assert len(monitor.capture_rects) == 3


@pytest.mark.parametrize("part,new_value", [(0, 99), (1, 99), (2, "OtherClass")])
async def test_identical_pixels_in_replacement_window_are_never_published(
    recovering, part, new_value
):
    agent, monitor, _, gateway, _, published, window, identity, _, _ = recovering
    task = await begin(recovering)
    identity[part] = new_value
    monitor.window = window
    await asyncio.wait_for(task, 3)
    assert not published and agent.last_image_base64 == ""
    assert (
        agent.last_withheld_review.reason
        == "viewer_identity_changed_before_publication"
    )
    assert len(monitor.capture_rects) == 1 and len(gateway.sent) == 5


@pytest.mark.parametrize("action", ["pause", "pause_resume", "stop", "cancel", "roi"])
async def test_interrupt_wait_discards_pending_result_without_reinference(
    recovering, action
):
    agent, monitor, _, gateway, _, published, window, _, _, _ = recovering
    task = await begin(recovering)
    if action in {"pause", "pause_resume"}:
        agent.pause()
        if action == "pause_resume":
            agent.resume()
    elif action == "stop":
        await agent.stop()
    elif action == "roi":
        agent.on_roi_setup_complete(ROICrop())
    else:
        task.cancel()
    monitor.window = window
    if action == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        await asyncio.wait_for(task, 3)
    assert not published and agent.last_result is None
    assert agent.displayed_review_snapshot is None and agent.last_image_base64 == ""
    assert len(monitor.capture_rects) == 1 and len(gateway.sent) == 5


async def test_occlusion_after_restore_does_not_capture_hidden_pixels(
    recovering, monkeypatch
):
    agent, monitor, _, gateway, _, published, window, _, _, _ = recovering
    task = await begin(recovering)

    def blocked(_rect):
        raise CaptureBlockedError("viewer_roi_obstructed")

    monkeypatch.setattr(monitor, "verify_capture_target", blocked)
    monitor.window = window
    await asyncio.wait_for(task, 3)
    assert (
        not published
        and agent.last_withheld_review.reason
        == "viewer_unverifiable_before_publication"
    )
    assert len(monitor.capture_rects) == 1 and len(gateway.sent) == 5


async def test_restored_same_window_may_move_but_roi_does_not_expand(recovering):
    _agent, monitor, _, gateway, _, published, window, _, _, _ = recovering
    task = await begin(recovering)
    monitor.window = WindowRect(
        window.left + 100, window.top + 50, window.width, window.height
    )
    await asyncio.wait_for(task, 3)
    assert len(published) == 1 and len(gateway.sent) == 5
    before, after, final = monitor.capture_rects
    assert (after.width, after.height) == (before.width, before.height)
    assert (after.left, after.top) == (before.left + 100, before.top + 50)
    assert final == after


async def test_recovery_after_preview_still_needs_second_pixel_check(
    tmp_path, replies, monkeypatch
):
    agent, monitor, legacy, gateway, _, published = configured(tmp_path, replies)
    window = monitor.window
    monkeypatch.setattr(
        monitor, "capture_target_identity", lambda: (55, 66, "SyntheticClass")
    )
    ready = asyncio.Event()
    agent.on_publication_status = lambda _text: ready.set()
    original = agent.on_scientific_review

    async def presenter(run_id, prepared):
        receipt = await original(run_id, prepared)
        monitor.window = None
        return receipt

    agent.on_scientific_review = presenter
    await agent.start()
    await agent.tick()
    task = asyncio.create_task(agent.trigger_manual())
    await asyncio.wait_for(ready.wait(), 3)
    assert len(monitor.capture_rects) == 2 and not published
    monitor.screenshot = changed_pixels()
    monitor.window = window
    await asyncio.wait_for(task, 3)
    assert (
        not published
        and agent.last_withheld_review.reason == "image_changed_during_analysis"
    )
    assert len(gateway.sent) == 5 and legacy.analyze_calls == 0


@pytest.mark.parametrize("overshoot", [0.0, 0.1], ids=["at-deadline", "after-deadline"])
async def test_deadline_does_not_accept_window_restored_too_late(
    recovering, monkeypatch, overshoot
):
    from dicom_overlay.application import overlay_agent

    agent, monitor, _, _, _, published, window, _, _, _ = recovering
    await agent.start()
    agent._transition(AgentState.ANALYZING)
    monitor.window = None
    clock = [100.0]
    deadline = clock[0] + 0.01
    sleeps = []
    reasons = []
    original_withhold = agent._withhold_review

    def withhold(reason, **kwargs):
        reasons.append(reason)
        original_withhold(reason, **kwargs)

    monkeypatch.setattr(agent, "_withhold_review", withhold)

    async def restore_at_deadline(delay):
        sleeps.append(delay)
        clock[0] = deadline + overshoot
        monitor.window = window

    # Real asyncio timers may wake before a 10ms deadline on Windows. Control
    # this module's clock/sleep only, not asyncio's global scheduler or time.
    monkeypatch.setattr(
        overlay_agent, "time", SimpleNamespace(monotonic=lambda: clock[0])
    )
    monkeypatch.setattr(
        overlay_agent, "asyncio", SimpleNamespace(sleep=restore_at_deadline)
    )
    result = await agent._publication_window(
        expected_identity=(55, 66, "SyntheticClass"), deadline=deadline
    )
    assert result is None and not published and agent.pending_analysis
    assert agent.state is AgentState.MONITORING
    assert sleeps == [pytest.approx(0.01)]
    assert reasons == ["viewer_restore_timeout"]


async def test_adapter_without_identity_fails_closed_and_clears_stale_result(
    recovering, monkeypatch
):
    agent, monitor, _, gateway, _, published, _, _, _, statuses = recovering
    monkeypatch.setattr(monitor, "capture_target_identity", lambda: None)
    await agent.start()
    await agent.tick()
    await agent.trigger_manual()
    assert not published and not statuses
    assert agent.last_result is None and agent.last_image_base64 == ""
    assert agent.state is AgentState.WAITING
    assert agent.last_withheld_review.reason == "viewer_lost_before_publication"
    assert len(gateway.sent) == 5 and len(monitor.capture_rects) == 1
