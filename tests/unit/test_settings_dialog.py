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
    assert "OpenAI GPT-5.6 Luna Vision" in labels
    assert "OpenRouter" in labels
    assert "GitHub Copilot CLI BYOK-compatible" in labels
    assert dialog.selected_profile().key == "openai-luna"


def test_settings_dialog_selects_the_model_in_the_active_openclaw_config(
    qtbot, tmp_path
):
    config_path = tmp_path / "openclaw" / "openclaw.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        '{"agents":{"defaults":{"model":{"primary":"openai/gpt-5.4-mini"}}}}',
        encoding="utf-8",
    )

    dialog = SettingsDialog(repo_root=tmp_path)
    qtbot.addWidget(dialog)

    assert dialog.selected_profile().key == "openai-vision"


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
    assert dialog._waveform_assist_status.text() == "Not configured"


def test_settings_dialog_shows_configured_waveform_assist_without_secret(
    qtbot, tmp_path
):
    (tmp_path / ".env").write_text(
        "DICOM_ECGFOUNDER_ENDPOINT=http://127.0.0.1:18790/v1/analyze\n"
        "DICOM_ECGFOUNDER_TOKEN=super-secret-test-token\n",
        encoding="utf-8",
    )

    dialog = SettingsDialog(repo_root=tmp_path)
    qtbot.addWidget(dialog)

    assert dialog._waveform_assist_status.text() == "Evaluation sidecar configured"
    assert (
        "trusted study-to-waveform binding" in dialog._waveform_assist_status.toolTip()
    )
    assert "super-secret" not in dialog._waveform_assist_status.text()
