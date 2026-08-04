from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from sidecars.ecgfounder import evaluate

if TYPE_CHECKING:
    from pathlib import Path


def _row(
    artifact_id: str,
    *,
    score: float,
    concepts: frozenset[str] = frozenset(),
    expected_severity: str = "warning",
    label_status: str = "asserted",
) -> evaluate.ScoreRow:
    return evaluate.ScoreRow(
        artifact_id=artifact_id,
        concepts=concepts,
        expected_severity=expected_severity,
        label_status=label_status,
        ranked_labels=("TARGET",),
        scores={"TARGET": score},
    )


def _artifact_for_fold(*, prefix: str, fold: int, seed: str, folds: int) -> str:
    for index in range(10_000):
        artifact_id = f"{prefix}-{index}"
        if evaluate.fold_index(artifact_id, seed=seed, folds=folds) == fold:
            return artifact_id
    raise AssertionError("could not construct deterministic fold fixture")


def _write_run(
    root: Path,
    *,
    tasks: tuple[str, ...],
    concepts: object,
    max_predictions: int = 150,
    status: str = "ok",
    reason: str = "",
) -> None:
    protocol = {
        "schema_version": 1,
        "runner": "ecgfounder-meeti-batch-v3",
        "max_predictions": max_predictions,
        "case_count": 1,
    }
    protocol["fingerprint"] = evaluate.canonical_hash(protocol)
    predictions = [
        {"label": label, "probability": 1.0 - index / len(tasks)}
        for index, label in enumerate(tasks)
    ]
    result = {
        "schema_version": 1,
        "artifact_id": "wf-one",
        "status": status,
        "case": {
            "concepts": concepts,
            "expected_severity": "warning",
            "label_status": "asserted",
        },
        "predictions": predictions if status == "ok" else [],
    }
    if reason:
        result["reason"] = reason
    (root / "protocol.json").write_text(json.dumps(protocol), encoding="utf-8")
    (root / "results.jsonl").write_text(json.dumps(result) + "\n", encoding="utf-8")
    (root / "summary.json").write_text(
        json.dumps(
            {
                "status": "complete" if status == "ok" else "incomplete",
                "completed_case_count": 1,
                "target_case_count": 1,
                "status_counts": {status: 1},
                "protocol": protocol,
            }
        ),
        encoding="utf-8",
    )


def test_statement_map_only_references_pinned_task_vocabulary() -> None:
    tasks = evaluate.load_tasks(evaluate.DEFAULT_TASKS)

    mappings = evaluate.load_concept_map(evaluate.DEFAULT_MAPPING, tasks=tasks)

    assert len(tasks) == 150
    assert len(mappings) >= 30
    assert all(set(mapping.statements) <= set(tasks) for mapping in mappings.values())


def test_full_score_loader_rejects_truncated_vectors_before_reading_results(
    tmp_path: Path,
) -> None:
    tasks = evaluate.load_tasks(evaluate.DEFAULT_TASKS)
    _write_run(tmp_path, tasks=tasks, concepts=["afib"], max_predictions=20)

    with pytest.raises(ValueError, match="all 150"):
        evaluate.load_full_score_rows(tmp_path, tasks=tasks)


def test_full_score_loader_rejects_invalid_concept_metadata(tmp_path: Path) -> None:
    tasks = evaluate.load_tasks(evaluate.DEFAULT_TASKS)
    _write_run(tmp_path, tasks=tasks, concepts=["afib", 42])

    with pytest.raises(ValueError, match="invalid case concepts"):
        evaluate.load_full_score_rows(tmp_path, tasks=tasks)


def test_full_score_loader_rejects_tampered_protocol_fingerprint(
    tmp_path: Path,
) -> None:
    tasks = evaluate.load_tasks(evaluate.DEFAULT_TASKS)
    _write_run(tmp_path, tasks=tasks, concepts=["afib"])
    protocol_path = tmp_path / "protocol.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol["case_count"] = 2
    protocol_path.write_text(json.dumps(protocol), encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint mismatch"):
        evaluate.load_full_score_rows(tmp_path, tasks=tasks)


def test_full_score_dataset_reports_explicit_ineligible_exclusion(
    tmp_path: Path,
) -> None:
    tasks = evaluate.load_tasks(evaluate.DEFAULT_TASKS)
    _write_run(
        tmp_path,
        tasks=tasks,
        concepts=["pvc"],
        status="ineligible",
        reason="waveform_contains_flat_lead",
    )

    with pytest.raises(ValueError, match="non-ok"):
        evaluate.load_full_score_rows(tmp_path, tasks=tasks)

    dataset = evaluate.load_full_score_dataset(
        tmp_path,
        tasks=tasks,
        allow_ineligible=True,
    )

    assert dataset.rows == ()
    assert dataset.target_case_count == 1
    assert dataset.exclusions == (
        evaluate.ScoreExclusion("wf-one", "waveform_contains_flat_lead"),
    )


def test_controls_never_treat_report_silence_or_uncertainty_as_negative() -> None:
    explicit_normal = _row(
        "normal",
        score=0.1,
        concepts=frozenset({"normal"}),
        expected_severity="normal",
    )
    silent_abnormal = _row("silent", score=0.2, concepts=frozenset())
    partial_normal = _row(
        "partial",
        score=0.3,
        concepts=frozenset({"normal"}),
        expected_severity="normal",
        label_status="partially_uncertain",
    )

    assert evaluate._controls(
        [explicit_normal, silent_abnormal, partial_normal], "explicit_normal"
    ) == [explicit_normal]


def test_cross_validation_selects_thresholds_without_test_fold_leakage() -> None:
    seed = "cv-test"
    folds = 5
    positives = [
        _row(
            _artifact_for_fold(
                prefix=f"positive-{fold}", fold=fold, seed=seed, folds=folds
            ),
            score=0.9,
            concepts=frozenset({"target"}),
        )
        for fold in range(folds)
    ]
    controls = [
        _row(
            _artifact_for_fold(
                prefix=f"control-{fold}", fold=fold, seed=seed, folds=folds
            ),
            score=0.1,
            concepts=frozenset({"normal"}),
            expected_severity="normal",
        )
        for fold in range(folds)
    ]

    metrics = evaluate.cross_validated_metrics(
        positives,
        controls,
        mapping=evaluate.ConceptMap(("TARGET",), "explicit_normal"),
        seed=seed,
        folds=folds,
        min_training_positives=4,
        min_training_controls=4,
    )

    assert metrics is not None
    assert metrics["balanced_accuracy"] == 1.0
    assert metrics["confusion"] == {"tp": 5, "fn": 0, "fp": 0, "tn": 5}
    assert metrics["threshold_installable"] is False
    assert len(metrics["fold_thresholds"]) == folds


def test_ranking_reports_complete_three_diagnosis_recall() -> None:
    mappings = {
        concept: evaluate.ConceptMap((label,), "explicit_normal")
        for concept, label in (("a", "A"), ("b", "B"), ("c", "C"))
    }
    row = evaluate.ScoreRow(
        artifact_id="ranked",
        concepts=frozenset(mappings),
        expected_severity="warning",
        label_status="asserted",
        ranked_labels=("A", "B", "C"),
        scores={"A": 0.9, "B": 0.8, "C": 0.7},
    )

    metrics = evaluate._ranking_metrics([row], mappings)

    assert metrics["at_k"]["1"]["three_to_five_complete_recall"] == 0.0
    assert metrics["at_k"]["3"]["three_to_five_complete_recall"] == 1.0
    assert metrics["at_k"]["3"]["micro_concept_recall"] == 1.0
