"""Actual agent/scientific workflow; synthetic capture, Gateway and reviewer."""

from __future__ import annotations

import ast
import asyncio
import base64
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from dicom_overlay.__main__ import _scientific_mode_requested
from dicom_overlay.domain.entities import AgentState, AppConfig, FindingDelta, FindingOp
from dicom_overlay.infrastructure.desktop_review_exporter import export_desktop_review
from dicom_overlay.infrastructure.openclaw_client import OpenClawClient
from dicom_overlay.infrastructure.scientific_desktop_reader import (
    ScientificDesktopReader,
)
from dicom_overlay.infrastructure.screen_monitor import ImageProcessor
from tests.unit.test_contract_assembly import inputs as inputs
from tests.unit.test_image_evidence_turn import SOURCE, picture
from tests.unit.test_image_publication_guard import _agent
from tests.unit.test_scientific_draft import draft_request as draft_request
from tests.unit.test_scientific_image_session import replies as replies
from tests.unit.test_scientific_review_handoff import receipt, setup


def main_client(tmp_path, *, enabled):
    """Use the real main construction, not a fixture that enables missing options."""
    path = Path(__file__).resolve().parents[2] / "src/dicom_overlay/__main__.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    construction = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "openclaw_client"
            for target in node.targets
        )
    )
    config = AppConfig()
    config.openclaw.inference_timeout_sec = 1
    environment = {
        "config": config,
        "gateway_token": "synthetic-token",
        "registry": None,
        "base_dir": tmp_path,
        "scientific_mode": enabled,
        "OpenClawClient": OpenClawClient,
    }
    exec(
        compile(ast.Module(body=[construction], type_ignores=[]), str(path), "exec"),
        environment,
    )
    return environment["openclaw_client"]


@pytest.mark.parametrize("enabled", [False, True])
def test_main_client_evidence_collection_matches_scientific_mode(tmp_path, enabled):
    assert main_client(tmp_path, enabled=enabled)._collect_transport_evidence is enabled


def configured(tmp_path, replies):
    agent, monitor, legacy, _processor = _agent()
    monitor.screenshot = SOURCE
    agent._processor = ImageProcessor()
    _unused, gateway = setup(tmp_path, replies)
    client = main_client(tmp_path, enabled=True)
    client._ws = gateway
    client._connected = True
    client._gateway_protocol = 4
    readers, published = [], []

    def factory(raw, modality):
        reader = ScientificDesktopReader(
            client, image_bytes=raw, modality=modality, deidentified=True
        )
        readers.append(reader)
        return reader

    agent._scientific_reader_factory = factory
    agent.on_analysis_result = published.append

    async def presenter(run_id, prepared):
        assert agent.state is AgentState.ANALYZING
        assert agent.displayed_review_snapshot is None  # Export/QA remain blocked.
        source = prepared.result.input_provenance.source_image_sha256
        assert agent.scientific_review_is_current(run_id, source)
        return json.dumps(receipt(run_id, prepared)).encode()

    agent.on_scientific_review = presenter
    return agent, monitor, legacy, gateway, readers, published


async def analyze(agent):
    await agent.start()
    await agent.tick()
    await agent.trigger_manual()


def changed_pixels():
    """Change actual content, not just PNG/JPEG encoding of identical white pixels."""
    with Image.open(io.BytesIO(SOURCE)) as source:
        changed = source.convert("RGB")
    changed.putpixel((0, 0), (0, 0, 0))
    buffer = io.BytesIO()
    changed.save(buffer, format="PNG")
    changed.close()
    return buffer.getvalue()


