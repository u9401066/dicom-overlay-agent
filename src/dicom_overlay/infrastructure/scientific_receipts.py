"""Private, append-only visible scientific attempt artifacts, never global logs.

This store is opt-in for trusted de-identified inputs. Files inherit the local
directory's access permissions; they are not encrypted, clinical exports, signed
attestations, or complete wire transcripts. No auth, prompts or reasoning stream
is accepted. Keep the directory out of source control and release archives.
"""

from __future__ import annotations

import json
import os
import re
from hashlib import sha256
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from dicom_overlay.infrastructure.gateway_evidence import ImageEvidenceTurn


class ScientificReceiptError(ValueError):
    """Fixed categories, without private paths or exception text."""


def _write(path: Path, raw: bytes) -> str:
    # Exclusive creation: existing attempts cannot be overwritten on retry.
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return sha256(raw).hexdigest()


def _json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True
    ).encode("utf-8")


class ScientificReceiptStore:
    """Persist exact decoded visible bytes before any scientific decoder runs."""

    def __init__(
        self, root: Path, *, run_id: str, image_bytes: bytes, deidentified: bool
    ) -> None:
        if deidentified is not True:
            raise ScientificReceiptError(
                "scientific_receipts_require_deidentified_input"
            )
        if re.fullmatch(r"[0-9a-f]{32}", run_id) is None:
            raise ScientificReceiptError("scientific_receipts_invalid_run_id")
        self.directory = root / run_id
        self._sequence = 0
        self._failed = False
        try:
            root.mkdir(parents=True, exist_ok=True)
            self.directory.mkdir()  # Existing run directories are immutable.
            source_hash = _write(self.directory / "source.png", image_bytes)
            _write(
                self.directory / "intake.json",
                _json(
                    {
                        "receipt_version": "1",
                        "run_id": run_id,
                        "source_image_sha256": source_hash,
                        "deidentified_asserted": True,
                        "scope": "private_visible_attempt_evidence_not_clinical_acceptance",
                    }
                ),
            )
        except OSError:
            raise ScientificReceiptError(
                "scientific_receipts_initialization_failed"
            ) from None

    def save_turn(self, stage: str, turn: ImageEvidenceTurn) -> None:
        if self._failed:
            raise ScientificReceiptError("scientific_receipts_failed_store")
        self._sequence += 1
        directory = self.directory / f"turn-{self._sequence:04d}"
        gateway = turn.gateway
        try:
            directory.mkdir()
            hashes = {}
            if gateway.model_text_bytes is not None:
                hashes["model-visible.txt"] = _write(
                    directory / "model-visible.txt", gateway.model_text_bytes
                )
            for index, tool in enumerate(gateway.native_tools, 1):
                name = f"native-tool-{index:04d}-visible.txt"
                hashes[name] = _write(directory / name, tool.text_bytes)
            for index, audit in enumerate(turn.native_bbox_audit_json, 1):
                name = f"native-bbox-{index:04d}.json"
                hashes[name] = _write(directory / name, audit)
            # Commit marker written last. Missing receipt.json means an incomplete
            # write, not a saved turn. Partial artifacts remain for local diagnosis.
            _write(
                directory / "receipt.json",
                _json(
                    {
                        "receipt_version": "1",
                        "stage": stage,
                        "sequence": self._sequence,
                        "image_sha256": turn.image_sha256,
                        "prompt_sha256": turn.prompt_sha256,
                        "elapsed_ms": turn.elapsed_ms,
                        "request_id": gateway.request_id,
                        "session_key": gateway.session_key,
                        "gateway_run_id": gateway.run_id,
                        "terminal_seen": gateway.terminal_seen,
                        "transport_failure": gateway.failure,
                        "model_text_sha256": gateway.model_text_sha256,
                        "tool_event_seen": gateway.tool_event_seen,
                        "non_bbox_tool_event_seen": gateway.non_bbox_tool_event_seen,
                        "bbox_tool_call_ids": gateway.bbox_tool_call_ids,
                        "unbound_bbox_event_seen": gateway.unbound_bbox_event_seen,
                        "native_tools": [
                            {
                                "tool_call_id": tool.tool_call_id,
                                "tool_name": tool.tool_name,
                                "text_sha256": tool.text_sha256,
                            }
                            for tool in gateway.native_tools
                        ],
                        "artifacts": hashes,
                        "scope": "visible_transport_output_before_scientific_validation",
                    }
                ),
            )
        except OSError:
            self._failed = True
            raise ScientificReceiptError("scientific_receipts_write_failed") from None
