"""Offline 10k+ scale gate for eval identity and crash/resume plumbing.

This is not a clinical-accuracy test. Its 10,001 deterministic identities all
point at one tiny synthetic byte fixture; they are protocol records, not 10,001
medical images. The canonical MEETI unique cohort remains 9,922 images.

Small production-path tests cover the physical artifact details which should
not be multiplied by 10,001 here:

* ``test_mock_run_and_resume_leave_full_canonical_scorecard`` rebuilds the
  canonical scorecard from persisted results after resume.
* ``test_run_evaluation_atomically_replaces_all_json_artifacts`` checks raw,
  partial, and final scorecard replacement.
* ``test_atomic_json_write_preserves_previous_file_when_replace_fails`` checks
  crash safety at the atomic replacement boundary.
"""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from dicom_overlay.domain.entities import Modality, Severity
from dicom_overlay.infrastructure.eval_harness import EvalCase, _atomic_write_json

if TYPE_CHECKING:
    from types import ModuleType


_SYNTHETIC_SCALE_CASE_COUNT = 10_001
_CANONICAL_MEETI_UNIQUE_COHORT_COUNT = 9_922
_INTERRUPT_AFTER = 4_097


def _load_run_eval_module() -> ModuleType:
    script = Path(__file__).resolve().parents[2] / "scripts" / "run-eval.py"
    spec = importlib.util.spec_from_file_location("run_eval_scale_gate", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fingerprint(run_eval: ModuleType, manifest_identity: dict) -> dict:
    protocol = {
        "manifest": manifest_identity,
        "model": {"id": "offline-scale-gate", "gateway_mode": "none"},
        "flags": {"defer_scoring": False, "clinical_accuracy": False},
    }
    return {
        "schema_version": 1,
        "created_at": "2000-01-01T00:00:00+00:00",
        "protocol_scope": "entire_run",
        "protocol_digest": run_eval._protocol_digest(protocol),
        "comparability": {
            "status": "comparable",
            "comparable": True,
            "reasons": [],
        },
        "protocol": protocol,
    }


def test_10001_identity_fingerprint_and_crash_resume_partition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep every synthetic identity exactly once across a simulated restart."""

    run_eval = _load_run_eval_module()
    assert _SYNTHETIC_SCALE_CASE_COUNT > 10_000
    assert _SYNTHETIC_SCALE_CASE_COUNT > _CANONICAL_MEETI_UNIQUE_COHORT_COUNT

    fixture = tmp_path / "synthetic-scale-fixture.bin"
    fixture.write_bytes(b"offline scale gate; no patient data\n")
    labels = [
        f"scale_case_{index:05d}" for index in range(_SYNTHETIC_SCALE_CASE_COUNT)
    ]
    cases = [
        EvalCase(
            image_path=fixture,
            modality=Modality.EKG,
            expected_severity=Severity.NORMAL,
            label=label,
        )
        for label in labels
    ]
    manifest = tmp_path / "manifest.synthetic-scale.json"
    manifest.write_text(
        json.dumps(
            {
                "dataset": "synthetic-scale-resume-plumbing-only",
                "clinical_accuracy": False,
                "canonical_meeti_unique_cohort_count": (
                    _CANONICAL_MEETI_UNIQUE_COHORT_COUNT
                ),
                "cases": [
                    {
                        "image": fixture.name,
                        "modality": "EKG",
                        "expected_severity": "normal",
                        "label": label,
                    }
                    for label in labels
                ],
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    original_sha256_file = run_eval._sha256_file
    hashed_paths: list[Path] = []

    def record_hash(path: Path) -> str:
        hashed_paths.append(path.resolve())
        return original_sha256_file(path)

    monkeypatch.setattr(run_eval, "_sha256_file", record_hash)
    manifest_identity = run_eval._manifest_identity(manifest, cases)
    fingerprint = _fingerprint(run_eval, manifest_identity)
    all_result_names = {run_eval._result_filename(label) for label in labels}

    assert manifest_identity["selected_case_count"] == len(labels)
    assert [row["case"] for row in manifest_identity["cases"]] == labels
    assert len(all_result_names) == len(labels)
    # The shared synthetic source is hashed once, not miscounted as 10,001
    # unique images. The manifest itself is the other hashed path.
    assert hashed_paths.count(fixture.resolve()) == 1
    assert run_eval._protocol_digest(deepcopy(fingerprint["protocol"])) == (
        fingerprint["protocol_digest"]
    )

    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    prepared = run_eval._prepare_protocol_fingerprint(
        output_dir=eval_dir,
        current=fingerprint,
        cases=cases,
        resume=False,
        legacy_policy="reject",
    )
    assert prepared["protocol_digest"] == fingerprint["protocol_digest"]
    assert run_eval._read_protocol_fingerprint(
        eval_dir / "protocol-fingerprint.json"
    )["protocol_digest"] == fingerprint["protocol_digest"]

    changed = deepcopy(fingerprint)
    changed["protocol"]["flags"]["clinical_accuracy"] = True
    changed["protocol_digest"] = run_eval._protocol_digest(changed["protocol"])
    with pytest.raises(run_eval.ProtocolFingerprintError, match="protocol mismatch"):
        run_eval._prepare_protocol_fingerprint(
            output_dir=eval_dir,
            current=changed,
            cases=cases,
            resume=True,
            legacy_policy="reject",
        )

    completed_labels = labels[:_INTERRUPT_AFTER]
    completed_names = {
        run_eval._result_filename(label) for label in completed_labels
    }
    pending, skipped = run_eval._partition_resume_cases(
        cases,
        completed_result_filenames=completed_names,
    )
    pending_labels = [case.label for case in pending]
    pending_names = {
        run_eval._result_filename(label) for label in pending_labels
    }

    assert skipped == _INTERRUPT_AFTER
    assert pending_labels == labels[_INTERRUPT_AFTER:]
    assert completed_names.isdisjoint(pending_names)
    assert completed_names | pending_names == all_result_names
    assert len(completed_names) + len(pending_names) == len(labels)

    # One compact durable checkpoint models the process boundary. Production
    # result/scorecard atomic-replace failure behavior is covered by the small
    # tests named in this module's docstring.
    checkpoint_path = eval_dir / "scale-resume-checkpoint.json"
    checkpoint = {
        "kind": "scale_crash_resume_plumbing_only",
        "clinical_accuracy": False,
        "canonical_meeti_unique_cohort_count": (
            _CANONICAL_MEETI_UNIQUE_COHORT_COUNT
        ),
        "protocol_digest": fingerprint["protocol_digest"],
        "manifest_total": len(labels),
        "result_count": len(completed_labels),
        "completed_case_ids": completed_labels,
        "pending_case_ids": pending_labels,
    }
    _atomic_write_json(
        checkpoint_path,
        json.dumps(checkpoint, separators=(",", ":")),
    )
    restored = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    restored_completed_names = {
        run_eval._result_filename(label)
        for label in restored["completed_case_ids"]
    }
    resumed_pending, resumed_skipped = run_eval._partition_resume_cases(
        cases,
        completed_result_filenames=restored_completed_names,
    )

    assert restored["protocol_digest"] == fingerprint["protocol_digest"]
    assert resumed_skipped == _INTERRUPT_AFTER
    assert [case.label for case in resumed_pending] == pending_labels

    final_pending, final_skipped = run_eval._partition_resume_cases(
        cases,
        completed_result_filenames=all_result_names,
    )
    canonical_identity_checkpoint = {
        **checkpoint,
        "result_count": len(labels),
        "completed_case_ids": labels,
        "pending_case_ids": [],
    }
    _atomic_write_json(
        checkpoint_path,
        json.dumps(canonical_identity_checkpoint, separators=(",", ":")),
    )
    canonical = json.loads(checkpoint_path.read_text(encoding="utf-8"))

    assert final_pending == []
    assert final_skipped == len(labels)
    assert canonical["manifest_total"] == len(labels)
    assert canonical["result_count"] == len(labels)
    assert canonical["pending_case_ids"] == []
    assert canonical["completed_case_ids"] == labels
    assert len(canonical["completed_case_ids"]) == len(
        set(canonical["completed_case_ids"])
    )
    assert not list(eval_dir.glob("*.tmp"))
