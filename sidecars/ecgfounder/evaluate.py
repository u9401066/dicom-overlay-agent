"""Leakage-aware research evaluation for ECGFounder MEETI waveform scores."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, median
from typing import Any

SCHEMA_VERSION = 1
EVALUATOR_VERSION = "ecgfounder-meeti-heldout-v2"
DEFAULT_RUN_DIR = Path(
    "data/eval-runs/ecgfounder-meeti-1000-fullscores-20260804"
)
DEFAULT_MAPPING = Path(__file__).resolve().parent / "meeti_statement_map.json"
DEFAULT_TASKS = Path(__file__).resolve().parent / "tasks.txt"
_CONTROL_GROUPS = frozenset(
    {"explicit_normal", "asserted_abnormal", "positive_ranking_only"}
)
_SUPPORTED_RUNNERS = frozenset(
    {"ecgfounder-meeti-batch-v2", "ecgfounder-meeti-batch-v3"}
)


@dataclass(frozen=True)
class ConceptMap:
    statements: tuple[str, ...]
    control_group: str


@dataclass(frozen=True)
class ScoreRow:
    artifact_id: str
    concepts: frozenset[str]
    expected_severity: str
    label_status: str
    ranked_labels: tuple[str, ...]
    scores: dict[str, float]

    def concept_score(self, mapping: ConceptMap) -> float:
        return max(self.scores[label] for label in mapping.statements)


@dataclass(frozen=True)
class ScoreExclusion:
    artifact_id: str
    reason: str


@dataclass(frozen=True)
class ScoreDataset:
    rows: tuple[ScoreRow, ...]
    exclusions: tuple[ScoreExclusion, ...]
    target_case_count: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_tasks(path: Path) -> tuple[str, ...]:
    try:
        tasks = tuple(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError as exc:
        raise ValueError(f"cannot read task vocabulary: {path}") from exc
    if len(tasks) != 150 or len(set(tasks)) != 150:
        raise ValueError("ECGFounder task vocabulary must have 150 unique labels")
    return tasks


def load_concept_map(path: Path, *, tasks: tuple[str, ...]) -> dict[str, ConceptMap]:
    payload = _read_object(path)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported ECGFounder statement-map schema")
    raw_concepts = payload.get("concepts")
    if not isinstance(raw_concepts, dict) or not raw_concepts:
        raise ValueError("statement map has no concepts")
    task_set = set(tasks)
    mappings: dict[str, ConceptMap] = {}
    for concept, raw in raw_concepts.items():
        if not isinstance(concept, str) or not concept or not isinstance(raw, dict):
            raise ValueError("statement map contains an invalid concept")
        control_group = raw.get("control_group")
        statements = raw.get("statements")
        if control_group not in _CONTROL_GROUPS:
            raise ValueError(f"invalid control group for {concept}")
        if not isinstance(statements, list) or not statements:
            raise ValueError(f"statement map has no labels for {concept}")
        clean = tuple(item for item in statements if isinstance(item, str) and item)
        if len(clean) != len(statements) or len(clean) != len(set(clean)):
            raise ValueError(f"statement map has invalid labels for {concept}")
        unknown = set(clean) - task_set
        if unknown:
            raise ValueError(
                f"statement map references unknown labels for {concept}: "
                + ", ".join(sorted(unknown))
            )
        mappings[concept] = ConceptMap(clean, str(control_group))
    return mappings


def load_full_score_dataset(
    run_dir: Path,
    *,
    tasks: tuple[str, ...],
    allow_ineligible: bool = False,
) -> ScoreDataset:
    protocol = _read_object(run_dir / "protocol.json")
    if protocol.get("runner") not in _SUPPORTED_RUNNERS:
        raise ValueError("unsupported ECGFounder batch protocol")
    recorded_fingerprint = protocol.get("fingerprint")
    fingerprint_payload = {
        key: value for key, value in protocol.items() if key != "fingerprint"
    }
    if recorded_fingerprint != canonical_hash(fingerprint_payload):
        raise ValueError("ECGFounder batch protocol fingerprint mismatch")
    if protocol.get("max_predictions") != len(tasks):
        raise ValueError("evaluation requires all 150 ECGFounder scores")
    task_set = set(tasks)
    rows: list[ScoreRow] = []
    exclusions: list[ScoreExclusion] = []
    artifacts: set[str] = set()
    results_path = run_dir / "results.jsonl"
    try:
        stream = results_path.open(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read full-score results: {results_path}") from exc
    with stream:
        for line_number, line in enumerate(stream, start=1):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid result JSON at line {line_number}") from exc
            if not isinstance(raw, dict):
                raise ValueError(f"invalid full-score result at line {line_number}")
            artifact_id = raw.get("artifact_id")
            if not isinstance(artifact_id, str) or not artifact_id:
                raise ValueError(f"missing artifact id at line {line_number}")
            if artifact_id in artifacts:
                raise ValueError(f"duplicate artifact id: {artifact_id}")
            artifacts.add(artifact_id)
            status = raw.get("status")
            if status == "ineligible":
                if not allow_ineligible:
                    raise ValueError(f"non-ok full-score result at line {line_number}")
                reason = raw.get("reason")
                if not isinstance(reason, str) or not reason:
                    raise ValueError(
                        f"ineligible result has no reason at line {line_number}"
                    )
                if raw.get("predictions") != []:
                    raise ValueError(
                        f"ineligible result has predictions at line {line_number}"
                    )
                exclusions.append(ScoreExclusion(artifact_id, reason))
                continue
            if status != "ok":
                raise ValueError(f"non-ok full-score result at line {line_number}")
            raw_predictions = raw.get("predictions")
            if not isinstance(raw_predictions, list) or len(raw_predictions) != len(tasks):
                raise ValueError(f"incomplete prediction vector at line {line_number}")
            ranked_labels: list[str] = []
            scores: dict[str, float] = {}
            previous = math.inf
            for prediction in raw_predictions:
                if not isinstance(prediction, dict):
                    raise ValueError(f"invalid prediction at line {line_number}")
                label = prediction.get("label")
                probability = prediction.get("probability")
                if not isinstance(label, str) or not isinstance(probability, int | float):
                    raise ValueError(f"invalid prediction value at line {line_number}")
                score = float(probability)
                if not math.isfinite(score) or not 0.0 <= score <= 1.0:
                    raise ValueError(f"score outside [0,1] at line {line_number}")
                if score > previous:
                    raise ValueError(f"predictions are not ranked at line {line_number}")
                previous = score
                ranked_labels.append(label)
                scores[label] = score
            if set(ranked_labels) != task_set or len(scores) != len(tasks):
                raise ValueError(f"prediction vocabulary mismatch at line {line_number}")
            case = raw.get("case")
            if not isinstance(case, dict):
                raise ValueError(f"missing case metadata at line {line_number}")
            concepts = case.get("concepts")
            if (
                not isinstance(concepts, list)
                or not all(isinstance(item, str) and item for item in concepts)
                or len(concepts) != len(set(concepts))
            ):
                raise ValueError(f"invalid case concepts at line {line_number}")
            clean_concepts = frozenset(concepts)
            rows.append(
                ScoreRow(
                    artifact_id=artifact_id,
                    concepts=clean_concepts,
                    expected_severity=str(case.get("expected_severity") or ""),
                    label_status=str(case.get("label_status") or ""),
                    ranked_labels=tuple(ranked_labels),
                    scores=scores,
                )
            )
    summary = _read_object(run_dir / "summary.json")
    target = int(summary.get("target_case_count") or 0)
    if summary.get("protocol") != protocol:
        raise ValueError("summary protocol does not match the pinned protocol")
    if len(rows) + len(exclusions) != target or target != protocol.get("case_count"):
        raise ValueError("full-score run is incomplete")
    status_counts = summary.get("status_counts")
    if allow_ineligible:
        if summary.get("status") not in {"complete", "incomplete"}:
            raise ValueError("full-score run is incomplete")
        if summary.get("completed_case_count") != target:
            raise ValueError("full-score run did not traverse the complete cohort")
        if not isinstance(status_counts, dict) or set(status_counts) - {
            "ok",
            "ineligible",
        }:
            raise ValueError("full-score status counts are invalid")
        if status_counts.get("ok", 0) != len(rows) or status_counts.get(
            "ineligible", 0
        ) != len(exclusions):
            raise ValueError("full-score status counts do not match results")
    elif summary.get("status") != "complete" or exclusions:
        raise ValueError("full-score run is incomplete")
    return ScoreDataset(tuple(rows), tuple(exclusions), target)


def load_full_score_rows(run_dir: Path, *, tasks: tuple[str, ...]) -> list[ScoreRow]:
    return list(load_full_score_dataset(run_dir, tasks=tasks).rows)


def split_role(artifact_id: str, *, seed: str, calibration_fraction: float) -> str:
    if not 0.0 < calibration_fraction < 1.0:
        raise ValueError("calibration fraction must be between zero and one")
    digest = hashlib.sha256(f"{seed}:{artifact_id}".encode()).digest()
    unit = int.from_bytes(digest[:8], "big") / (2**64)
    return "calibration" if unit < calibration_fraction else "holdout"


def fold_index(artifact_id: str, *, seed: str, folds: int) -> int:
    if folds < 2:
        raise ValueError("cross-validation requires at least two folds")
    digest = hashlib.sha256(f"{seed}:fold:{artifact_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % folds


def _is_explicit_normal(row: ScoreRow) -> bool:
    return (
        row.label_status == "asserted"
        and row.expected_severity == "normal"
        and "normal" in row.concepts
    )


def _is_asserted_abnormal(row: ScoreRow) -> bool:
    return (
        row.label_status == "asserted"
        and row.expected_severity in {"warning", "critical"}
        and bool(row.concepts - {"normal", "sinus"})
    )


def _controls(rows: list[ScoreRow], group: str) -> list[ScoreRow]:
    if group == "explicit_normal":
        return [row for row in rows if _is_explicit_normal(row)]
    if group == "asserted_abnormal":
        return [row for row in rows if _is_asserted_abnormal(row)]
    return []


def confusion(
    positives: list[float], negatives: list[float], *, threshold: float
) -> dict[str, int]:
    tp = sum(score > threshold for score in positives)
    fn = len(positives) - tp
    fp = sum(score > threshold for score in negatives)
    tn = len(negatives) - fp
    return {"tp": tp, "fn": fn, "fp": fp, "tn": tn}


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def metrics_from_confusion(counts: dict[str, int]) -> dict[str, float]:
    tp, fn, fp, tn = (counts[key] for key in ("tp", "fn", "fp", "tn"))
    sensitivity = _ratio(tp, tp + fn)
    specificity = _ratio(tn, tn + fp)
    precision = _ratio(tp, tp + fp)
    npv = _ratio(tn, tn + fn)
    return {
        "sensitivity": sensitivity,
        "specificity": specificity,
        "balanced_accuracy": (sensitivity + specificity) / 2,
        "precision": precision,
        "npv": npv,
        "f1": _ratio(2 * precision * sensitivity, precision + sensitivity),
    }


def choose_threshold(positives: list[float], negatives: list[float]) -> float:
    """Match ECGFounder's official balanced-accuracy grid on calibration data."""
    best_threshold = 0.5
    best_score = -1.0
    for step in range(1, 100):
        threshold = step / 100
        score = metrics_from_confusion(
            confusion(positives, negatives, threshold=threshold)
        )["balanced_accuracy"]
        if score > best_score:
            best_score = score
            best_threshold = threshold
    return best_threshold


