"""Real Qt widgets/callbacks with synthetic local data; no paid inference."""

from __future__ import annotations

import ast
import base64
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QDialog, QPushButton

from dicom_overlay.application.regional_conversation import RegionalConversations
from dicom_overlay.application.regional_history import decode_regional_history
from dicom_overlay.presentation.regional_history_dialog import RegionalHistoryDialog
from dicom_overlay.presentation.settings_dialog import SettingsDialog
from medical_image_harness.models import RegionRect


@pytest.fixture
def source():
    buffer = io.BytesIO()
    Image.new("RGB", (300, 200), "white").save(buffer, format="PNG")
    image = base64.b64encode(buffer.getvalue()).decode()
    store = RegionalConversations()
    store.bind(image)
    store.append(
        store.thread(RegionRect(0.1, 0.2, 0.3, 0.4), "f1"),
        question="<b>literal</b>",
        answer="<img src='file:///never-read'>",
    )
    return image, store


def _callbacks(names, env):
    path = Path(__file__).resolve().parents[2] / "src/dicom_overlay/__main__.py"
    nodes = [
        node
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert len(nodes) == len(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), env)


def test_settings_history_button_closes_settings_and_emits(qtbot, tmp_path):
    dialog = SettingsDialog(repo_root=tmp_path)
    qtbot.addWidget(dialog)
    observed = []
    dialog.regional_history_requested.connect(lambda: observed.append(dialog.result()))
    dialog.findChild(QPushButton, "regionalHistory").click()
    assert observed == [QDialog.DialogCode.Accepted]


def test_load_select_preview_plaintext_cancel_then_open(
    qtbot, monkeypatch, tmp_path, source
):
    image, store = source
    path = tmp_path / "regional-conversations.json"
    path.write_text(json.dumps(store.export()), encoding="utf-8")
    monkeypatch.setattr(
        "dicom_overlay.presentation.regional_history_dialog.QFileDialog.getOpenFileName",
        lambda *args: (str(path), ""),
    )
    dialog = RegionalHistoryDialog(image_base64=image, threads=[])
    qtbot.addWidget(dialog)
    # Windows' offscreen plugin has no system font fallback. Load an existing
    # local font for this owned-widget render; never install/download a font.
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msjh.ttc"
    if font_path.is_file():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            dialog.setFont(QFont(families[0], 10))
    assert not dialog._open.isEnabled()
    dialog.findChild(QPushButton, "loadRegionalHistory").click()
    assert dialog._list.count() == 1
    assert "<b>literal</b>" in dialog._transcript.toPlainText()
    assert "<img src=" in dialog._transcript.toPlainText()
    assert "unverified past-run context" in dialog._transcript.toPlainText()
    assert not dialog._preview.pixmap().isNull()
    dialog.show()
    qtbot.wait(10)
    assert dialog.grab().save(str(tmp_path / "history-dialog.png"), "PNG")
    dialog.findChild(QPushButton, "loadRegionalHistory").click()
    assert dialog._list.count() == 1
    assert dialog.selected_history is None
    dialog.reject()
    assert dialog.selected_history is None
    dialog._open.click()
    assert dialog.selected_history.turns[0].question == "<b>literal</b>"
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_bad_file_preserves_selection_and_cancel_file_picker_is_noop(
    qtbot, monkeypatch, tmp_path, source
):
    image, store = source
    history = decode_regional_history(
        json.dumps(store.export()).encode(), source_image_sha256=store.image_sha256
    )[0]
    store.restore_archive(history)
    dialog = RegionalHistoryDialog(image_base64=image, threads=store.archived_threads)
    qtbot.addWidget(dialog)
    before = dialog._transcript.toPlainText()
    warning = Mock()
    monkeypatch.setattr(
        "dicom_overlay.presentation.regional_history_dialog.QMessageBox.warning",
        warning,
    )
    path = tmp_path / "bad.json"
    path.write_text("{invalid", encoding="utf-8")
    monkeypatch.setattr(
        "dicom_overlay.presentation.regional_history_dialog.QFileDialog.getOpenFileName",
        lambda *args: (str(path), ""),
    )
    dialog._load()
    warning.assert_called_once()
    assert dialog._transcript.toPlainText() == before
    assert dialog._list.count() == 1
    monkeypatch.setattr(
        "dicom_overlay.presentation.regional_history_dialog.QFileDialog.getOpenFileName",
        lambda *args: ("", ""),
    )
    dialog._load()
    warning.assert_called_once()


@pytest.mark.parametrize(
    "changed", ["none", "revision", "image", "no-snapshot", "cancel"]
)
def test_actual_open_history_callback_rechecks_scope_and_never_queries(source, changed):
    image, old = source
    history = decode_regional_history(
        json.dumps(old.export()).encode(), source_image_sha256=old.image_sha256
    )[0]
    snapshot = SimpleNamespace(image_base64=image, revision=7)
    after = snapshot
    if changed in {"revision", "image"}:
        after = SimpleNamespace(
            image_base64=image
            if changed == "revision"
            else base64.b64encode(b"new image").decode(),
            revision=8 if changed == "revision" else 7,
        )
    elif changed == "no-snapshot":
        after = None
    store = RegionalConversations()
    dialog = Mock(selected_history=None if changed == "cancel" else history)
    env = {
        "_current_review_snapshot": Mock(side_effect=[snapshot, after]),
        "regional_conversations": store,
        "RegionalHistoryDialog": Mock(return_value=dialog),
        "_begin_chat_request": Mock(),
        "_active_region": [None],
        "control_bar": Mock(),
        "overlay": Mock(),
    }
    _callbacks({"open_regional_history"}, env)
    env["open_regional_history"]()
    if changed == "none":
        assert env["_active_region"][0] == (
            history.region,
            "",
            False,
            history.archive_id,
        )
        env["_begin_chat_request"].assert_called_once()
        env["overlay"].show_chat_response.assert_called_once()
        assert not store.archived_threads[0].turns
    else:
        assert not store.archived_threads
        env["overlay"].show_chat_response.assert_not_called()
    # No bridge/client/agent is provided: merely opening cannot issue inference.


def test_actual_inline_send_reuses_imported_region_and_original_snapshot(source):
    image, old = source
    history = decode_regional_history(
        json.dumps(old.export()).encode(), source_image_sha256=old.image_sha256
    )[0]
    snapshot = SimpleNamespace(image_base64=image, result=SimpleNamespace(findings=[]))
    processor = Mock()
    processor.crop_region_base64.return_value = "crop"
    processor.crop_region_bytes.return_value = b"crop"
    submit = Mock()
    env = {
        "_current_review_snapshot": lambda: snapshot,
        "_active_region": [(history.region, "", False, history.archive_id)],
        "overlay": Mock(),
        "control_bar": Mock(),
        "image_processor": processor,
        "_submit_region_review": submit,
    }
    _callbacks({"_continue_regional_chat"}, env)
    env["_continue_regional_chat"]("Continue this archived region")
    processor.crop_region_bytes.assert_called_once_with(image, history.region)
    assert submit.call_args.kwargs["archive_id"] == history.archive_id
    assert submit.call_args.kwargs["allow_add"] is False
    assert submit.call_args.kwargs["selected_finding"] is None
    assert submit.call_args.kwargs["snapshot"] is snapshot
