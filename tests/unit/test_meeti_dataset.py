"""Tests for the MEETI report -> ground-truth-label mapping.

These cover the pure ``classify_report`` vocabulary; the ``.mat`` reader (scipy)
is intentionally not exercised here so the suite stays dependency-light.
"""

from __future__ import annotations

from dicom_overlay.infrastructure.meeti_dataset import (
    ReportLabels,
    classify_report,
)


class TestSeverityMapping:
    def test_empty_report_is_normal(self) -> None:
        assert classify_report("").severity == "normal"
        assert classify_report("   ").severity == "normal"

    def test_plain_sinus_is_normal(self) -> None:
        labels = classify_report("Sinus rhythm. Normal ECG.")
        assert labels.severity == "normal"
        assert "no st elevation" in labels.negatives

    def test_wnl_and_within_normal_range_are_explicit_normal(self) -> None:
        for report in ("WNL.", "Within normal range."):
            labels = classify_report(report)
            assert labels.severity == "normal"
            assert "normal" in labels.keywords
            assert "normal" in labels.concepts

    def test_bradycardia_is_warning(self) -> None:
        labels = classify_report("Sinus bradycardia.")
        assert labels.severity == "warning"
        assert "bradycardia" in labels.keywords
        assert "heart_rate" in labels.target_axes

    def test_only_escalate_takes_max_severity(self) -> None:
        # Normal sinus + a critical finding -> critical, never downgraded.
        labels = classify_report("Sinus rhythm; Acute myocardial infarction.")
        assert labels.severity == "critical"

    def test_lvh_is_warning(self) -> None:
        labels = classify_report(
            "Sinus bradycardia; Left ventricular hypertrophy; "
            "Extensive T wave changes may be due to hypertrophy and/or ischemia."
        )
        assert labels.severity == "warning"
        assert "ischemia" in labels.keywords
        assert "st depression" not in labels.keywords
        assert "t wave changes" in labels.keywords
        assert "left ventricular hypertrophy" in labels.keywords
        assert "chamber_enlargement" in labels.target_axes

    def test_nonspecific_t_wave_changes_do_not_imply_ischemia_or_st_depression(self) -> None:
        labels = classify_report(
            "Sinus tachycardia, Inferior and anterior T wave changes are nonspecific, "
            "Borderline ECG"
        )
        assert labels.severity == "warning"
        assert "tachycardia" in labels.keywords
        assert "t wave changes" in labels.keywords
        assert "ischemia" not in labels.keywords
        assert "st depression" not in labels.keywords

    def test_st_depression_is_scored_separately_from_t_wave_changes(self) -> None:
        labels = classify_report("ST depression with lateral T wave abnormalities.")
        assert labels.severity == "warning"
        assert "st depression" in labels.keywords
        assert "t wave changes" in labels.keywords


class TestCantMiss:
    def test_stemi_detected(self) -> None:
        labels = classify_report("Acute ST-elevation myocardial infarction, anterior.")
        assert labels.severity == "critical"
        assert "STEMI" in labels.cant_miss
        assert "stemi_pattern" in labels.target_axes

    def test_complete_heart_block(self) -> None:
        labels = classify_report("Complete heart block with junctional escape.")
        assert "complete heart block" in labels.cant_miss
        assert labels.severity == "critical"

    def test_third_degree_block_alias(self) -> None:
        labels = classify_report("Third-degree AV block.")
        assert "complete heart block" in labels.cant_miss

    def test_vtach(self) -> None:
        labels = classify_report("Ventricular tachycardia.")
        assert "ventricular tachycardia" in labels.cant_miss
        assert labels.severity == "critical"

    def test_hyperkalemia(self) -> None:
        labels = classify_report("Peaked T waves suggestive of hyperkalemia.")
        assert "hyperkalemia" in labels.cant_miss

    def test_long_qt(self) -> None:
        labels = classify_report("Prolonged QT interval.")
        assert "long QT" in labels.cant_miss

    def test_cant_miss_aligns_with_harness_reference(self) -> None:
        from dicom_overlay.domain.entities import Modality
        from dicom_overlay.infrastructure.eval_harness import CANT_MISS

        reference = set(CANT_MISS[Modality.EKG])
        produced = set()
        for report in (
            "Acute STEMI",
            "Complete heart block",
            "Ventricular tachycardia",
            "Hyperkalemia",
            "Prolonged QT",
            "Wellens syndrome",
        ):
            produced |= set(classify_report(report).cant_miss)
        assert produced == reference


class TestNegationGuard:
    def test_no_acute_infarct_not_critical(self) -> None:
        labels = classify_report("Sinus rhythm; no acute ST-elevation.")
        assert labels.severity == "normal"
        assert "STEMI" not in labels.cant_miss

    def test_ruled_out_block(self) -> None:
        labels = classify_report("Sinus rhythm; no evidence of complete heart block.")
        assert "complete heart block" not in labels.cant_miss


class TestWarnings:
    def test_atrial_fibrillation(self) -> None:
        labels = classify_report("Atrial fibrillation with rapid ventricular response.")
        assert labels.severity == "warning"
        assert "atrial fibrillation" in labels.keywords
        assert "regularity" in labels.target_axes

    def test_lbbb(self) -> None:
        labels = classify_report("Left bundle branch block.")
        assert labels.severity == "warning"
        assert "qrs_duration" in labels.target_axes

    def test_first_degree_block(self) -> None:
        labels = classify_report("First degree AV block.")
        assert labels.severity == "warning"
        assert "av_block" in labels.target_axes

    def test_returns_frozen_dataclass(self) -> None:
        labels = classify_report("Sinus rhythm.")
        assert isinstance(labels, ReportLabels)
