"""Actual Qt signal/callback wiring with synthetic, offline model responses."""

from __future__ import annotations

import ast
import asyncio
import base64
import json
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from dicom_overlay.__main__ import _SignalBridge
from dicom_overlay.application.regional_conversation import RegionalConversations
from dicom_overlay.application.regional_history import decode_regional_history
from dicom_overlay.application.review_chat import ReviewChatResponse
from dicom_overlay.domain.entities import AgentState, FindingDelta, FindingOp
from medical_image_harness.models import Finding, Modality, RegionRect, Severity


class _ImmediateBridge:
    def submit(self, coroutine):
        future = Future()
        try:
            future.set_result(asyncio.run(coroutine))
        except Exception as exc:
            future.set_exception(exc)
        return future


@pytest.mark.parametrize(
    "outcome,archived",
    [
        ("no_change", False),
        ("blocked", False),
        ("applied", False),
        ("dismissed", False),
        ("no_change", True),
        ("blocked", True),
    ],
)
def test_same_host_turn_id_crosses_model_reply_qt_signal_history_and_outcome(
    outcome, archived
):
    image = base64.b64encode(b"synthetic pixels").decode()
    crop = base64.b64encode(b"synthetic selected crop pixels").decode()
    region = RegionRect(0.1, 0.2, 0.3, 0.4)
    finding = Finding(
        id="new",
        regions=["user_selected"],
        label="Synthetic observation",
        detail="Synthetic test only",
        severity=Severity.INFO,
        bboxes=[region],
    )
    proposal = outcome in {"applied", "dismissed"}
    response = ReviewChatResponse(
        answer="Synthetic answer",
        delta=FindingDelta(op=FindingOp.ADD, finding=finding) if proposal else None,
        proposal_summary="Add synthetic marker" if proposal else "",
        warning="Synthetic blocked proposal" if outcome == "blocked" else "",
    )
    snapshot = SimpleNamespace(
        image_base64=image, revision=8, result=SimpleNamespace(modality=Modality.EKG)
    )
    agent = Mock(state=AgentState.DISPLAYING, result_revision=8, target_window=None)
    agent.last_image_base64 = base64.b64encode(b"different live image").decode()

    def record(**kwargs):
        agent.result_revision += 1
        snapshot.revision = agent.result_revision
        return snapshot.result

    agent.record_regional_review_outcome.side_effect = record
    signals = _SignalBridge()
    errors = []
    signals.chat_failed.connect(errors.append)
    store = RegionalConversations()
    archive_id = ""
    if archived:
        old = RegionalConversations()
        old.bind(image)
        old.append(
            old.thread(region, "same-id-from-old-report"),
            question="Old question",
            answer="Old answer",
        )
        history = decode_regional_history(
            json.dumps(old.export()).encode(), source_image_sha256=old.image_sha256
        )[0]
        store.bind(image)
        store.restore_archive(history)
        archive_id = history.archive_id
    pending = [None]
    env = {
        "uuid4": uuid4,
        "AgentState": AgentState,
        "agent": agent,
        "signals": signals,
        "bridge": _ImmediateBridge(),
        "regional_conversations": store,
        "_pending_review": pending,
        "_pending_regional_threads": {},
        "_pending_user_region": {},
        "_active_region": [None],
        "_chat_request_id": [1],
        "_begin_chat_request": lambda: 1,
        "_current_review_snapshot": lambda: snapshot,
        "overlay": Mock(),
        "control_bar": Mock(),
        "logger": Mock(),
        "config": SimpleNamespace(
            analysis=SimpleNamespace(multi_pass_enabled=archived)
        ),
        "image_processor": Mock(),
        "openclaw_client": SimpleNamespace(
            refine=AsyncMock(),
            review_region_about_image_with_trace=AsyncMock(
                return_value=("synthetic raw response", {"run_id": "synthetic-run"})
            ),
        ),
        "summarize_result_for_followup": Mock(return_value="synthetic context"),
        "build_region_review_prompt": Mock(return_value="synthetic prompt"),
        "parse_region_review_response": Mock(return_value=response),
    }
    env["image_processor"].image_quality_profile.return_value = {"low_signal": False}
    path = Path(__file__).resolve().parents[2] / "src/dicom_overlay/__main__.py"
    wanted = {
        "_submit_region_review",
        "_show_review_chat_response",
        "_apply_review_proposal",
        "_dismiss_review_proposal",
    }
    nodes = [
        node
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    assert len(nodes) == len(wanted)
    # Inherits postponed annotations from this module; no App startup or OAuth.
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), env)
    signals.review_chat_done.connect(env["_show_review_chat_response"])
    env["_submit_region_review"](
        question="Synthetic question",
        crop_base64=crop,
        source_crop_bytes=b"synthetic crop",
        snapshot=snapshot,
        selected_region=region,
        selected_finding=None,
        allow_add=True,
        archive_id=archive_id,
    )
    assert not errors
    env["build_region_review_prompt"].assert_called_once()
    assert (
        env["build_region_review_prompt"].call_args.kwargs["has_source_context"] is True
    )
    transport = env["openclaw_client"].review_region_about_image_with_trace
    transport.assert_awaited_once_with(
        "synthetic prompt",
        image_base64=crop,
        context_image_base64=snapshot.image_base64,
    )
    if archived:
        env["openclaw_client"].refine.assert_not_awaited()
        assert not store.export()["threads"]
        assert (
            env["build_region_review_prompt"].call_args.kwargs["selected_finding"]
            is None
        )
        assert env["build_region_review_prompt"].call_args.kwargs["allow_add"] is False
        assert (
            "Old answer"
            in env["build_region_review_prompt"].call_args.kwargs["regional_history"]
        )
        assert (
            env["parse_region_review_response"].call_args.kwargs["allow_add"] is False
        )
        assert env["_active_region"][0] == (region, "", False, archive_id)
    collection = "archived_threads" if archived else "threads"
    turn = store.export()[collection][0]["turns"][0]
    turn_id = turn["review_turn_id"]
    assert len(turn_id) == 32
    if outcome == "applied":
        env["_apply_review_proposal"]()
        call = agent.apply_finding_delta.call_args
        agent.record_regional_review_outcome.assert_not_called()
    else:
        if outcome == "dismissed":
            env["_dismiss_review_proposal"]()
        call = agent.record_regional_review_outcome.call_args
        assert call.kwargs["outcome"] == outcome
        agent.apply_finding_delta.assert_not_called()
    assert call.kwargs["review_turn_id"] == turn_id
    trace = call.kwargs["regional_review_trace"]
    assert trace[-1]["run_id"] == "synthetic-run"
    if archived:
        assert trace[0] == {
            "stage": "regional_refine",
            "status": "skipped",
            "reason": "imported_history_qa_only",
        }
    assert pending[0] is None
    assert store.export()[collection][0]["turns"][0] == turn