def wilson_interval(successes: int, total: int, *, z: float = 1.959964) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    proportion = successes / total
    denominator = 1 + (z * z / total)
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total + z * z / (4 * total * total)
        )
        / denominator
    )
    return [max(0.0, center - margin), min(1.0, center + margin)]


def roc_auc(positives: list[float], negatives: list[float]) -> float:
    if not positives or not negatives:
        return 0.0
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            if positive > negative:
                wins += 1.0
            elif positive == negative:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def average_precision(positives: list[float], negatives: list[float]) -> float:
    if not positives:
        return 0.0
    grouped: dict[float, list[int]] = {}
    for score in positives:
        grouped.setdefault(score, [0, 0])[0] += 1
    for score in negatives:
        grouped.setdefault(score, [0, 0])[1] += 1
    tp = 0
    fp = 0
    ap = 0.0
    for score in sorted(grouped, reverse=True):
        group_positive, group_negative = grouped[score]
        tp += group_positive
        fp += group_negative
        if group_positive:
            recall_increment = group_positive / len(positives)
            ap += recall_increment * _ratio(tp, tp + fp)
    return ap


def _score_metrics(
    positives: list[float], negatives: list[float], *, threshold: float
) -> dict[str, Any]:
    counts = confusion(positives, negatives, threshold=threshold)
    metrics = metrics_from_confusion(counts)
    metrics.update(
        {
            "confusion": counts,
            "sensitivity_95ci": wilson_interval(
                counts["tp"], counts["tp"] + counts["fn"]
            ),
            "specificity_95ci": wilson_interval(
                counts["tn"], counts["tn"] + counts["fp"]
            ),
            "auroc": roc_auc(positives, negatives),
            "average_precision": average_precision(positives, negatives),
        }
    )
    return metrics


