"""Private visible-output retention, with synthetic pixels and public Gateway frames."""

from __future__ import annotations

import json
from hashlib import sha256

import pytest

from dicom_overlay.infrastructure.scientific_image_session import ScientificImageSession
from dicom_overlay.infrastructure.scientific_receipts import (
    ScientificReceiptError,
    ScientificReceiptStore,
)
from medical_image_harness.models import Modality
from tests.unit.test_image_evidence_turn import SOURCE, connected
from tests.unit.test_scientific_image_session import StageGateway


@pytest.mark.parametrize(
    "raw",
    [
        ' {"not_quality":"synthetic"} \n',
        '{"large":"' + "合成可見證據" * 5000 + '"}',
        '{"broken":',
    ],
    ids=["whitespace", "long-visible-text", "malformed-json"],
)
async def test_exact_visible_output_survives_failed_decoder_and_session_exit(
    tmp_path, raw
):
    root = tmp_path / "private"
    gateway = StageGateway([raw])
    reader = ScientificImageSession(
        connected(tmp_path, gateway),
        image_bytes=SOURCE,
        modality=Modality.EKG,
        deidentified=True,
        receipt_root=root,
    )
    with pytest.raises(ValueError):
        await reader.read_blind()
    assert len(gateway.sent) == 1
    run_id = reader.records[0].run_id
    del reader
    directory = root / run_id
    assert (directory / "source.png").read_bytes() == SOURCE
    saved = directory / "turn-0001"
    assert (saved / "model-visible.txt").read_bytes() == raw.encode("utf-8")
    receipt = json.loads((saved / "receipt.json").read_bytes())
    assert receipt["model_text_sha256"] == sha256(raw.encode()).hexdigest()
    assert receipt["artifacts"]["model-visible.txt"] == receipt["model_text_sha256"]
    assert receipt["stage"] == "quality_gate" and receipt["terminal_seen"]
    assert receipt["scope"] == "visible_transport_output_before_scientific_validation"
    assert set(receipt).isdisjoint(
        {"auth", "prompt", "thinking", "reasoning", "messages"}
    )


def test_unknown_deidentification_creates_no_files(tmp_path):
    root = tmp_path / "private"
    with pytest.raises(ScientificReceiptError, match="require_deidentified"):
        ScientificReceiptStore(
            root, run_id="a" * 32, image_bytes=SOURCE, deidentified=False
        )
    assert not root.exists()


@pytest.mark.parametrize(
    "run_id", ["../escape", "../" + "a" * 32, "A" * 32, "", "a" * 33]
)
def test_run_id_never_becomes_an_untrusted_path(tmp_path, run_id):
    root = tmp_path / "private"
    with pytest.raises(ScientificReceiptError, match="invalid_run_id"):
        ScientificReceiptStore(
            root, run_id=run_id, image_bytes=SOURCE, deidentified=True
        )
    assert not root.exists()


def test_existing_run_cannot_be_overwritten(tmp_path):
    root = tmp_path / "private"
    store = ScientificReceiptStore(
        root, run_id="a" * 32, image_bytes=SOURCE, deidentified=True
    )
    with pytest.raises(ScientificReceiptError, match="initialization_failed"):
        ScientificReceiptStore(
            root, run_id="a" * 32, image_bytes=b"different", deidentified=True
        )
    assert (store.directory / "source.png").read_bytes() == SOURCE


async def test_write_failure_stops_pipeline_without_next_model_request(
    tmp_path, monkeypatch
):
    gateway = StageGateway(["{}"])
    reader = ScientificImageSession(
        connected(tmp_path, gateway),
        image_bytes=SOURCE,
        modality=Modality.EKG,
        deidentified=True,
        receipt_root=tmp_path / "private",
    )

    def fail_write(*_args):
        raise OSError("synthetic-private-path-do-not-log")

    monkeypatch.setattr(
        "dicom_overlay.infrastructure.scientific_receipts._write", fail_write
    )
    with pytest.raises(
        ScientificReceiptError, match=r"^scientific_receipts_write_failed$"
    ):
        await reader.read_blind()
    assert len(gateway.sent) == 1
    assert reader.records[-1].status == "failed"
    assert list((tmp_path / "private").rglob("receipt.json")) == []
    with pytest.raises(ValueError, match="failed_run_cannot_continue"):
        await reader.read_blind()
    assert len(gateway.sent) == 1


async def test_session_storage_is_opt_in(tmp_path):
    reader = ScientificImageSession(
        connected(tmp_path, StageGateway(["{}"])),
        image_bytes=SOURCE,
        modality=Modality.EKG,
        deidentified=True,
    )
    assert reader._receipt_store is None
    with pytest.raises(ValueError):
        await reader.read_blind()
    assert list(tmp_path.rglob("model-visible.txt")) == []
