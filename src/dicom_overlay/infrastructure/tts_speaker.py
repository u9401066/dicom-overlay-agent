"""Text-to-speech via Windows SAPI."""

from __future__ import annotations

import threading

import structlog

logger = structlog.get_logger(__name__)

_SEVERITY_LABELS = {
    "critical": "critical",
    "warning": "warning",
    "normal": "normal",
    "info": "info",
}

_MODALITY_LABELS = {
    "EKG": "EKG",
    "CXR": "CXR",
    "CT_BRAIN": "CT brain",
    "auto": "image",
}


def speak_result(modality: str, severity: str, summary: str) -> None:
    """Announce analysis result via TTS in a background thread."""
    sev_label = _SEVERITY_LABELS.get(severity, severity)
    mod_label = _MODALITY_LABELS.get(modality, modality)
    text = f"{mod_label} analysis complete. Result: {sev_label}. {summary}"
    _speak_async(text)


def speak_error(message: str) -> None:
    """Announce an error via TTS in a background thread."""
    _speak_async(f"Error: {message}")


def _speak_async(text: str) -> None:
    """Run TTS in a daemon thread to avoid blocking the Qt event loop."""
    t = threading.Thread(target=_speak_sapi, args=(text,), daemon=True)
    t.start()


def _speak_sapi(text: str) -> None:
    """Speak text using Windows SAPI."""
    try:
        import pythoncom  # type: ignore[import-untyped]

        pythoncom.CoInitialize()
        try:
            import win32com.client  # type: ignore[import-untyped]

            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice.Speak(text)
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        logger.warning("TTS failed", exc_info=True)
