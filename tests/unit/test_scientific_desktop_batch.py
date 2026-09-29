"""Synthetic retained-evidence tampering tests; no desktop, models or clinical gold."""

from __future__ import annotations

import hashlib
import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

from tests.unit.test_scientific_desktop_usage import inputs as inputs
from tests.unit.test_scientific_desktop_usage import retained as retained
from tests.unit.test_scientific_desktop_usage import usage as usage


@pytest.fixture
def verifier():
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts/verify-scientific-desktop-batch.py"
    )
    spec = importlib.util.spec_from_file_location("scientific_batch", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture
def evidence(verifier, retained, usage, tmp_path):
    collector, export, live, attempt, write = retained
    _, _, sessions, lines = usage
    old_sha = collector.digest(export / "source.png")
    Image.new("RGB", (32, 24), "white").save(export / "source.png")
    new_sha = collector.digest(export / "source.png")
    (attempt / "source.png").write_bytes((export / "source.png").read_bytes())
    for path in live.rglob("*.json"):
        path.write_text(
            path.read_text("utf-8").replace(old_sha, new_sha), encoding="utf-8"
        )
    projection = collector.read(export / "result.json")
    projection["source_image"].update(width_px=32, height_px=24)
    projection["coordinate_space"] = "normalized_original_roi"
    write(export / "result.json", projection)
    write(
        export / "ui-capture.json",
        {
            "method": "app_owned_widget_render",
            "desktop_background_captured": False,
            "capture_exclusion_disabled": False,
        },
    )
    for name in verifier.REQUIRED - {p.name for p in export.iterdir()}:
        (export / name).write_bytes(b"synthetic artifact")
    (export / "crops").mkdir()
    (export / "crops/local.png").write_bytes(b"synthetic crop")
    log = "\n".join(lines).encode()
    (live / "gateway.log").write_bytes(log)
    turns, binding = collector.inspect_export(export, live)
    record = dict(
        receipt_version="scientific-desktop-usage-v1",
        collector_sha256="c" * 64,
        gateway_log_prefix_bytes=len(log),
        gateway_log_prefix_sha256=hashlib.sha256(log).hexdigest(),
        **binding,
        turns=collector.bind_usage(turns, sessions, log.decode()),
        model_requests=0,
        source_results_mutated=False,
        all_turns_verified_astra_medium=True,
        source_export_sha256=verifier.inventory(export),
    )
    receipt = tmp_path / "usage.json"
    write(receipt, record)
    return verifier, export, live, attempt, receipt, write


def verify(evidence):
    v, export, live, _, receipt, _ = evidence
    return v.verify_usage(export, live, receipt, v.digest(receipt), "c" * 64)


def test_valid_usage_is_read_only_and_log_may_grow(evidence):
    v, _, live, _, _, _ = evidence
    before = v.inventory(live)
    assert len(verify(evidence)["turns"]) == 5
    assert v.inventory(live) == before
    with (live / "gateway.log").open("ab") as stream:
        stream.write(b"\nnext live case starts")
    assert len(verify(evidence)["turns"]) == 5


@pytest.mark.parametrize(
    "tamper",
    [
        "crop",
        "extra_file",
        "missing_file",
        "turn_text",
        "log",
        "log_truncated",
        "prefix_size",
        "collector",
        "model",
        "profile_flag",
        "receipt_hash",
        "recorded_binding",
        "recorded_turn",
        "mutated",
        "model_request",
    ],
)
def test_usage_tampering_fails(evidence, tamper):
    v, export, live, attempt, receipt, write = evidence
    record = v.read(receipt)
    if tamper == "crop":
        (export / "crops/local.png").write_bytes(b"changed")
    elif tamper == "extra_file":
        (export / "unrecorded").write_bytes(b"extra")
    elif tamper == "missing_file":
        (export / "review.png").unlink()
    elif tamper == "turn_text":
        (attempt / "turn-0001/model-visible.txt").write_bytes(b"changed")
    elif tamper == "log":
        (live / "gateway.log").write_bytes(
            b"X" + (live / "gateway.log").read_bytes()[1:]
        )
    elif tamper == "log_truncated":
        (live / "gateway.log").write_bytes(b"short")
    elif tamper == "prefix_size":
        record["gateway_log_prefix_bytes"] = True
    elif tamper == "collector":
        record["collector_sha256"] = "d" * 64
    elif tamper == "model":
        record["turns"][0]["public_session_fields"]["model"] = "other"
    elif tamper == "profile_flag":
        record["all_turns_verified_astra_medium"] = False
    elif tamper == "recorded_binding":
        record["host_run_id"] = "d" * 32
    elif tamper == "recorded_turn":
        record["turns"][0]["runtime_observation"]["log_line"] = 99
    elif tamper == "mutated":
        record["source_results_mutated"] = True
    elif tamper == "model_request":
        record["model_requests"] = 1
    write(receipt, record)
    with pytest.raises((ValueError, OSError)):
        if tamper == "receipt_hash":
            v.verify_usage(export, live, receipt, "0" * 64, "c" * 64)
        else:
            verify(evidence)


@pytest.fixture
def case(evidence, tmp_path):
    v, export, live, _, usage_path, write = evidence
    folder = tmp_path / "run/case-000"
    folder.mkdir(parents=True)
    (folder / "visible-roi.png").write_bytes((export / "source.png").read_bytes())
    source = tmp_path / "input.png"
    source.write_bytes((export / "source.png").read_bytes())
    record = {
        "index": 0,
        "case_id": "synthetic",
        "started_utc": "2026-09-29T11:00:00+00:00",
        "input_sha256": v.digest(source),
        "actual_gui": True,
        "gold_read": False,
        "direct_model_requests": 0,
    }
    write(folder / "attempt.json", record)
    record.update(
        finished_utc="2026-09-29T11:01:00+00:00",
        status="technical_failure",
        error=v.RECOVERY_ERROR,
        export_dir=str(export),
        scientific_contract_sha256=v.digest(export / "scientific-result.json"),
        file_to_visible_bilinear_mae=0.0,
        visible_to_export_mae=0.0,
    )
    write(folder / "receipt.json", record)
    plan = {
        "planned_cases": [{"image_sha256": v.digest(source)}],
        "retained_case0_failure_sha256": v.digest(folder / "receipt.json"),
        "case0_usage_recovery_sha256": v.digest(usage_path),
        "bindings": {"collector_sha256": "c" * 64, "roi": [0, 0, 32, 24]},
    }
    return (
        v,
        folder,
        {"label": "synthetic", "image": "input.png"},
        plan,
        tmp_path / "inference.json",
        live,
        usage_path,
        write,
    )


def check_case(case):
    v, folder, row, plan, manifest, live, recovery, _ = case
    return v.verify_case(
        folder,
        row,
        0,
        plan,
        manifest,
        live,
        recovery,
        v.timestamp("2026-09-29T10:00:00+00:00"),
    )


def test_case_zero_recovery_preserves_original_failure(case):
    result = check_case(case)
    assert result["status"] == "published_with_recovered_collector_failure"
    assert result["original_status"] == "technical_failure"


@pytest.mark.parametrize(
    "tamper", ["none", "recursive_inventory", "top_inventory", "usage_hash"]
)
def test_normal_publication_requires_its_own_inventories(case, tamper):
    v, folder, row, plan, manifest, live, recovery, write = case
    plan["planned_cases"].append(deepcopy(plan["planned_cases"][0]))
    for name in ("receipt.json", "attempt.json"):
        record = v.read(folder / name)
        record["index"] = 1
        write(folder / name, record)
    record = v.read(folder / "receipt.json")
    export = Path(record["export_dir"])
    usage_path = folder / "scientific-usage-receipt.json"
    usage_path.write_bytes(recovery.read_bytes())
    record.update(
        status="exported_verified",
        scientific_usage_sha256=v.digest(usage_path),
        recursive_artifact_sha256=v.inventory(export),
        artifact_sha256={p.name: v.digest(p) for p in export.iterdir() if p.is_file()},
    )
    if tamper == "recursive_inventory":
        record["recursive_artifact_sha256"].pop(str(Path("crops/local.png")))
    elif tamper == "top_inventory":
        record["artifact_sha256"].pop("source.png")
    elif tamper == "usage_hash":
        record["scientific_usage_sha256"] = "d" * 64
    write(folder / "receipt.json", record)
    args = (
        folder,
        row,
        1,
        plan,
        manifest,
        live,
        recovery,
        v.timestamp("2026-09-29T10:00:00+00:00"),
    )
    if tamper != "none":
        with pytest.raises(ValueError):
            v.verify_case(*args)
    else:
        assert v.verify_case(*args)["status"] == "published_verified"


@pytest.mark.parametrize(
    "tamper",
    [
        "other_failure",
        "identity",
        "gold",
        "input",
        "chronology",
        "roi",
        "pixels",
        "recovery",
        "failure_hash",
        "attempt_start",
        "contract",
    ],
)
def test_recovery_never_hides_unrelated_failure_or_wrong_pixels(case, tamper):
    v, folder, _, plan, _, _, _, write = case
    record = v.read(folder / "receipt.json")
    if tamper == "other_failure":
        record["error"] = "different failure"
    elif tamper == "identity":
        record["case_id"] = "other"
    elif tamper == "gold":
        record["gold_read"] = True
    elif tamper == "input":
        record["input_sha256"] = "d" * 64
    elif tamper == "chronology":
        record["finished_utc"] = "2026-09-29T09:00:00+00:00"
    elif tamper == "roi":
        plan["bindings"]["roi"][2] = 33
    elif tamper == "pixels":
        Image.new("RGB", (32, 24), "black").save(folder / "visible-roi.png")
    elif tamper == "recovery":
        plan["case0_usage_recovery_sha256"] = "d" * 64
    elif tamper == "attempt_start":
        record["started_utc"] = "2026-09-29T10:59:00+00:00"
    elif tamper == "contract":
        record["scientific_contract_sha256"] = "d" * 64
    write(folder / "receipt.json", record)
    if tamper != "failure_hash":
        plan["retained_case0_failure_sha256"] = v.digest(folder / "receipt.json")
    else:
        plan["retained_case0_failure_sha256"] = "d" * 64
    with pytest.raises(ValueError):
        check_case(case)


@pytest.fixture
def batch(case):
    v, folder, row, plan, manifest, live, recovery, write = case
    run = folder.parent
    (manifest.parent / "pending.png").write_bytes(b"unexposed synthetic pending")
    records = [
        {
            "case_identity": "synthetic",
            "image_sha256": plan["planned_cases"][0]["image_sha256"],
        },
        {
            "case_identity": "pending",
            "image_sha256": v.digest(manifest.parent / "pending.png"),
        },
    ]
    rows = [row, {"label": "pending", "image": "pending.png"}]
    order = v.legacy.canonical_digest(records)
    write(
        manifest,
        {
            "cases": rows,
            "counts": {"cases": 2},
            "selection": {
                "manifest_role": "inference",
                "input_image_order_sha256": order,
            },
        },
    )
    plan.update(
        source_head="synthetic-head",
        planned_cases=records,
        expected_model="gpt-6-astra",
        reasoning="medium",
        actual_gui_required=True,
        gold_read=False,
        scientific_review=True,
        started_utc="2026-09-29T10:00:00+00:00",
    )
    plan["bindings"].update(
        inference_sha256=v.digest(manifest),
        input_image_order_sha256=order,
        config_sha256="a" * 64,
        source_fingerprint="b" * 64,
        driver_sha256="d" * 64,
    )
    original = deepcopy(plan)
    write(run / "plan.json", original)
    plan.update(
        original_plan_sha256=v.digest(run / "plan.json"),
        started_utc="2026-09-29T11:02:00+00:00",
    )
    write(run / "plan-v2.json", plan)
    return v, run, manifest, live, recovery, write


def check_batch(batch):
    v, run, manifest, live, recovery, _ = batch
    return v.audit(
        run,
        manifest,
        live,
        recovery,
        v.digest(run / "plan.json"),
        v.digest(run / "plan-v2.json"),
    )


def test_partial_batch_is_not_complete_or_scored(batch):
    report = check_batch(batch)
    assert report["counts"] == {
        "published_verified": 0,
        "published_with_recovered_collector_failure": 1,
        "pending": 1,
        "invalid_evidence": 0,
        "technical_failure": 0,
    }
    assert not report["complete_evidence"] and not report["clinical_scored"]


@pytest.mark.parametrize(
    "tamper",
    [
        "source",
        "binding",
        "order",
        "count",
        "manifest_role",
        "plan_link",
        "extra_case",
        "plan_effort",
    ],
)
def test_batch_plan_and_input_tamper_fails(batch, tamper):
    v, run, manifest, _, _, write = batch
    plan = v.read(run / "plan-v2.json")
    if tamper == "source":
        (manifest.parent / "input.png").write_bytes(b"changed")
    elif tamper == "binding":
        plan["bindings"]["config_sha256"] = "f" * 64
    elif tamper == "order":
        plan["planned_cases"].reverse()
    elif tamper in {"count", "manifest_role"}:
        payload = v.read(manifest)
        if tamper == "count":
            payload["counts"]["cases"] = 3
        else:
            payload["selection"]["manifest_role"] = "gold"
        write(manifest, payload)
    elif tamper == "plan_link":
        plan["original_plan_sha256"] = "f" * 64
    elif tamper == "extra_case":
        (run / "case-999").mkdir()
    elif tamper == "plan_effort":
        plan["reasoning"] = "low"
    write(run / "plan-v2.json", plan)
    with pytest.raises(ValueError):
        check_batch(batch)


def test_terminal_after_pending_gap_is_not_accepted(batch):
    _, run, _, _, _, write = batch
    (run / "case-000/receipt.json").unlink()
    (run / "case-001").mkdir()
    write(run / "case-001/receipt.json", {})
    report = check_batch(batch)
    assert report["counts"]["pending"] == 1
    assert report["counts"]["invalid_evidence"] == 1


def test_genuine_failure_without_capture_is_distinct_from_invalid_evidence(batch):
    v, run, _, _, _, write = batch
    folder = run / "case-001"
    folder.mkdir()
    plan = v.read(run / "plan-v2.json")
    record = {
        "index": 1,
        "case_id": "pending",
        "input_sha256": plan["planned_cases"][1]["image_sha256"],
        "actual_gui": True,
        "gold_read": False,
        "direct_model_requests": 0,
        "started_utc": "2026-09-29T11:03:00+00:00",
    }
    write(folder / "attempt.json", record)
    record.update(status="technical_failure", finished_utc="2026-09-29T11:04:00+00:00")
    write(folder / "receipt.json", record)
    result = check_batch(batch)
    assert result["counts"]["technical_failure"] == 1
    assert result["counts"]["invalid_evidence"] == 0
    assert not result["complete_evidence"]


@pytest.mark.parametrize(
    "reuse",
    ["session_keys", "run_ids", "export_dir", "public_session_ids", "host_run_id"],
)
def test_batch_rejects_cross_case_identity_reuse(batch, monkeypatch, reuse):
    v, run, _, _, _, write = batch
    (run / "case-001").mkdir()
    write(run / "case-001/receipt.json", {})

    def verified(folder, row, index, *args):
        value = {
            "index": index,
            "status": "published_verified",
            "session_keys": [f"session-{index}"],
            "public_session_ids": [f"public-{index}"],
            "host_run_id": f"host-{index}",
            "run_ids": [f"run-{index}"],
            "export_dir": f"export-{index}",
            "finished_utc": f"2026-09-29T11:0{1 if index == 0 else 4}:00+00:00",
        }
        value[reuse] = (
            ["same"]
            if reuse in {"session_keys", "run_ids", "public_session_ids"}
            else "same"
        )
        return value

    monkeypatch.setattr(v, "verify_case", verified)
    result = check_batch(batch)
    assert result["counts"]["published_verified"] == 1
    assert result["counts"]["invalid_evidence"] == 1


def test_cli_partial_checkpoint_is_create_only_and_read_only(
    batch, monkeypatch, tmp_path
):
    v, run, manifest, live, recovery, _ = batch
    output = tmp_path.parent / (tmp_path.name + "-audit.json")
    before = v.inventory(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "audit",
            "--run",
            str(run),
            "--manifest",
            str(manifest),
            "--live",
            str(live),
            "--recovery",
            str(recovery),
            "--output",
            str(output),
            "--original-sha256",
            v.digest(run / "plan.json"),
            "--continuation-sha256",
            v.digest(run / "plan-v2.json"),
        ],
    )
    assert v.main() == 0
    assert v.read(output)["complete_evidence"] is False
    assert v.inventory(tmp_path) == before
    with pytest.raises(ValueError, match="output already exists"):
        v.main()


def test_cli_cannot_overwrite_or_write_into_primary_evidence(
    batch, monkeypatch, tmp_path
):
    v, run, manifest, live, recovery, _ = batch
    for output in (
        run / "forbidden.json",
        live / "forbidden.json",
        manifest.parent / "forbidden.json",
        recovery,
    ):
        monkeypatch.setattr(
            "sys.argv",
            [
                "audit",
                "--run",
                str(run),
                "--manifest",
                str(manifest),
                "--live",
                str(live),
                "--recovery",
                str(recovery),
                "--output",
                str(output),
                "--original-sha256",
                v.digest(run / "plan.json"),
                "--continuation-sha256",
                v.digest(run / "plan-v2.json"),
            ],
        )
        with pytest.raises(ValueError):
            v.main()
