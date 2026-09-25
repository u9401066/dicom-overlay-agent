"""Actual queued Qt painting; deterministic synthetic scientific content."""

from __future__ import annotations

import ast
import asyncio
import json
import os
from concurrent.futures import CancelledError
from dataclasses import replace
from pathlib import Path
from time import monotonic

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from dicom_overlay.application.contract_assembly import preflight_review_contract
from dicom_overlay.infrastructure.async_bridge import AsyncBridge
from dicom_overlay.presentation.scientific_review import (
    QtReviewPresenter,
    ReviewPresentationError,
    ScientificReviewPanel,
)
from tests.unit.test_contract_assembly import inputs as inputs
from tests.unit.test_review_preflight import prefix
from tests.unit.test_scientific_draft import draft_request as draft_request
from tests.unit.test_scientific_image_session import replies as replies
from tests.unit.test_scientific_review_handoff import setup, through_second


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def prepared(inputs):
    draft, bindings = inputs
    return preflight_review_contract(draft, **prefix(bindings))


@pytest.fixture
def bridge(qt_app):
    worker = AsyncBridge()
    worker.start()
    yield worker
    worker.shutdown()
    qt_app.processEvents()


@pytest.fixture
def panel(qt_app):
    widget = ScientificReviewPanel()
    yield widget
    widget.hide()
    widget.close()
    qt_app.processEvents()


def pump(app, condition, timeout=3):
    deadline = monotonic() + timeout
    while not condition() and monotonic() < deadline:
        app.processEvents()
        QTest.qWait(5)
    assert condition(), "Qt condition timed out"


def test_background_request_waits_for_qt_paint_and_shows_evidence(
    qt_app, bridge, panel, prepared
):
    checks = []

    def current(run_id, source):
        assert QThread.currentThread() == qt_app.thread()
        checks.append((run_id, source))
        return True

    presenter = QtReviewPresenter(panel, current)
    future = bridge.submit(presenter("a" * 32, prepared))
    pump(qt_app, future.done)
    value = json.loads(future.result())
    assert value == {
        "run_id": "a" * 32,
        "source_image_sha256": prepared.result.input_provenance.source_image_sha256,
        "review_content_sha256": prepared.content_sha256,
        "surface": "qt-scientific-review",
        "available": True,
    }
    assert len(checks) >= 2 and presenter._active.painted
    assert panel.isVisible() and panel.windowHandle().isExposed()
    assert panel._tabs.count() == 5
    assert "o1" in panel._observations.toPlainText()
    assert "e1" in panel._evidence.toPlainText()
    assert prepared.result.summary in panel._summary_label.text()
    assert "非核准" in panel._availability.text()
    assert panel.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert panel.windowFlags() & Qt.WindowType.FramelessWindowHint


@pytest.mark.parametrize("failure", ["scope", "scope_exception", "bad_hash", "render"])
def test_unavailable_or_invalid_content_does_not_acknowledge(
    qt_app, bridge, panel, prepared, monkeypatch, failure
):
    def current(*_args):
        if failure == "scope_exception":
            raise RuntimeError("Synthetic scope unavailable")
        return failure != "scope"

    def bad_render(*_args):
        raise RuntimeError("Synthetic paint failure")

    if failure == "bad_hash":
        prepared = replace(prepared, content_sha256="f" * 64)
    if failure == "render":
        monkeypatch.setattr(panel, "show_prepared", bad_render)
    presenter = QtReviewPresenter(panel, current)
    future = bridge.submit(presenter("a" * 32, prepared))
    pump(qt_app, future.done)
    with pytest.raises(ReviewPresentationError):
        future.result()
    assert not panel.isVisible() and not panel.content_sha256


@pytest.mark.parametrize("reason", ["scope", "hide", "explicit", "content_replaced"])
def test_visible_review_is_revoked_and_content_cleared(
    qt_app, bridge, panel, prepared, reason
):
    scope = [True]
    revoked = []
    presenter = QtReviewPresenter(panel, lambda *_: scope[0])
    presenter.invalidated.connect(revoked.append)
    future = bridge.submit(presenter("a" * 32, prepared))
    pump(qt_app, future.done)
    future.result()
    if reason == "scope":
        scope[0] = False
    elif reason == "hide":
        panel.hide()
    elif reason == "content_replaced":
        panel.update_result(prepared.result)
    else:
        presenter.invalidate()
    pump(qt_app, lambda: not panel.isVisible())
    assert revoked == ["a" * 32]
    assert not panel.content_sha256 and not panel._observations.toPlainText()
    assert not panel._evidence.toPlainText()
    assert presenter._active is None