async def test_agent_publishes_only_after_handoff_and_second_pixel_recheck(
    tmp_path, replies
):
    agent, monitor, legacy, gateway, readers, published = configured(tmp_path, replies)
    await analyze(agent)
    assert agent.state is AgentState.DISPLAYING
    assert legacy.analyze_calls == 0 and len(gateway.sent) == 5
    assert len(monitor.capture_rects) == 3
    assert (
        len(published) == 1 and agent.displayed_review_snapshot.result is published[0]
    )
    payload = published[0].to_contract_payload()
    assert len(payload["analysis_trace"]) == 8 and payload["review_required"]
    assert readers[0].session.final_result.to_contract_payload() == payload
    assert agent._scientific_scope is None
    exported = export_desktop_review(
        image_base64=agent.last_image_base64,
        result=published[0],
        output_root=tmp_path / "exports",
    ).parent
    assert json.loads((exported / "scientific-result.json").read_text()) == payload
    metadata = json.loads((exported / "result.json").read_text())
    assert metadata["scientific_contract_scope"].startswith("analysis_ledger_only")


@pytest.mark.parametrize("when", ["before_preview", "during_preview"])
async def test_same_window_changed_pixels_never_publish_scientific_result(
    tmp_path, replies, when
):
    agent, monitor, legacy, gateway, readers, published = configured(tmp_path, replies)
    shown = []
    original_present = agent.on_scientific_review
    original_factory = agent._scientific_reader_factory

    def factory(raw, modality):
        reader = original_factory(raw, modality)
        prepare = reader.prepare

        async def changed_prepare():
            prepared = await prepare()
            if when == "before_preview":
                monitor.screenshot = changed_pixels()
            return prepared

        reader.prepare = changed_prepare
        return reader

    async def presenter(run_id, prepared):
        shown.append(run_id)
        raw = await original_present(run_id, prepared)
        monitor.screenshot = changed_pixels()
        return raw

    agent._scientific_reader_factory = factory
    agent.on_scientific_review = presenter
    await analyze(agent)
    assert not published and agent.displayed_review_snapshot is None
    assert agent.last_result is None and agent.last_image_base64 == ""
    assert agent.last_withheld_review.reason == "image_changed_during_analysis"
    assert len(shown) == (0 if when == "before_preview" else 1)
    assert len(readers[0].session.records) == (7 if when == "before_preview" else 8)
    assert len(gateway.sent) == 5 and legacy.analyze_calls == 0


@pytest.mark.parametrize(
    "failure", ["closed", "pause", "exception", "bad_receipt", "changed_content"]
)
async def test_review_failure_has_no_publication_or_legacy_fallback(
    tmp_path, replies, failure
):
    agent, _monitor, legacy, gateway, readers, published = configured(tmp_path, replies)
    original = agent.on_scientific_review

    async def presenter(run_id, prepared):
        raw = await original(run_id, prepared)
        if failure == "closed":
            agent.invalidate_scientific_review(run_id)
        elif failure == "pause":
            agent.pause()
        elif failure == "exception":
            raise RuntimeError("synthetic presentation unavailable")
        elif failure == "bad_receipt":
            raw = b"{}"
        else:
            readers[0].session._second_look.decoded.draft.summary += " changed"
        return raw

    agent.on_scientific_review = presenter
    await analyze(agent)
    assert not published and agent.displayed_review_snapshot is None
    assert agent.last_result is None and agent._scientific_scope is None
    assert len(gateway.sent) == 5 and legacy.analyze_calls == 0


async def test_missing_presenter_fails_before_any_inference(tmp_path, replies):
    agent, _monitor, legacy, gateway, readers, published = configured(tmp_path, replies)
    agent.on_scientific_review = None
    await analyze(agent)
    assert not readers and not gateway.sent and not published
    assert legacy.analyze_calls == 0


@pytest.mark.parametrize("failure", [TimeoutError, ConnectionError, ValueError])
async def test_failed_scientific_attempt_is_manual_retry_only(
    tmp_path, replies, failure
):
    agent, _monitor, legacy, gateway, readers, published = configured(tmp_path, replies)
    errors = []
    agent.on_error = errors.append
    factory = agent._scientific_reader_factory

    def failing_factory(raw, modality):
        reader = factory(raw, modality)

        async def fail():
            raise failure("synthetic failure")

        reader.prepare = fail
        return reader

    agent._scientific_reader_factory = failing_factory
    await analyze(agent)
    await agent.tick()
    assert len(readers) == 1 and not gateway.sent and not published
    assert legacy.analyze_calls == 0 and agent.pending_analysis
    assert agent.state is AgentState.MONITORING
    assert agent.last_result is None and agent.displayed_review_snapshot is None
    assert len(errors) == 1 and "未發布結果" in errors[0]
    assert "影像已變更" not in errors[0]