def cross_validated_metrics(
    positives: list[ScoreRow],
    controls: list[ScoreRow],
    *,
    mapping: ConceptMap,
    seed: str,
    folds: int,
    min_training_positives: int,
    min_training_controls: int,
) -> dict[str, Any] | None:
    total_counts = {"tp": 0, "fn": 0, "fp": 0, "tn": 0}
    thresholds: list[float] = []
    evaluated_folds = 0
    for fold in range(folds):
        training_positive = [
            row.concept_score(mapping)
            for row in positives
            if fold_index(row.artifact_id, seed=seed, folds=folds) != fold
        ]
        training_control = [
            row.concept_score(mapping)
            for row in controls
            if fold_index(row.artifact_id, seed=seed, folds=folds) != fold
        ]
        test_positive = [
            row.concept_score(mapping)
            for row in positives
            if fold_index(row.artifact_id, seed=seed, folds=folds) == fold
        ]
        test_control = [
            row.concept_score(mapping)
            for row in controls
            if fold_index(row.artifact_id, seed=seed, folds=folds) == fold
        ]
        if (
            len(training_positive) < min_training_positives
            or len(training_control) < min_training_controls
            or not test_positive
            or not test_control
        ):
            return None
        threshold = choose_threshold(training_positive, training_control)
        thresholds.append(threshold)
        counts = confusion(test_positive, test_control, threshold=threshold)
        for key, value in counts.items():
            total_counts[key] += value
        evaluated_folds += 1
    positive_scores = [row.concept_score(mapping) for row in positives]
    control_scores = [row.concept_score(mapping) for row in controls]
    metrics = metrics_from_confusion(total_counts)
    metrics.update(
        {
            "confusion": total_counts,
            "sensitivity_95ci": wilson_interval(
                total_counts["tp"], total_counts["tp"] + total_counts["fn"]
            ),
            "specificity_95ci": wilson_interval(
                total_counts["tn"], total_counts["tn"] + total_counts["fp"]
            ),
            "auroc": roc_auc(positive_scores, control_scores),
            "average_precision": average_precision(
                positive_scores, control_scores
            ),
            "fold_count": evaluated_folds,
            "fold_thresholds": thresholds,
            "threshold_median": median(thresholds),
            "threshold_min": min(thresholds),
            "threshold_max": max(thresholds),
            "threshold_installable": False,
        }
    )
    return metrics


