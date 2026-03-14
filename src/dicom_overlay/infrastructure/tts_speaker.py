"""Text-to-Speech via Windows SAPI (presentation-layer feedback utility)."""

from __future__ import annotations

import threading

import structlog

logger = structlog.get_logger(__name__)

_SEVERITY_LABELS = {
    "critical": "危急",
    "warning": "警示",
    "normal": "正常",
    "info": "資訊",
}

_MODALITY_LABELS = {
    "EKG": "心電圖",
    "CXR": "胸部X光",
    "CT_BRAIN": "腦部電腦斷層",
    "auto": "自動",
}


def speak_result(modality: str, severity: str, summary: str) -> None:
    """Announce analysis result via TTS in a background thread."""
    sev_label = _SEVERITY_LABELS.get(severity, severity)
    mod_label = _MODALITY_LABELS.get(modality, modality)
    text = f"{mod_label} 判讀完成。結果：{sev_label}。{summary}"
    _speak_async(text)


def speak_error(message: str) -> None:
    """Announce an error via TTS in a background thread."""
    _speak_async(f"判讀失敗。{message}")


def _speak_async(text: str) -> None:
    """Run TTS in a daemon thread to avoid blocking the Qt event loop."""
    t = threading.Thread(target=_speak_sapi, args=(text,), daemon=True)
    t.start()


def _speak_sapi(text: str) -> None:
    """Speak text using Windows SAPI."""
    try:
        import pythoncom
        pythoncom.CoInitialize()
        try:
            import win32com.client
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice.Speak(text)
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        logger.warning("TTS failed", exc_info=True)