async def test_non_diagnostic_quality_makes_one_request_and_no_fake_normal_report(
    tmp_path, replies
):
    replies[0]["adequacy"] = "non_diagnostic"
    agent, _monitor, legacy, gateway, readers, published = configured(tmp_path, replies)
    errors = []
    agent.on_error = errors.append
    await analyze(agent)
    assert len(gateway.sent) == 1 and legacy.analyze_calls == 0
    assert not published and agent.last_result is None
    assert readers[0].session.quality["adequacy"] == "non_diagnostic"
    assert len(errors) == 1 and "影像品質不足" in errors[0]


async def test_pending_presentation_cancellation_and_duplicate_click_do_not_repeat_calls(
    tmp_path, replies
):
    agent, _monitor, legacy, gateway, _readers, published = configured(
        tmp_path, replies
    )
    entered = asyncio.Event()

    async def presenter(*_args):
        entered.set()
        await asyncio.Event().wait()

    agent.on_scientific_review = presenter
    await agent.start()
    await agent.tick()
    pending = asyncio.create_task(agent.trigger_manual())
    await asyncio.wait_for(entered.wait(), 3)
    await agent.trigger_manual()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert len(gateway.sent) == 5 and legacy.analyze_calls == 0
    assert not published and agent.displayed_review_snapshot is None


async def test_regional_edit_preserves_review_but_revokes_canonical_ledger_claim(
    tmp_path, replies
):
    agent, _monitor, _legacy, _gateway, readers, published = configured(
        tmp_path, replies
    )
    await analyze(agent)
    original = published[0]
    finding = original.findings[0]
    # A no-box scientific finding cannot be rewritten without selected geometry;
    # retraction is an explicit reviewer action and requires no invented box.
    revised = agent.apply_finding_delta(
        FindingDelta(FindingOp.RETRACT, finding),
        expected_revision=agent.result_revision,
        local_signal_audit={"status": "ok", "low_signal": False},
    )
    assert not revised.workflow_events
    assert readers[0].session.final_result.workflow_events
    with pytest.raises(ValueError):
        revised.to_contract_payload()
    exported = export_desktop_review(
        image_base64=agent.last_image_base64,
        result=revised,
        output_root=tmp_path / "edited",
    ).parent
    assert not (exported / "scientific-result.json").exists()
    assert json.loads((exported / "result.json").read_text())[
        "scientific_contract_status"
    ].startswith("requires_reconciliation")


async def test_export_rejects_wrong_source_before_creating_files(tmp_path, replies):
    agent, _monitor, _legacy, _gateway, _readers, published = configured(
        tmp_path, replies
    )
    await analyze(agent)
    output = tmp_path / "invalid-export"
    with pytest.raises(ValueError, match="scientific_export_contract_invalid"):
        export_desktop_review(
            image_base64=base64.b64encode(picture("JPEG")).decode(),
            result=published[0],
            output_root=output,
        )
    assert not output.exists()


@pytest.mark.parametrize(
    "args,enabled",
    [([], False), (["--scientific-review", "--deidentified-input"], True)],
)
def test_scientific_mode_requires_explicit_source_assertion(args, enabled):
    assert _scientific_mode_requested(args) is enabled


@pytest.mark.parametrize("arg", ["--scientific-review", "--deidentified-input"])
def test_partial_scientific_flags_do_not_silently_enable_or_ignore(arg):
    with pytest.raises(ValueError, match="explicit_deidentified_input"):
        _scientific_mode_requested([arg])
