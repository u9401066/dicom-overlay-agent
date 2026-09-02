"""Desktop settings dialog for trigger mode and OpenClaw provider setup."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dicom_overlay.domain.entities import TriggerMode
from dicom_overlay.infrastructure.desktop_settings_store import DesktopSettingsStore
from dicom_overlay.infrastructure.openclaw_settings import (
    DEFAULT_VISION_PROFILE_KEY,
    ProviderAuthMode,
    ProviderProfile,
    default_provider_profiles,
)

if TYPE_CHECKING:
    from pathlib import Path


class SettingsDialog(QDialog):
    """GUI control panel for the OpenClaw settings this app owns."""

    trigger_mode_saved = pyqtSignal(object)
    analysis_settings_saved = pyqtSignal(bool, int, bool)
    vision_test_requested = pyqtSignal(object)
    roi_setup_requested = pyqtSignal()

    def __init__(
        self,
        repo_root: Path,
        *,
        current_mode: TriggerMode = TriggerMode.HYBRID,
        multi_pass_enabled: bool = True,
        multi_pass_max_zoom_targets: int = 2,
        fast_mode_enabled: bool = True,
        config_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("DICOM Overlay Settings")
        self.setMinimumWidth(560)

        self._store = DesktopSettingsStore(
            repo_root=repo_root,
            config_path=config_path,
        )
        self._profiles = default_provider_profiles()

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_mode_tab(current_mode), "Trigger")
        tabs.addTab(
            self._build_analysis_tab(
                multi_pass_enabled,
                multi_pass_max_zoom_targets,
                fast_mode_enabled,
            ),
            "Analysis",
        )
        tabs.addTab(self._build_provider_tab(), "AI Provider")
        layout.addWidget(tabs)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self._load_profile_fields(self._provider_combo.currentData())

    def selected_profile(self) -> ProviderProfile:
        profile = cast("ProviderProfile", self._provider_combo.currentData())
        return replace(
            profile,
            model=self._model_edit.text().strip(),
            base_url=self._base_url_edit.text().strip(),
            api_key_env=self._api_key_env_edit.text().strip(),
        )

    def selected_trigger_mode(self) -> TriggerMode:
        return cast("TriggerMode", self._mode_combo.currentData())

    def _build_mode_tab(self, current_mode: TriggerMode) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        self._mode_combo = QComboBox()
        for mode, label in (
            (TriggerMode.HYBRID, "Hybrid - detect changes, ask before analysis"),
            (TriggerMode.MANUAL, "Manual - only analyze when clicked"),
            (TriggerMode.AUTO, "Auto - analyze after stable image change"),
        ):
            self._mode_combo.addItem(label, mode)
        self._mode_combo.setCurrentIndex(
            max(0, self._mode_combo.findData(current_mode))
        )
        form.addRow("Mode", self._mode_combo)

        save_mode_btn = QPushButton("Save mode")
        save_mode_btn.clicked.connect(self._save_trigger_mode)
        form.addRow("", save_mode_btn)

        roi_btn = QPushButton("Set ROI")
        roi_btn.clicked.connect(self.roi_setup_requested.emit)
        form.addRow("", roi_btn)
        return tab

    def _build_provider_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()
        layout.addLayout(form)

        self._provider_combo = QComboBox()
        for profile in self._profiles:
            self._provider_combo.addItem(profile.label, profile)
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("Provider", self._provider_combo)

        self._model_edit = QLineEdit()
        form.addRow("Model", self._model_edit)

        self._base_url_edit = QLineEdit()
        form.addRow("Base URL", self._base_url_edit)

        self._api_key_env_edit = QLineEdit()
        form.addRow("API key env", self._api_key_env_edit)

        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("API key", self._api_key_edit)

        self._gateway_token_edit = QLineEdit()
        self._gateway_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Gateway token", self._gateway_token_edit)

        self._profile_notes = QLabel("")
        self._profile_notes.setWordWrap(True)
        form.addRow("Notes", self._profile_notes)

        self._inference_route = QLabel("")
        self._inference_route.setWordWrap(True)
        self._inference_route.setStyleSheet("color: #176b45; font-weight: 600;")
        form.addRow("Inference route", self._inference_route)

        button_row = QHBoxLayout()
        self._save_provider_btn = QPushButton("Save provider")
        self._save_provider_btn.clicked.connect(self._save_provider_profile)
        button_row.addWidget(self._save_provider_btn)

        self._test_image_btn = QPushButton("Test image")
        self._test_image_btn.clicked.connect(self._request_vision_test)
        button_row.addWidget(self._test_image_btn)

        button_row.addStretch()
        layout.addLayout(button_row)
        self._select_initial_provider()
        return tab

    def _select_initial_provider(self) -> None:
        active_model = self._store.load_model_ref().lower()
        active_api = self._store.load_provider_api().lower()
        preferred_index = 0
        for index, profile in enumerate(self._profiles):
            if profile.key == DEFAULT_VISION_PROFILE_KEY:
                preferred_index = index
            if (
                active_model
                and profile.model_ref.lower() == active_model
                and active_api
                and profile.api.lower() == active_api
            ):
                preferred_index = index
                break
            if (
                active_model
                and profile.model_ref.lower() == active_model
                and not active_api
                and profile.key == DEFAULT_VISION_PROFILE_KEY
            ):
                preferred_index = index
        self._provider_combo.setCurrentIndex(preferred_index)

    def _build_analysis_tab(
        self,
        multi_pass_enabled: bool,
        max_zoom_targets: int,
        fast_mode_enabled: bool,
    ) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self._multi_pass_check = QCheckBox("Multi-pass clinical review")
        self._multi_pass_check.setToolTip(
            "Targeted crop verification, layout-derived EKG discovery, and a "
            "localized rhythm-strip re-check from the original capture"
        )
        self._multi_pass_check.setChecked(multi_pass_enabled)
        form.addRow("Multi-pass", self._multi_pass_check)

        self._max_zoom_targets = QSpinBox()
        self._max_zoom_targets.setRange(1, 5)
        self._max_zoom_targets.setValue(max(1, min(5, max_zoom_targets)))
        self._max_zoom_targets.setToolTip(
            "Total crop budget shared by finding verification and discovery probes"
        )
        form.addRow("Pass budget", self._max_zoom_targets)

        self._fast_mode_check = QCheckBox("Priority inference")
        self._fast_mode_check.setChecked(fast_mode_enabled)
        self._fast_mode_check.setToolTip(
            "Requests OpenClaw fast mode for each whole-image and crop turn; "
            "this may consume priority subscription capacity"
        )
        form.addRow("Response speed", self._fast_mode_check)

        waveform_configured = self._store.ecg_founder_configured()
        self._waveform_assist_status = QLabel(
            "Evaluation sidecar configured" if waveform_configured else "Not configured"
        )
        self._waveform_assist_status.setStyleSheet(
            "color: #8a5a00;" if waveform_configured else "color: #666;"
        )
        self._waveform_assist_status.setToolTip(
            "ECGFounder is evaluation-only until the desktop has a trusted "
            "study-to-waveform binding. Configured does not prove sidecar readiness; "
            "screenshot-only reads do not invoke it."
        )
        form.addRow("Waveform assist", self._waveform_assist_status)

        save_btn = QPushButton("Save analysis")
        save_btn.clicked.connect(self._save_analysis_settings)
        form.addRow("", save_btn)
        return tab

    def _on_provider_changed(self) -> None:
        self._load_profile_fields(
            cast("ProviderProfile", self._provider_combo.currentData())
        )

    def _load_profile_fields(self, profile: ProviderProfile) -> None:
        self._model_edit.setText(profile.model)
        self._base_url_edit.setText(profile.base_url)
        self._api_key_env_edit.setText(profile.api_key_env)
        self._profile_notes.setText(profile.notes)
        uses_subscription = profile.auth_mode is ProviderAuthMode.CODEX_SUBSCRIPTION
        self._base_url_edit.setEnabled(not uses_subscription)
        self._api_key_env_edit.setEnabled(not uses_subscription)
        self._api_key_edit.setEnabled(not uses_subscription)
        self._api_key_edit.clear()
        self._api_key_edit.setPlaceholderText(
            "Uses local Codex sign-in" if uses_subscription else ""
        )
        self._inference_route.setText(
            "OpenClaw agent | ChatGPT subscription OAuth"
            if uses_subscription
            else "OpenClaw agent | Provider API key"
        )

    def _save_trigger_mode(self) -> None:
        mode = self.selected_trigger_mode()
        self._store.save_trigger_mode(mode)
        self.trigger_mode_saved.emit(mode)
        QMessageBox.information(self, "Settings", "Trigger mode saved.")

    def _save_analysis_settings(self) -> None:
        enabled = self._multi_pass_check.isChecked()
        max_targets = self._max_zoom_targets.value()
        fast_mode_enabled = self._fast_mode_check.isChecked()
        self._store.save_analysis_settings(
            multi_pass_enabled=enabled,
            max_zoom_targets=max_targets,
            fast_mode_enabled=fast_mode_enabled,
        )
        self.analysis_settings_saved.emit(enabled, max_targets, fast_mode_enabled)
        QMessageBox.information(self, "Settings", "Analysis settings applied.")

    def _save_provider_profile(self) -> None:
        profile = self.selected_profile()
        self._store.save_provider_profile(
            profile,
            api_key=self._api_key_edit.text(),
            gateway_token=self._gateway_token_edit.text(),
        )
        QMessageBox.information(
            self,
            "OpenClaw",
            "Provider settings saved. Restart the gateway to apply them.",
        )

    def _request_vision_test(self) -> None:
        self.vision_test_requested.emit(self.selected_profile())
