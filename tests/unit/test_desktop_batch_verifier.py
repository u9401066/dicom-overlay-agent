from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image


def module():
    path = Path(__file__).resolve().parents[2] / "scripts/verify-desktop-batch.py"
    spec = importlib.util.spec_from_file_location("desktop_batch_verifier", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def evidence(tmp_path):
    m = module()
    run, exports = tmp_path / "run", tmp_path / "exports"
    run.mkdir()
    exports.mkdir()
    rows, records = [], []
    for index in range(2):
        source = tmp_path / f"input-{index}.png"
        Image.new("RGB", (4, 4), (60 + index, 90, 120)).save(source)
        rows.append({"label": f"synthetic-{index}", "image": source.name})
        records.append(
            {"case_identity": rows[-1]["label"], "image_sha256": m.digest(source)}
        )
    manifest = tmp_path / "inference.json"
    write(
        manifest,
        {
            "cases": rows,
            "selection": {"input_image_order_sha256": m.canonical_digest(records)},
        },
    )
    plan = {
        "actual_gui_required": True,
        "gold_read": False,
        "expected_model": "gpt-6-astra",
        "reasoning": "medium",
        "planned_cases": records,
        "bindings": {
            "app_pid": 1,
            "viewer_pid": 2,
            "roi": [30, 30, 4, 4],
            "inference_sha256": m.digest(manifest),
            "input_image_order_sha256": m.canonical_digest(records),
        },
    }
    write(run / "plan.json", plan)
    log = tmp_path / "gateway.log"
    log.write_text(
        "embedded run start: runId=run-a sessionId=session-a "
        "provider=openai model=gpt-6-astra thinking=medium\n",
        encoding="utf-8",
    )
    case_dir, export = run / "case-000", exports / "export-0"
    case_dir.mkdir()
    export.mkdir()
    source_bytes = (tmp_path / "input-0.png").read_bytes()
    (case_dir / "visible-roi.png").write_bytes(source_bytes)
    for name in m.REQUIRED_ARTIFACTS:
        (export / name).write_bytes(source_bytes if name.endswith(".png") else b"{}")
    result = {
        "source_image": {
            "sha256": m.digest(export / "source.png"),
            "width_px": 4,
            "height_px": 4,
        },
        "coordinate_space": "normalized_original_roi",
        "analysis_trace": [
            {"stage": "coarse", "session_key": "analysis-a", "run_id": "run-a"}
        ],
    }
    write(export / "result.json", result)
    usage = {
        "source_result_sha256": m.digest(export / "result.json"),
        "model_requests": 0,
        "source_results_mutated": False,
        "turns": [
            {
                "stage": "coarse",
                "position": "stage",
                "session_key": "agent:main:analysis-a",
                "run_id": "run-a",
                "usage_found": True,
                "public_session_fields": {
                    "sessionId": "session-a",
                    "model": "gpt-6-astra",
                    "modelProvider": "openai",
                    "inputTokens": 4,
                    "outputTokens": 2,
                    "totalTokens": 5,
                    "totalTokensFresh": True,
                },
                "runtime_observation": {
                    "run_id": "run-a",
                    "session_id": "session-a",
                    "model": "gpt-6-astra",
                    "provider": "openai",
                    "reasoning_effort": "medium",
                    "log_line": 1,
                },
            }
        ],
    }
    write(export / "usage-receipt.json", usage)
    write(
        export / "ui-capture.json",
        {
            "method": "app_owned_widget_render",
            "desktop_background_captured": False,
            "capture_exclusion_disabled": False,
        },
    )
    attempt = {
        "index": 0,
        "case_id": "synthetic-0",
        "input_sha256": records[0]["image_sha256"],
        "actual_gui": True,
        "gold_read": False,
        "direct_model_requests": 0,
        "started_utc": "2026-09-24T12:00:00+00:00",
    }
    write(case_dir / "attempt.json", attempt)
    receipt = {
        **attempt,
        "status": "exported_verified",
        "export_dir": str(export),
        "finished_utc": "2026-09-24T12:01:00+00:00",
    }

    def refresh():
        receipt["artifact_sha256"] = {p.name: m.digest(p) for p in export.iterdir()}
        write(case_dir / "receipt.json", receipt)

    refresh()
    kwargs = {
        "run": run,
        "manifest": manifest,
        "exports_root": exports,
        "gateway_log": log,
        "plan_sha256": m.digest(run / "plan.json"),
        "expected_cases": 2,
    }
    return m, kwargs, export, receipt, refresh


def test_partial_is_not_complete_and_does_not_mutate(evidence):
    m, kwargs, export, _, _ = evidence
    before = {p: m.digest(p) for p in export.parent.parent.rglob("*") if p.is_file()}
    report = m.audit(**kwargs)
    assert (report["verified"], report["pending"], report["complete"]) == (1, 1, False)
    assert report["cases"][0]["model_turns"] == 1
    assert report["clinical_scored"] is False
    assert before == {p: m.digest(p) for p in before}


@pytest.mark.parametrize("tamper", ["plan", "manifest", "input", "denominator"])
def test_frozen_inputs_fail_closed(evidence, tamper):
    m, kwargs, export, _, _ = evidence
    if tamper == "plan":
        kwargs["plan_sha256"] = "0" * 64
    elif tamper == "manifest":
        kwargs["manifest"].write_text("{}", encoding="utf-8")
    elif tamper == "input":
        Image.new("RGB", (4, 4), "white").save(export.parent.parent / "input-1.png")
    else:
        kwargs["expected_cases"] = 120
    with pytest.raises(m.AuditError):
        m.audit(**kwargs)


@pytest.mark.parametrize(
    "tamper",
    [
        "artifact",
        "missing",
        "inventory",
        "source_pixels",
        "visible_pixels",
        "export_escape",
        "source_binding",
        "usage_binding",
        "missing_turn",
        "extra_attempt",
        "public_model",
        "unknown_usage",
        "stale_usage",
        "log_effort",
        "log_identity",
        "log_duplicate",
        "recorded_line",
        "case_order",
        "capture",
        "attempt",
    ],
)
def test_receipt_success_does_not_override_evidence(evidence, tamper):
    m, kwargs, export, receipt, refresh = evidence
    if tamper == "artifact":
        (export / "review.png").write_bytes(b"changed")
    elif tamper == "missing":
        (export / "overlay-layer.png").unlink()
        refresh()
    elif tamper == "inventory":
        (export / "unrecorded.json").write_text("{}", encoding="utf-8")
    elif tamper in {"source_pixels", "visible_pixels"}:
        path = (
            export / "source.png"
            if tamper == "source_pixels"
            else kwargs["run"] / "case-000/visible-roi.png"
        )
        Image.new("RGB", (4, 4), "white").save(path)
        refresh()
    elif tamper in {"export_escape", "case_order"}:
        receipt["export_dir" if tamper == "export_escape" else "index"] = (
            str(export.parent.parent) if tamper == "export_escape" else 1
        )
        refresh()
    elif tamper in {"source_binding", "extra_attempt"}:
        value = m.read_json(export / "result.json")
        if tamper == "source_binding":
            value["source_image"]["sha256"] = "wrong"
        else:
            value["analysis_trace"][0]["attempts"] = [
                {"session_key": "retry", "run_id": "run-retry"}
            ]
        write(export / "result.json", value)
        usage = m.read_json(export / "usage-receipt.json")
        usage["source_result_sha256"] = m.digest(export / "result.json")
        write(export / "usage-receipt.json", usage)
        refresh()
    elif tamper in {
        "usage_binding",
        "missing_turn",
        "public_model",
        "unknown_usage",
        "stale_usage",
        "recorded_line",
    }:
        value = m.read_json(export / "usage-receipt.json")
        if tamper == "usage_binding":
            value["source_result_sha256"] = "wrong"
        elif tamper == "missing_turn":
            value["turns"] = []
        elif tamper == "recorded_line":
            value["turns"][0]["runtime_observation"]["log_line"] = 2
        else:
            field, replacement = {
                "public_model": ("model", "other-model"),
                "unknown_usage": ("inputTokens", None),
                "stale_usage": ("totalTokensFresh", False),
            }[tamper]
            value["turns"][0]["public_session_fields"][field] = replacement
        write(export / "usage-receipt.json", value)
        refresh()
    elif tamper.startswith("log_"):
        value = kwargs["gateway_log"].read_text(encoding="utf-8")
        value = {
            "log_effort": value.replace("medium", "low"),
            "log_identity": value.replace("session-a", "session-b"),
            "log_duplicate": value + value,
        }[tamper]
        kwargs["gateway_log"].write_text(value, encoding="utf-8")
    elif tamper == "capture":
        value = m.read_json(export / "ui-capture.json")
        value["desktop_background_captured"] = True
        write(export / "ui-capture.json", value)
        refresh()
    else:
        value = m.read_json(kwargs["run"] / "case-000/attempt.json")
        value["started_utc"] = "2026-09-24T11:00:00+00:00"
        write(kwargs["run"] / "case-000/attempt.json", value)
    report = m.audit(**kwargs)
    assert report["invalid"] == 1 and not report["complete"]


def test_failure_is_preserved_in_denominator(evidence):
    m, kwargs, _, receipt, refresh = evidence
    receipt["status"] = "technical_failure"
    refresh()
    report = m.audit(**kwargs)
    assert (report["planned"], report["technical_failure"], report["pending"]) == (
        2,
        1,
        1,
    )


def test_inflight_attempt_remains_pending(evidence):
    m, kwargs, _, _, _ = evidence
    (kwargs["run"] / "case-001").mkdir()
    write(kwargs["run"] / "case-001/attempt.json", {"started": True})
    assert m.audit(**kwargs)["pending"] == 1


@pytest.mark.parametrize("reuse_session", [False, True])
def test_complete_requires_all_planned_cases(evidence, reuse_session):
    m, kwargs, export, receipt, _ = evidence
    root = export.parent.parent
    target = export.parent / "export-1"
    target.mkdir()
    for source in export.iterdir():
        (target / source.name).write_bytes(source.read_bytes())
    case_dir = kwargs["run"] / "case-001"
    case_dir.mkdir()
    source_bytes = (root / "input-1.png").read_bytes()
    (case_dir / "visible-roi.png").write_bytes(source_bytes)
    (target / "source.png").write_bytes(source_bytes)
    for name in ("result.json", "usage-receipt.json"):
        text = (target / name).read_text(encoding="utf-8")
        (target / name).write_text(
            text.replace("run-a", "run-b")
            .replace("session-a", "session-b")
            .replace("analysis-a", "analysis-b"),
            encoding="utf-8",
        )
    result = m.read_json(target / "result.json")
    result["source_image"]["sha256"] = m.digest(target / "source.png")
    write(target / "result.json", result)
    usage = m.read_json(target / "usage-receipt.json")
    usage["source_result_sha256"] = m.digest(target / "result.json")
    usage["turns"][0]["runtime_observation"]["log_line"] = 2
    write(target / "usage-receipt.json", usage)
    log_text = kwargs["gateway_log"].read_text(encoding="utf-8")
    kwargs["gateway_log"].write_text(
        log_text + log_text.replace("run-a", "run-b").replace("session-a", "session-b"),
        encoding="utf-8",
    )
    if reuse_session:
        usage["turns"][0]["public_session_fields"]["sessionId"] = "session-a"
        usage["turns"][0]["runtime_observation"]["session_id"] = "session-a"
        write(target / "usage-receipt.json", usage)
        kwargs["gateway_log"].write_text(
            log_text + log_text.replace("run-a", "run-b"), encoding="utf-8"
        )
    attempt = {
        **m.read_json(kwargs["run"] / "case-000/attempt.json"),
        "index": 1,
        "case_id": "synthetic-1",
        "input_sha256": m.digest(root / "input-1.png"),
        "started_utc": "2026-09-24T12:02:00+00:00",
    }
    write(case_dir / "attempt.json", attempt)
    write(
        case_dir / "receipt.json",
        {
            **receipt,
            **attempt,
            "finished_utc": "2026-09-24T12:03:00+00:00",
            "export_dir": str(target),
            "artifact_sha256": {p.name: m.digest(p) for p in target.iterdir()},
        },
    )
    report = m.audit(**kwargs)
    if reuse_session:
        assert report["invalid"] == 1 and report["verified"] == 1
        assert "session reused" in report["cases"][1]["error"]
        return
    assert report["complete"] and report["verified"] == 2
    assert report["clinical_scored"] is False
    # A terminal result cannot jump over an unresolved earlier input.
    (kwargs["run"] / "case-000/receipt.json").unlink()
    report = m.audit(**kwargs)
    assert (report["pending"], report["invalid"], report["verified"]) == (1, 1, 0)


def test_masked_identity_requires_one_exact_identity():
    m = module()
    run, session = "1234567890123456-run", "1234567890123456-session"
    prefix = "1234567890123456***"
    assert m.identity_matches(run, session, run, prefix)
    assert m.identity_matches(run, session, prefix, session)
    assert not m.identity_matches(run, session, prefix, prefix)
    assert not m.identity_matches(run, session, "123***", session)


@pytest.mark.parametrize(
    "partial,failed,expected", [(False, False, 1), (True, False, 0), (True, True, 1)]
)
def test_cli_partial_cannot_hide_failures(monkeypatch, partial, failed, expected):
    m = module()
    monkeypatch.setattr(
        m,
        "audit",
        lambda *a, **k: {
            "complete": False,
            "invalid": int(failed),
            "technical_failure": 0,
        },
    )
    argv = [
        "--run",
        "run",
        "--manifest",
        "inference",
        "--exports-root",
        "exports",
        "--gateway-log",
        "gateway",
        "--plan-sha256",
        "digest",
    ]
    if partial:
        argv.append("--allow-partial")
    assert m.main(argv) == expected
