"""Qt-thread review availability, never clinician approval or report signing."""

from __future__ import annotations

import asyncio
import json
import math
import re
from concurrent.futures import Future, InvalidStateError
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, QObject, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QPushButton

from dicom_overlay.application.contract_assembly import (
    PreparedReview,
    review_content_sha256,
)
from dicom_overlay.presentation.overlay_window import SummaryPanel
from medical_image_harness.schema import preflight_validation_errors

if TYPE_CHECKING:
    from collections.abc import Callable

    from medical_image_harness.models import AnalysisResult


class ReviewPresentationError(ValueError):
    """Fixed categories only; no clinical content or provider exception text."""


class ScientificReviewPanel(SummaryPanel):
    """Existing frameless report presentation plus the observation/evidence map."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("scientific-review-panel")
        self._availability = QLabel("研究草稿・等待檢閱，尚未完成交付")
        self._availability.setTextFormat(Qt.TextFormat.PlainText)
        self._availability.setWordWrap(True)
        self._availability.setStyleSheet("color: #ffcb70; padding: 4px;")
        self._layout.insertWidget(2, self._availability)
        self._observations = QPlainTextEdit()
        self._evidence = QPlainTextEdit()
        for widget, title in (
            (self._observations, "Observations"),
            (self._evidence, "Evidence"),
        ):
            widget.setReadOnly(True)
            widget.setStyleSheet("color: #e5e7eb; background: #171923;")
            self._tabs.addTab(widget, title)
        self._close_button = QPushButton("關閉檢閱")
        self._close_button.clicked.connect(self.hide)
        self._layout.addWidget(self._close_button)
        self._content_sha256 = ""

    @property
    def content_sha256(self) -> str:
        return self._content_sha256

    def update_result(self, result: AnalysisResult) -> None:
        # A replacement through the inherited API is not a bound prepared view.
        self._content_sha256 = ""
        super().update_result(result)

    def show_prepared(self, prepared: PreparedReview) -> None:
        result = prepared.result
        payload = result.to_contract_payload(validate=False)
        if review_content_sha256(
            result
        ) != prepared.content_sha256 or preflight_validation_errors(payload):
            raise ReviewPresentationError("invalid_prepared_review")
        # Presentation-only copy: show actual workflow prefix in the Process tab.
        result.analysis_trace = deepcopy(result.workflow_events)
        self.update_result(result)
        self._observations.setPlainText(
            "\n\n".join(
                f"{item.id} · {item.anatomy}\n{item.finding}\n"
                f"{item.polarity.value} / {item.status.value} / "
                f"assessable={item.assessable}\n"
                f"Evidence: {', '.join(item.evidence_ids)}\n"
                f"Review question: {item.question or '—'}"
                for item in result.observations
            )
        )
        self._evidence.setPlainText(
            "\n\n".join(
                f"{item.id} · {item.kind}\n{item.description}\n"
                f"Source: {item.source_ref}\nSHA-256: {item.source_image_sha256}\n"
                f"Tool: {item.tool_name or '—'} {item.tool_version}\n"
                f"Source-normalized boxes: "
                + (
                    "; ".join(
                        f"({box.x:g}, {box.y:g}, {box.w:g}, {box.h:g}), bound={box.verified}"
                        for box in item.bboxes
                    )
                    or "none"
                )
                for item in result.evidence
            )
        )
        self._availability.setText("研究草稿・待醫師檢閱，非核准報告")
        self._content_sha256 = prepared.content_sha256
        self._tabs.setCurrentIndex(0)
        self.show()
        self.raise_()

    def clear(self) -> None:
        super().clear()
        self._observations.clear()
        self._evidence.clear()
        self._content_sha256 = ""
        self._availability.setText("檢閱已失效")


@dataclass(eq=False)
class _Presentation:
    run_id: str
    source_sha256: str
    prepared: PreparedReview
    future: Future[bytes]
    painted: bool = False


class QtReviewPresenter(QObject):
    """Callable from the async bridge; all QWidget operations stay on Qt thread.

    ``is_current`` runs on the UI thread, before render, before acknowledgement,
    and while visible. The host must bind it to the active image/revision, not
    supply an unconditional true. A revoked availability must also invalidate
    any host publication; the signal is not a clinical approval event.
    """

    _requested = pyqtSignal(object)
    _cancelled = pyqtSignal(object)
    invalidated = pyqtSignal(str)

    def __init__(
        self,
        panel: ScientificReviewPanel,
        is_current: Callable[[str, str], bool],
        *,
        timeout_seconds: float = 15.0,
    ) -> None:
        app = QApplication.instance()
        if app is None or QThread.currentThread() != app.thread():
            raise ReviewPresentationError("presenter_requires_qt_thread")
        if (
            not callable(is_current)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ReviewPresentationError("invalid_presenter_configuration")
        super().__init__(panel)
        self._panel = panel
        self._is_current = is_current
        self._timeout_seconds = timeout_seconds
        self._active: _Presentation | None = None
        # Runtime connect() supports type; the pinned Qt stubs omit it.
        self._requested.connect(self._show, type=Qt.ConnectionType.QueuedConnection)  # type: ignore[call-arg]
        self._cancelled.connect(self._cancel, type=Qt.ConnectionType.QueuedConnection)  # type: ignore[call-arg]
        panel.installEventFilter(self)
        self._watch = QTimer(self)
        self._watch.setInterval(100)
        self._watch.timeout.connect(self._check)

    async def __call__(self, run_id: str, prepared: PreparedReview) -> bytes:
        if re.fullmatch(r"[a-f0-9]{32}", run_id) is None:
            raise ReviewPresentationError("invalid_review_run_id")
        snapshot = deepcopy(prepared)
        provenance = snapshot.result.to_contract_payload(validate=False)[
            "input_provenance"
        ]
        if not isinstance(provenance, dict):
            raise ReviewPresentationError("missing_review_source")
        source = provenance.get("source_image_sha256")
        if not isinstance(source, str):
            raise ReviewPresentationError("missing_review_source")
        request = _Presentation(run_id, source, snapshot, Future())
        self._requested.emit(request)
        try:
            return await asyncio.wait_for(
                asyncio.wrap_future(request.future), self._timeout_seconds
            )
        except BaseException:
            request.future.cancel()
            self._cancelled.emit(request)
            raise

    def _current(self, request: _Presentation) -> bool:
        try:
            return self._is_current(request.run_id, request.source_sha256) is True
        except Exception:
            return False

    @staticmethod
    def _fail(request: _Presentation, category: str) -> None:
        # Cancellation can race a queued Qt event.
        with suppress(InvalidStateError):
            request.future.set_exception(ReviewPresentationError(category))

    @pyqtSlot(object)
    def _show(self, request: _Presentation) -> None:
        if request.future.done():
            return
        if self._active is not None:
            self._fail(request, "review_surface_busy")
            return
        if not self._current(request):
            self._fail(request, "review_scope_expired")
            return
        self._active = request
        try:
            self._panel.show_prepared(request.prepared)
        except Exception:
            self._revoke("review_render_failed")
            return
        # A synchronous hide/close during show_prepared may already revoke it.
        if self._active is request:
            self._watch.start()

    @pyqtSlot(object)
    def _cancel(self, request: _Presentation) -> None:
        if self._active is request:
            self._revoke("review_cancelled")

    def _revoke(self, category: str) -> None:
        request = self._active
        self._active = None
        self._watch.stop()
        if request is None:
            return
        self._fail(request, category)
        self._panel.hide()
        self._panel.clear()
        self.invalidated.emit(request.run_id)

    @pyqtSlot()
    def invalidate(self) -> None:
        """Call on the Qt thread when ROI/source/analysis scope is revoked."""
        self._revoke("review_scope_expired")

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        # Qt can deliver teardown events after Python wrapper attributes clear.
        request = getattr(self, "_active", None)
        if (
            watched is getattr(self, "_panel", None)
            and request is not None
            and event is not None
        ):
            if event.type() in (QEvent.Type.Hide, QEvent.Type.Close):
                self._revoke("review_surface_closed")
            elif event.type() == QEvent.Type.Paint:
                request.painted = True
                QTimer.singleShot(0, self._check)
        return False

    @pyqtSlot()
    def _check(self) -> None:
        request = self._active
        if request is None:
            return
        if (
            request.future.cancelled()
            or not self._current(request)
            or self._panel.content_sha256 != request.prepared.content_sha256
        ):
            self._revoke("review_scope_expired")
            return
        handle = self._panel.windowHandle()
        if (
            request.painted
            and self._panel.isVisible()
            and handle is not None
            and handle.isExposed()
            and self._panel.content_sha256 == request.prepared.content_sha256
            and not request.future.done()
        ):
            raw = json.dumps(
                {
                    "run_id": request.run_id,
                    "source_image_sha256": request.source_sha256,
                    "review_content_sha256": request.prepared.content_sha256,
                    "surface": "qt-scientific-review",
                    "available": True,
                }
            ).encode()
            try:
                request.future.set_result(raw)
            except InvalidStateError:
                self._revoke("review_cancelled")
