"""Compatibility exports for the public modality-profile registry."""

from medical_image_harness.profiles import (
    ModalityProfile,
    ModalityRegistry,
    build_registry,
    default_registry,
    get_active_registry,
    set_active_registry,
)

__all__ = [
    "ModalityProfile",
    "ModalityRegistry",
    "build_registry",
    "default_registry",
    "get_active_registry",
    "set_active_registry",
]
