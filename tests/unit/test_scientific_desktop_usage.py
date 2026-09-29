"""Scientific usage is bound to retained turns, not the thin legacy projection."""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from dicom_overlay.application.contract_assembly import assemble_review_contract
from tests.unit.test_contract_assembly import inputs as inputs


@pytest.fixture
def usage():
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts/collect-scientific-desktop-usage.py"
    )
    spec = importlib.util.spec_from_file_location("scientific_usage", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    turns, sessions, lines = [], [], []
    for index, stage in enumerate(module.STAGES):
        turns.append(
            {
                "stage": stage,
                "session_key": f"key-{index}",
                "gateway_run_id": f"run-{index}",
                "model_text_sha256": "a" * 64,
                "terminal_seen": True,
                "transport_failure": "",
            }
        )
        sessions.append(
            {
                "key": f"key-{index}",
                "sessionId": f"session-{index}",
                "model": "gpt-6-astra",
                "modelProvider": "openai",
                "totalTokensFresh": True,
                "inputTokens": 10,
                "outputTokens": 2,
                "totalTokens": 12,
            }
        )
        lines.append(
            f"embedded run start: runId=run-{index} sessionId=session-{index} "
            "provider=openai model=gpt-6-astra thinking=medium"
        )
    return module, turns, sessions, lines


def test_all_scientific_turns_bind_without_mutating_or_reading_legacy_trace(usage):
    module, turns, sessions, lines = usage
    before = deepcopy((turns, sessions, lines))
    result = module.bind_usage(turns, sessions, "\n".join(lines))
    assert [r["stage"] for r in result] == list(module.STAGES)
    assert len(result) == 5
    assert (turns, sessions, lines) == before


@pytest.mark.parametrize(
    "tamper",
    [
        "missing_turn",
        "extra_turn",
        "wrong_order",
        "reused_session",
        "reused_run",
        "not_terminal",
        "transport_error",
        "no_public",
        "duplicate_public",
        "wrong_model",
        "wrong_provider",
        "stale",
        "unknown_tokens",
        "boolean_tokens",
        "negative_tokens",
        "missing_runtime",
        "duplicate_runtime",
        "wrong_effort",
        "wrong_identity",
    ],
)
def test_incomplete_or_ambiguous_usage_is_not_success(usage, tamper):
    module, turns, sessions, lines = usage
    if tamper == "missing_turn":
        turns.pop()
    elif tamper == "extra_turn":
        turns.append(deepcopy(turns[-1]))
    elif tamper == "wrong_order":
        turns.reverse()
    elif tamper == "reused_session":
        turns[1]["session_key"] = turns[0]["session_key"]
    elif tamper == "reused_run":
        turns[1]["gateway_run_id"] = turns[0]["gateway_run_id"]
    elif tamper == "not_terminal":
        turns[0]["terminal_seen"] = False
    elif tamper == "transport_error":
        turns[0]["transport_failure"] = "synthetic"
    elif tamper == "no_public":
        sessions.pop()
    elif tamper == "duplicate_public":
        sessions.append(deepcopy(sessions[0]))
    elif tamper == "wrong_model":
        sessions[0]["model"] = "other"
    elif tamper == "wrong_provider":
        sessions[0]["modelProvider"] = "other"
    elif tamper == "stale":
        sessions[0]["totalTokensFresh"] = False
    elif tamper == "unknown_tokens":
        sessions[0]["totalTokens"] = None
    elif tamper == "boolean_tokens":
        sessions[0]["inputTokens"] = True
    elif tamper == "negative_tokens":
        sessions[0]["outputTokens"] = -1
    elif tamper == "missing_runtime":
        lines.pop()
    elif tamper == "duplicate_runtime":
        lines.append(lines[0])
    elif tamper == "wrong_effort":
        lines[0] = lines[0].replace("thinking=medium", "thinking=low")
    elif tamper == "wrong_identity":
        lines[0] = lines[0].replace("session-0", "unrelated")
    with pytest.raises(ValueError):
        module.bind_usage(turns, sessions, "\n".join(lines))


@pytest.fixture
def retained(usage, inputs, tmp_path):
    module, turns, _, _ = usage
    draft, host = inputs
    # Opaque synthetic source bytes are sufficient for this identity-only unit
    # fixture; rendered PNG identity is independently checked by the GUI driver.
    source = host["asset_bytes"]["image-1"]
    live = tmp_path / "runtime"
    export = live / "data/exports/example"
    export.mkdir(parents=True)
    (export / "source.png").write_bytes(source)
    source_sha = module.digest(export / "source.png")
    run_id = "b" * 32
    canonical = assemble_review_contract(draft, **host).to_contract_payload()
    for event in canonical["analysis_trace"]:
        event["detail"] = (
            f"Host operation_returned; run={run_id}; source_sha256={source_sha};"
        )

    def write(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    write(export / "scientific-result.json", canonical)
    write(
        export / "result.json",
        {
            "scientific_contract": "scientific-result.json",
            "source_image": {"sha256": source_sha},
        },
    )
    attempt = live / "data/scientific-attempts" / run_id
    attempt.mkdir(parents=True)
    (attempt / "source.png").write_bytes(source)
    write(
        attempt / "intake.json", {"run_id": run_id, "source_image_sha256": source_sha}
    )
    for index, original in enumerate(turns, 1):
        folder = attempt / f"turn-{index:04d}"
        folder.mkdir()
        (folder / "model-visible.txt").write_bytes(b"synthetic response")
        text_sha = module.digest(folder / "model-visible.txt")
        write(
            folder / "receipt.json",
            {
                **original,
                "sequence": index,
                "image_sha256": source_sha,
                "model_text_sha256": text_sha,
                "artifacts": {"model-visible.txt": text_sha},
            },
        )
    return module, export, live, attempt, write


def test_retained_contract_source_and_turns_bind_read_only(retained):
    module, export, live, _, _ = retained
    before = {p: module.digest(p) for p in live.rglob("*") if p.is_file()}
    turns, binding = module.inspect_export(export, live)
    assert len(turns) == 5
    assert binding["source_image_sha256"] == module.digest(export / "source.png")
    assert before == {p: module.digest(p) for p in before}


@pytest.mark.parametrize(
    "tamper",
    [
        "bad_contract",
        "source",
        "attempt_source",
        "projection",
        "intake",
        "missing_host",
        "mixed_host",
        "turn_source",
        "sequence",
        "text",
        "artifact_escape",
        "missing_receipt",
        "extra_artifact",
    ],
)
def test_retained_identity_or_inventory_tamper_fails(retained, tamper):
    module, export, live, attempt, write = retained
    path = attempt / "turn-0001/receipt.json"
    turn = module.read(path)
    if tamper == "bad_contract":
        write(export / "scientific-result.json", {})
    elif tamper == "source":
        (export / "source.png").write_bytes(b"changed")
    elif tamper == "attempt_source":
        (attempt / "source.png").write_bytes(b"changed")
    elif tamper == "projection":
        write(export / "result.json", {"scientific_contract": "other.json"})
    elif tamper == "intake":
        write(attempt / "intake.json", {"run_id": "c" * 32})
    elif tamper in {"missing_host", "mixed_host"}:
        canonical = module.read(export / "scientific-result.json")
        canonical["analysis_trace"][0]["detail"] = (
            "missing"
            if tamper == "missing_host"
            else canonical["analysis_trace"][0]["detail"].replace("b" * 32, "c" * 32)
        )
        write(export / "scientific-result.json", canonical)
    elif tamper == "turn_source":
        turn["image_sha256"] = "c" * 64
    elif tamper == "sequence":
        turn["sequence"] = 2
    elif tamper == "text":
        (path.parent / "model-visible.txt").write_bytes(b"changed")
    elif tamper == "artifact_escape":
        turn["artifacts"] = {"../escape": "c" * 64}
    elif tamper == "missing_receipt":
        (attempt / "turn-0006").mkdir()
    elif tamper == "extra_artifact":
        (path.parent / "unrecorded.txt").write_bytes(b"unrecorded")
    write(path, turn)
    with pytest.raises((ValueError, KeyError)):
        module.inspect_export(export, live)