def test_scope_expiring_during_render_is_not_acknowledged(
    qt_app, bridge, panel, prepared, monkeypatch
):
    scope = [True]
    render = panel.show_prepared

    def expired(snapshot):
        render(snapshot)
        scope[0] = False

    monkeypatch.setattr(panel, "show_prepared", expired)
    presenter = QtReviewPresenter(panel, lambda *_: scope[0])
    future = bridge.submit(presenter("a" * 32, prepared))
    pump(qt_app, future.done)
    with pytest.raises(ReviewPresentationError, match="review_scope_expired"):
        future.result()
    assert not panel.isVisible()


def test_cancelled_queued_request_never_opens_late(qt_app, bridge, panel, prepared):
    presenter = QtReviewPresenter(panel, lambda *_: True)

    async def cancel_before_dispatch():
        task = asyncio.create_task(presenter("a" * 32, prepared))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    # Wait for worker cancellation before allowing any Qt dispatch.
    bridge.submit(cancel_before_dispatch()).result(timeout=3)
    qt_app.processEvents()
    assert not panel.isVisible() and presenter._active is None


@pytest.mark.parametrize("reason", ["cancel", "timeout"])
def test_missing_paint_cannot_acknowledge_and_cleans_up(
    qt_app, bridge, panel, prepared, monkeypatch, reason
):
    monkeypatch.setattr(
        panel,
        "show_prepared",
        lambda snapshot: setattr(panel, "_content_sha256", snapshot.content_sha256),
    )
    presenter = QtReviewPresenter(panel, lambda *_: True, timeout_seconds=0.2)
    future = bridge.submit(presenter("a" * 32, prepared))
    pump(qt_app, lambda: presenter._active is not None)
    if reason == "cancel":
        assert future.cancel()
    pump(qt_app, future.done)
    with pytest.raises(CancelledError if reason == "cancel" else TimeoutError):
        future.result()
    pump(qt_app, lambda: presenter._active is None)
    assert not panel.isVisible()


def test_new_request_cannot_replace_an_active_surface(qt_app, bridge, panel, prepared):
    presenter = QtReviewPresenter(panel, lambda *_: True)
    first = bridge.submit(presenter("a" * 32, prepared))
    pump(qt_app, first.done)
    first.result()
    second = bridge.submit(presenter("b" * 32, prepared))
    pump(qt_app, second.done)
    with pytest.raises(ReviewPresentationError, match="review_surface_busy"):
        second.result()
    assert presenter._active.run_id == "a" * 32 and panel.isVisible()
    presenter.invalidate()
    third = bridge.submit(presenter("c" * 32, prepared))
    pump(qt_app, third.done)
    assert json.loads(third.result())["run_id"] == "c" * 32


def test_untrusted_text_stays_plain_and_caller_mutation_is_detached(
    qt_app, bridge, panel, inputs
):
    draft, bindings = inputs
    draft.summary = "<img src='https://invalid.example/pixel'> Synthetic summary"
    prepared = preflight_review_contract(draft, **prefix(bindings))
    presenter = QtReviewPresenter(panel, lambda *_: True)
    future = bridge.submit(presenter("a" * 32, prepared))
    pump(qt_app, future.done)
    future.result()
    prepared._result.observations.clear()
    assert draft.summary in panel._summary_label.text()
    assert panel._summary_label.textFormat() is Qt.TextFormat.PlainText
    assert panel._observations.toPlainText()


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout_is_rejected(panel, timeout):
    with pytest.raises(ReviewPresentationError):
        QtReviewPresenter(panel, lambda *_: True, timeout_seconds=timeout)


def test_real_session_awaits_queued_qt_presentation_before_final_assembly(
    qt_app, bridge, panel, replies, tmp_path
):
    reader, gateway = setup(tmp_path, replies)
    scope = [None]
    presenter = QtReviewPresenter(panel, lambda run, source: scope[0] == (run, source))

    async def run():
        await through_second(reader)
        await reader.prepare_review()
        scope[0] = (reader.records[0].run_id, reader.provenance.source_image_sha256)
        return await reader.offer_review(presenter)

    future = bridge.submit(run())
    pump(qt_app, future.done)
    final = future.result()
    assert final.to_contract_payload()["analysis_trace"][-1]["stage"] == "human_handoff"
    assert panel.isVisible() and presenter._active.painted
    assert panel.content_sha256 == reader.prepared_review.content_sha256
    assert len(gateway.sent) == 5  # Synthetic Gateway, actual Qt rendering.
    scope[0] = None
    pump(qt_app, lambda: not panel.isVisible())


def test_presenter_must_be_constructed_on_qt_thread(bridge, panel):
    async def wrong_thread():
        return QtReviewPresenter(panel, lambda *_: True)

    future = bridge.submit(wrong_thread())
    with pytest.raises(ReviewPresentationError, match="presenter_requires_qt_thread"):
        future.result(timeout=3)