def _ranking_metrics(
    rows: list[ScoreRow], mappings: dict[str, ConceptMap]
) -> dict[str, Any]:
    inverse: dict[str, set[str]] = {}
    for concept, mapping in mappings.items():
        for statement in mapping.statements:
            inverse.setdefault(statement, set()).add(concept)
    expected_instances = 0
    reciprocal_ranks: list[float] = []
    first_ranks: list[int] = []
    ks = (1, 3, 5, 10, 20)
    counters = {
        k: {
            "hits": 0,
            "cases": 0,
            "cases_any": 0,
            "cases_complete": 0,
            "cases_3_to_5": 0,
            "cases_3_to_5_complete": 0,
        }
        for k in ks
    }
    mappable_cases = 0
    three_to_five_cases = 0
    for row in rows:
        expected = row.concepts & mappings.keys()
        if not expected:
            continue
        mappable_cases += 1
        expected_instances += len(expected)
        if 3 <= len(expected) <= 5:
            three_to_five_cases += 1
        for concept in expected:
            labels = set(mappings[concept].statements)
            rank = next(
                index
                for index, label in enumerate(row.ranked_labels, start=1)
                if label in labels
            )
            first_ranks.append(rank)
            reciprocal_ranks.append(1 / rank)
        for k in ks:
            predicted: set[str] = set()
            for label in row.ranked_labels[:k]:
                predicted.update(inverse.get(label, ()))
            hits = len(expected & predicted)
            counter = counters[k]
            counter["hits"] += hits
            counter["cases"] += 1
            counter["cases_any"] += int(hits > 0)
            counter["cases_complete"] += int(hits == len(expected))
            if 3 <= len(expected) <= 5:
                counter["cases_3_to_5"] += 1
                counter["cases_3_to_5_complete"] += int(hits == len(expected))
    at_k: dict[str, Any] = {}
    for k, counter in counters.items():
        at_k[str(k)] = {
            "micro_concept_recall": _ratio(counter["hits"], expected_instances),
            "case_any_recall": _ratio(counter["cases_any"], counter["cases"]),
            "case_complete_recall": _ratio(
                counter["cases_complete"], counter["cases"]
            ),
            "three_to_five_complete_recall": _ratio(
                counter["cases_3_to_5_complete"], counter["cases_3_to_5"]
            ),
        }
    return {
        "row_count": len(rows),
        "mappable_case_count": mappable_cases,
        "mappable_expected_concept_instances": expected_instances,
        "three_to_five_mappable_diagnosis_cases": three_to_five_cases,
        "mean_reciprocal_rank": fmean(reciprocal_ranks) if reciprocal_ranks else 0.0,
        "median_first_statement_rank": median(first_ranks) if first_ranks else 0.0,
        "at_k": at_k,
        "precision_warning": (
            "Reference reports do not enumerate every absent diagnosis; top-k "
            "precision is intentionally not estimated."
        ),
    }


