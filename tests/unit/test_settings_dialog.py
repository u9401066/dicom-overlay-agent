from __future__ import annotations

from dicom_overlay.presentation.settings_dialog import SettingsDialog


def test_settings_dialog_lists_desktop_provider_profiles(qtbot, tmp_path):
    dialog = SettingsDialog(repo_root=tmp_path)
    qtbot.addWidget(dialog)

    labels = [
        dialog._provider_combo.itemText(i)
        for i in range(dialog._provider_combo.count())
    ]

    assert "OpenAI Codex" in labels
    assert "OpenAI GPT-5.4 Mini Vision" in labels
    assert "OpenRouter" in labels
    assert "GitHub Copilot CLI BYOK-compatible" in labels


def test_settings_dialog_updates_fields_when_provider_changes(qtbot, tmp_path):
    dialog = SettingsDialog(repo_root=tmp_path)
    qtbot.addWidget(dialog)

    openrouter_index = next(
        i
        for i in range(dialog._provider_combo.count())
        if dialog._provider_combo.itemData(i).key == "openrouter"
    )
    dialog._provider_combo.setCurrentIndex(openrouter_index)

    assert dialog._model_edit.text() == "minimax/minimax-m3"
    assert dialog._base_url_edit.text() == "https://openrouter.ai/api/v1"
    assert dialog._api_key_env_edit.text() == "OPENROUTER_API_KEY"


def test_settings_dialog_exposes_bounded_multi_pass_controls(qtbot, tmp_path):
    dialog = SettingsDialog(
        repo_root=tmp_path,
        multi_pass_enabled=False,
        multi_pass_max_zoom_targets=4,
    )
    qtbot.addWidget(dialog)

    assert dialog._multi_pass_check.isChecked() is False
    assert dialog._multi_pass_check.text() == "Multi-pass clinical review"
    assert "discovery" in dialog._multi_pass_check.toolTip()
    assert dialog._max_zoom_targets.value() == 4
    assert dialog._max_zoom_targets.minimum() == 1
    assert dialog._max_zoom_targets.maximum() == 5