def test_quality_is_readable_without_mutating_bound_content(panel, prepared):
    original = prepared.result.to_contract_payload(validate=False)
    panel.show_prepared(prepared)
    texts = [
        panel._findings_layout.itemAt(index).widget().text()
        for index in range(panel._findings_layout.count())
        if hasattr(panel._findings_layout.itemAt(index).widget(), "text")
    ]
    quality = next(text for text in texts if text.startswith("Image quality:"))
    assert "部分可判讀" in quality and "未提供，不能推定完整" in quality
    assert (
        "Synthetic fixture only." in quality and "synthetic partial source" in quality
    )
    assert '"adequacy"' not in quality
    assert prepared.result.to_contract_payload(validate=False) == original
    process = "\n".join(
        panel._process_layout.itemAt(index).widget().text()
        for index in range(panel._process_layout.count())
        if hasattr(panel._process_layout.itemAt(index).widget(), "text")
    )
    assert "Intake" in process and "Human Handoff" not in process
    assert "Model usage requires separate receipts" in process
    assert "0/12" not in process and "Lead layout not supplied" in process


def test_close_during_render_does_not_leave_a_background_timer(
    qt_app, bridge, panel, prepared, monkeypatch
):
    render = panel.show_prepared

    def close_during_show(snapshot):
        render(snapshot)
        panel.hide()

    monkeypatch.setattr(panel, "show_prepared", close_during_show)
    presenter = QtReviewPresenter(panel, lambda *_: True)
    future = bridge.submit(presenter("a" * 32, prepared))
    pump(qt_app, future.done)
    with pytest.raises(ReviewPresentationError, match="review_surface_closed"):
        future.result()
    assert not presenter._watch.isActive() and presenter._active is None


def test_acknowledged_preview_can_retire_without_revoking_publication(
    qt_app, bridge, panel, prepared
):
    presenter = QtReviewPresenter(panel, lambda *_: True)
    revoked = []
    presenter.invalidated.connect(revoked.append)
    shown = bridge.submit(presenter("a" * 32, prepared))
    pump(qt_app, shown.done)
    shown.result()
    wrong = bridge.submit(presenter.retire("b" * 32))
    pump(qt_app, wrong.done)
    assert wrong.result() is False and panel.isVisible()
    retired = bridge.submit(presenter.retire("a" * 32))
    pump(qt_app, retired.done)
    assert retired.result() is True and not panel.isVisible()
    assert not revoked and presenter._active is None and not presenter._watch.isActive()
    # Final overlay publication uses inherited update_result after source recheck.
    panel.update_result(prepared.result)
    assert panel._observations.toPlainText() and panel._evidence.toPlainText()


def test_closed_preview_cannot_be_retired_as_accepted(qt_app, bridge, panel, prepared):
    presenter = QtReviewPresenter(panel, lambda *_: True)
    shown = bridge.submit(presenter("a" * 32, prepared))
    pump(qt_app, shown.done)
    shown.result()
    panel.hide()
    retired = bridge.submit(presenter.retire("a" * 32))
    pump(qt_app, retired.done)
    assert retired.result() is False


def test_real_agent_uses_exact_main_callback_and_qt_retirement_before_publication(
    qt_app, bridge, panel, tmp_path, replies
):
    from tests.unit.test_scientific_desktop_publication import analyze, configured

    agent, monitor, legacy, gateway, readers, published = configured(tmp_path, replies)
    presenter = QtReviewPresenter(panel, agent.scientific_review_is_current)
    presenter.invalidated.connect(agent.invalidate_scientific_review)
    # Execute the exact main callback, not a second implementation of its ordering.
    source = Path(__file__).resolve().parents[2] / "src/dicom_overlay/__main__.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    callback = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "offer_scientific_review"
    )
    environment = {"scientific_presenter": presenter}
    exec(
        compile(ast.Module(body=[callback], type_ignores=[]), str(source), "exec"),
        environment,
    )
    agent.on_scientific_review = environment["offer_scientific_review"]
    pending = bridge.submit(analyze(agent))
    pump(qt_app, pending.done)
    pending.result()
    assert len(published) == 1 and len(gateway.sent) == 5
    assert len(monitor.capture_rects) == 3 and legacy.analyze_calls == 0
    assert presenter._active is None and not panel.isVisible()
    assert not panel._observations.toPlainText()  # Preview was retired, not left stale.
    assert agent.displayed_review_snapshot.result is published[0]
    assert (
        readers[0].session.final_result.to_contract_payload()
        == published[0].to_contract_payload()
    )
    # Existing overlay update_result is the subsequent final-display path.
    panel.update_result(published[0])
    assert panel._observations.toPlainText() and panel._evidence.toPlainText()