def evaluate(
    *,
    run_dir: Path,
    mapping_path: Path = DEFAULT_MAPPING,
    tasks_path: Path = DEFAULT_TASKS,
    split_seed: str = "meeti-ecgfounder-heldout-v1",
    calibration_fraction: float = 0.60,
    min_positive_per_split: int = 5,
    min_control_per_split: int = 10,
    cross_validation_folds: int = 5,
    allow_ineligible: bool = False,
) -> dict[str, Any]:
    tasks = load_tasks(tasks_path)
    mappings = load_concept_map(mapping_path, tasks=tasks)
    dataset = load_full_score_dataset(
        run_dir,
        tasks=tasks,
        allow_ineligible=allow_ineligible,
    )
    rows = list(dataset.rows)
    roles = {
        row.artifact_id: split_role(
            row.artifact_id,
            seed=split_seed,
            calibration_fraction=calibration_fraction,
        )
        for row in rows
    }
    concept_results: dict[str, Any] = {}
    evaluated: list[dict[str, Any]] = []
    cross_validated: list[dict[str, Any]] = []
    observed_concepts = set().union(*(row.concepts for row in rows))
    for concept, mapping in mappings.items():
        positives = [row for row in rows if concept in row.concepts]
        controls = _controls(rows, mapping.control_group)
        result: dict[str, Any] = {
            "control_group": mapping.control_group,
            "comparison_scope": (
                "asserted concept positives versus explicit normal controls"
                if mapping.control_group == "explicit_normal"
                else (
                    "explicit normal positives versus asserted abnormal controls"
                    if mapping.control_group == "asserted_abnormal"
                    else "positive ranking only; no negative class is inferred"
                )
            ),
            "statements": list(mapping.statements),
            "positive_count": len(positives),
            "control_count": len(controls),
        }
        if mapping.control_group == "positive_ranking_only":
            result["status"] = "ranking_only"
            concept_results[concept] = result
            continue
        cv_metrics = cross_validated_metrics(
            positives,
            controls,
            mapping=mapping,
            seed=split_seed,
            folds=cross_validation_folds,
            min_training_positives=min_positive_per_split,
            min_training_controls=min_control_per_split,
        )
        if cv_metrics is not None:
            result["cross_validation"] = cv_metrics
            cross_validated.append(result)
        calibration_positive = [
            row.concept_score(mapping)
            for row in positives
            if roles[row.artifact_id] == "calibration"
        ]
        holdout_positive = [
            row.concept_score(mapping)
            for row in positives
            if roles[row.artifact_id] == "holdout"
        ]
        calibration_control = [
            row.concept_score(mapping)
            for row in controls
            if roles[row.artifact_id] == "calibration"
        ]
        holdout_control = [
            row.concept_score(mapping)
            for row in controls
            if roles[row.artifact_id] == "holdout"
        ]
        result["split_support"] = {
            "calibration_positive": len(calibration_positive),
            "calibration_control": len(calibration_control),
            "holdout_positive": len(holdout_positive),
            "holdout_control": len(holdout_control),
        }
        if (
            len(calibration_positive) < min_positive_per_split
            or len(holdout_positive) < min_positive_per_split
            or len(calibration_control) < min_control_per_split
            or len(holdout_control) < min_control_per_split
        ):
            result["status"] = "insufficient_support"
            concept_results[concept] = result
            continue
        threshold = choose_threshold(calibration_positive, calibration_control)
        result.update(
            {
                "status": "research_holdout_evaluated",
                "threshold": threshold,
                "threshold_installable": False,
                "calibration": _score_metrics(
                    calibration_positive,
                    calibration_control,
                    threshold=threshold,
                ),
                "holdout": _score_metrics(
                    holdout_positive,
                    holdout_control,
                    threshold=threshold,
                ),
            }
        )
        evaluated.append(result)
        concept_results[concept] = result
    holdout_rows = [row for row in rows if roles[row.artifact_id] == "holdout"]
    holdout_balanced = [item["holdout"]["balanced_accuracy"] for item in evaluated]
    holdout_sensitivity = [item["holdout"]["sensitivity"] for item in evaluated]
    holdout_specificity = [item["holdout"]["specificity"] for item in evaluated]
    cv_balanced = [
        item["cross_validation"]["balanced_accuracy"]
        for item in cross_validated
    ]
    cv_sensitivity = [
        item["cross_validation"]["sensitivity"] for item in cross_validated
    ]
    cv_specificity = [
        item["cross_validation"]["specificity"] for item in cross_validated
    ]
    mapping_coverage_instances = sum(
        len(row.concepts & mappings.keys()) for row in rows
    )
    total_instances = sum(len(row.concepts) for row in rows)
    protocol = _read_object(run_dir / "protocol.json")
    evaluation_protocol = {
        "schema_version": SCHEMA_VERSION,
        "evaluator": EVALUATOR_VERSION,
        "run_protocol_fingerprint": protocol.get("fingerprint"),
        "results_sha256": sha256_file(run_dir / "results.jsonl"),
        "mapping_sha256": sha256_file(mapping_path),
        "tasks_sha256": sha256_file(tasks_path),
        "split_seed": split_seed,
        "split_unit": "opaque waveform artifact id",
        "calibration_fraction": calibration_fraction,
        "cross_validation_folds": cross_validation_folds,
        "threshold_selection": (
            "maximize balanced accuracy on 0.01..0.99 grid using calibration "
            "partition only; official ECGFounder method adapted to heldout use"
        ),
        "positive_policy": (
            "affirmative concepts from the MEETI classifier's concepts field; "
            "uncertain_concepts are excluded even when label_status is partial"
        ),
        "uncertain_label_policy": (
            "uncertain concepts are neither positive labels nor negative labels"
        ),
        "negative_control_policy": (
            "explicit normal reports for abnormal concepts; asserted abnormal "
            "reports for the normal concept; absence is never assumed negative"
        ),
        "patient_level_isolation": False,
        "ineligible_case_policy": (
            "explicit_exclusion_with_coverage_reporting"
            if allow_ineligible
            else "reject_run"
        ),
    }
    evaluation_protocol["fingerprint"] = canonical_hash(evaluation_protocol)
    target = 0.85
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "use_policy": "research_supporting_evidence_only",
        "protocol": evaluation_protocol,
        "cohort": {
            "row_count": len(rows),
            "target_row_count": dataset.target_case_count,
            "ineligible_row_count": len(dataset.exclusions),
            "eligibility_fraction": _ratio(len(rows), dataset.target_case_count),
            "ineligible_reason_counts": {
                reason: sum(item.reason == reason for item in dataset.exclusions)
                for reason in sorted({item.reason for item in dataset.exclusions})
            },
            "ineligible_cases": [
                {"artifact_id": item.artifact_id, "reason": item.reason}
                for item in dataset.exclusions
            ],
            "calibration_rows": len(rows) - len(holdout_rows),
            "holdout_rows": len(holdout_rows),
            "observed_reference_concepts": len(observed_concepts),
            "mapped_reference_concepts": len(observed_concepts & mappings.keys()),
            "mapped_concept_instance_fraction": _ratio(
                mapping_coverage_instances, total_instances
            ),
        },
        "ranking": {
            "holdout": _ranking_metrics(holdout_rows, mappings),
            "all_rows_exploratory": _ranking_metrics(rows, mappings),
        },
        "threshold_evaluation": {
            "eligible_concept_count": len(evaluated),
            "cross_validated_concept_count": len(cross_validated),
            "primary_estimate": "deterministic out-of-fold cross-validation",
            "macro_cross_validated_balanced_accuracy": (
                fmean(cv_balanced) if cv_balanced else 0.0
            ),
            "macro_cross_validated_sensitivity": (
                fmean(cv_sensitivity) if cv_sensitivity else 0.0
            ),
            "macro_cross_validated_explicit_control_specificity": (
                fmean(cv_specificity) if cv_specificity else 0.0
            ),
            "cross_validated_concepts_meeting_0_85_balanced_accuracy": sum(
                value >= target for value in cv_balanced
            ),
            "macro_holdout_balanced_accuracy": (
                fmean(holdout_balanced) if holdout_balanced else 0.0
            ),
            "macro_holdout_sensitivity": (
                fmean(holdout_sensitivity) if holdout_sensitivity else 0.0
            ),
            "macro_holdout_specificity": (
                fmean(holdout_specificity) if holdout_specificity else 0.0
            ),
            "concepts_meeting_0_85_balanced_accuracy": sum(
                value >= target for value in holdout_balanced
            ),
            "concepts": concept_results,
        },
        "product_accuracy_target": {
            "single_diagnosis_target": target,
            "status": "not_comparable",
            "reason": (
                "This waveform-only ontology audit is not the screenshot agent's "
                "single- or multi-diagnosis accuracy."
            ),
        },
        "limitations": [
            "MEETI report labels are weak clinical-report labels, not a blinded adjudication panel.",
            "Patient identifiers are unavailable, so patient-level split isolation cannot be proven.",
            "Only explicit normal reports are used as abnormal-concept controls; report silence is not a negative label.",
            "Reported specificity for abnormal concepts is specificity against explicit-normal controls, not one-vs-all disease specificity.",
            "The semantic statement map is hand-authored and hash-pinned but not independently clinician-adjudicated.",
            "Thresholds are research-only and must not be installed as deployment calibration.",
            "ECGFounder provides no screenshot localization or bounding boxes.",
            *(
                [
                    f"{len(dataset.exclusions)} waveform case(s) were excluded by "
                    "the pinned input-quality gate; metrics cover eligible cases only."
                ]
                if dataset.exclusions
                else []
            ),
        ],
        "sources": {
            "official_repository": "https://github.com/PKUDigitalHealth/ECGFounder",
            "official_threshold_code": "https://github.com/PKUDigitalHealth/ECGFounder/blob/master/util.py",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    cohort = report["cohort"]
    ranking = report["ranking"]["holdout"]
    threshold = report["threshold_evaluation"]
    at_20 = ranking["at_k"]["20"]
    lines = [
        "# ECGFounder MEETI Held-out Research Evaluation",
        "",
        f"- Protocol: `{report['protocol']['fingerprint']}`",
        (
            f"- Cohort: {cohort['row_count']} eligible / "
            f"{cohort['target_row_count']} traversed; holdout "
            f"{cohort['holdout_rows']}"
        ),
        (
            f"- Input eligibility: {cohort['eligibility_fraction']:.3%}; "
            f"excluded {cohort['ineligible_row_count']}"
        ),
        (
            "- Ontology coverage: "
            f"{cohort['mapped_concept_instance_fraction']:.3f} of asserted "
            "concept instances"
        ),
        (
            "- Cross-validated threshold concepts: "
            f"{threshold['cross_validated_concept_count']}"
        ),
        (
            "- Macro cross-validated balanced accuracy: "
            f"{threshold['macro_cross_validated_balanced_accuracy']:.3f}"
        ),
        (
            "- Macro cross-validated sensitivity: "
            f"{threshold['macro_cross_validated_sensitivity']:.3f}"
        ),
        (
            "- Macro explicit-normal control specificity: "
            f"{threshold['macro_cross_validated_explicit_control_specificity']:.3f}"
        ),
        f"- Single-split eligible concepts: {threshold['eligible_concept_count']}",
        (
            "- Macro holdout balanced accuracy: "
            f"{threshold['macro_holdout_balanced_accuracy']:.3f}"
        ),
        f"- Macro holdout sensitivity: {threshold['macro_holdout_sensitivity']:.3f}",
        f"- Macro holdout specificity: {threshold['macro_holdout_specificity']:.3f}",
        (
            "- Holdout top-20 mapped-concept recall: "
            f"{at_20['micro_concept_recall']:.3f}"
        ),
        (
            "- Holdout 3-5 diagnosis complete recall at 20: "
            f"{at_20['three_to_five_complete_recall']:.3f}"
        ),
        "",
        "These are waveform-only research metrics, not screenshot-agent accuracy.",
        "Thresholds are not deployment-installable and ECGFounder supplies no bbox.",
        "",
        "## Per-concept holdout metrics",
        "",
        "| Concept | Support + / control | CV BA | Sens | Control spec | AUROC |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    concepts = threshold["concepts"]
    evaluated = [
        (concept, value)
        for concept, value in concepts.items()
        if "cross_validation" in value
    ]
    evaluated.sort(
        key=lambda item: item[1]["cross_validation"]["balanced_accuracy"],
        reverse=True,
    )
    for concept, value in evaluated:
        cross_validation = value["cross_validation"]
        lines.append(
            f"| {concept} | {value['positive_count']} / "
            f"{value['control_count']} | "
            f"{cross_validation['balanced_accuracy']:.3f} | "
            f"{cross_validation['sensitivity']:.3f} | "
            f"{cross_validation['specificity']:.3f} | "
            f"{cross_validation['auroc']:.3f} |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], *, output: Path, markdown: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(report), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--split-seed", default="meeti-ecgfounder-heldout-v1")
    parser.add_argument("--calibration-fraction", type=float, default=0.60)
    parser.add_argument("--min-positive-per-split", type=int, default=5)
    parser.add_argument("--min-control-per-split", type=int, default=10)
    parser.add_argument("--cross-validation-folds", type=int, default=5)
    parser.add_argument(
        "--allow-ineligible",
        action="store_true",
        help=(
            "evaluate eligible rows only after validating complete cohort traversal; "
            "coverage and exclusions remain explicit in the report"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = args.output or (args.run_dir / "heldout-evaluation.json")
    markdown = args.markdown or (args.run_dir / "heldout-evaluation.md")
    try:
        report = evaluate(
            run_dir=args.run_dir,
            mapping_path=args.mapping,
            tasks_path=args.tasks,
            split_seed=args.split_seed,
            calibration_fraction=args.calibration_fraction,
            min_positive_per_split=max(1, args.min_positive_per_split),
            min_control_per_split=max(1, args.min_control_per_split),
            cross_validation_folds=max(2, args.cross_validation_folds),
            allow_ineligible=args.allow_ineligible,
        )
        write_report(report, output=output, markdown=markdown)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    threshold = report["threshold_evaluation"]
    ranking = report["ranking"]["holdout"]["at_k"]["20"]
    print(f"Evaluation status: {report['status']}")
    print(f"Protocol: {report['protocol']['fingerprint']}")
    cohort = report["cohort"]
    print(
        "Input eligibility: "
        f"{cohort['row_count']}/{cohort['target_row_count']} "
        f"({cohort['eligibility_fraction']:.3%})"
    )
    print(
        "Cross-validated metrics: "
        f"macro_BA={threshold['macro_cross_validated_balanced_accuracy']:.3f}, "
        f"macro_sensitivity={threshold['macro_cross_validated_sensitivity']:.3f}, "
        "explicit_control_specificity="
        f"{threshold['macro_cross_validated_explicit_control_specificity']:.3f}, "
        f"top20_recall={ranking['micro_concept_recall']:.3f}"
    )
    print(f"JSON: {output}")
    print(f"Markdown: {markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
