"""Exercise the actual queued GUI callback without launching the desktop App."""

from __future__ import annotations

import ast
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dicom_overlay.application.regional_conversation import RegionalConversations
from dicom_overlay.domain.entities import FindingDelta, FindingOp
from medical_image_harness.models import RegionRect


def _callback(snapshot, conversations):
    # main() owns Qt/async closures. Compile this exact nested callback, rather
    # than copying its implementation into a test or starting OAuth/GUI services.
    path = Path(__file__).resolve().parents[2] / "src/dicom_overlay/__main__.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(
        item
        for item in ast.walk(tree)
        if isinstance(item, ast.FunctionDef) and item.name == "_on_review_apply_done"
    )
    environment = {
        "FindingDelta": FindingDelta,
        "FindingOp": FindingOp,
        "_current_review_snapshot": lambda: snapshot,
        "regional_conversations": conversations,
        "overlay": Mock(),
        "on_analysis_result": Mock(),
        "control_bar": Mock(),
    }
    exec(
        compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"),
        environment,
    )
    return environment


@pytest.mark.parametrize("operation", [FindingOp.ADD, FindingOp.REVISE])
def test_current_writeback_only_promotes_explicit_add_before_render(operation):
    image = base64.b64encode(b"synthetic source").decode()
    store = RegionalConversations()
    store.bind(image)
    box = RegionRect(0.1, 0.2, 0.3, 0.4)
    thread = store.thread(box)
    store.append(thread, question="Before", answer="Answer")
    result = object()
    context = _callback(SimpleNamespace(result=result, image_base64=image), store)
    delta = SimpleNamespace(
        op=operation, finding=SimpleNamespace(id="added", bboxes=[box])
    )

    def rendered(*args, **kwargs):
        if operation is FindingOp.ADD:
            assert store.thread(box, "added") is thread
        else:
            assert store.thread(box) is thread

    context["on_analysis_result"].side_effect = rendered
    context["_on_review_apply_done"](result, delta)
    context["on_analysis_result"].assert_called_once_with(
        result, announce=False, preserve_user_regions=True
    )
    if operation is FindingOp.ADD:
        context["overlay"].consume_user_region.assert_called_once_with(box)
    else:
        context["overlay"].consume_user_region.assert_not_called()


@pytest.mark.parametrize("snapshot_exists", [False, True])
def test_late_writeback_callback_cannot_restore_old_overlay_or_history(snapshot_exists):
    image = base64.b64encode(b"current image").decode()
    store = RegionalConversations()
    store.bind(image)
    box = RegionRect(0.1, 0.2, 0.3, 0.4)
    thread = store.thread(box)
    store.append(thread, question="Current", answer="Keep")
    before = store.export()
    snapshot = (
        SimpleNamespace(result=object(), image_base64=image)
        if snapshot_exists
        else None
    )
    context = _callback(snapshot, store)
    delta = SimpleNamespace(
        op=FindingOp.ADD, finding=SimpleNamespace(id="old", bboxes=[box])
    )
    context["_on_review_apply_done"](object(), delta)
    assert store.export() == before
    assert context["overlay"].mock_calls == []
    context["on_analysis_result"].assert_not_called()
    assert context["control_bar"].mock_calls == []
