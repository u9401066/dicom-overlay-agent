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
    def test_empty_report_is_ungradable_not_normal(self) -> None:
        for report in ("", "   "):
            labels = classify_report(report)
            assert labels.severity == "info"
            assert labels.label_status == "ungradable"
            assert labels.ungradable_reasons == ("empty_report",)
            assert labels.negatives == ()

    def test_plain_sinus_is_normal(self) -> None:
        labels = classify_report("Sinus rhythm. Normal ECG.")
        assert labels.severity == "normal"
        assert labels.negatives == ()

    def test_sinus_rhythm_alone_does_not_assert_a_normal_ecg(self) -> None:
        labels = classify_report("Sinus rhythm.")
        assert labels.severity == "info"
        assert labels.label_status == "asserted"
        assert labels.keywords == ("sinus rhythm",)
        assert labels.negatives == ()

    def test_abbreviated_probable_early_repolarization_is_not_normal(self) -> None:
        labels = classify_report(
            "Sinus rhythm; ST elev, probable normal early repol pattern."
        )
        assert labels.severity == "info"
        assert labels.label_status == "partially_uncertain"
        assert "st_elevation" in labels.uncertain_concepts
        assert "early_repol" in labels.uncertain_concepts
        assert labels.negatives == ()

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
        assert "ischemia" not in labels.keywords
        assert "ischemia" in labels.uncertain_concepts
        assert "st depression" not in labels.keywords
        assert "t wave changes" in labels.keywords
        assert "left ventricular hypertrophy" in labels.keywords
        assert "chamber_enlargement" in labels.target_axes

    def test_comma_separated_uncertainty_does_not_leak_backward(self) -> None:
        labels = classify_report(
            "Sinus bradycardia, Right bundle branch block, "
            "Possible LVH with secondary repolarization abnormality"
        )
        assert "right bundle branch block" in labels.keywords
        assert "rbbb" in labels.concepts
        assert "lvh" in labels.uncertain_concepts

    def test_meeti_abbreviations_are_recognized(self) -> None:
        labels = classify_report(
            "Sinus rhythm with PACs with 1st degree A-V block, "
            "Leftward axis, IV conduction defect, Low QRS voltages"
        )
        assert {
            "pac",
            "first_degree_block",
            "axis_deviation",
            "iv_conduction_delay",
            "low_voltage",
        }.issubset(labels.concepts)

    def test_atrial_pacing_is_not_ungradable_abnormal_text(self) -> None:
        labels = classify_report("Atrial pacing, Abnormal ECG")
        assert labels.severity == "warning"
        assert labels.label_status == "asserted"
        assert labels.concepts == ("paced",)

    def test_identified_uncertain_findings_are_not_called_unspecified(self) -> None:
        labels = classify_report(
            "Probable supraventricular tachycardia, Possible LVH, Abnormal ECG"
        )
        assert labels.severity == "info"
        assert labels.label_status == "uncertain"
        assert labels.ungradable_reasons == ()

    def test_nonspecific_t_wave_changes_do_not_imply_ischemia_or_st_depression(
        self,
    ) -> None:
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

    def test_unmatched_report_is_ungradable_not_normal(self) -> None:
        labels = classify_report("Technician comment only.")
        assert labels.severity == "info"
        assert labels.label_status == "ungradable"
        assert labels.concepts == ()
        assert labels.ungradable_reasons == ("unmatched_report",)
        assert labels.negatives == ()

    def test_abnormal_early_r_wave_transition_is_not_normal(self) -> None:
        labels = classify_report(
            "Sinus rhythm, Abnormal R-wave progression, early transition"
        )
        assert labels.severity == "warning"
        assert labels.label_status == "asserted"
        assert "early_r_transition" in labels.concepts
        assert "early transition" in labels.keywords

    def test_unsuitable_leads_are_not_auto_normal(self) -> None:
        labels = classify_report(
            "Sinus rhythm. Leads V1-V3 are unsuitable for analysis."
        )
        assert labels.severity == "info"
        assert labels.label_status == "partially_ungradable"
        assert "unsuitable_leads" in labels.ungradable_reasons
        assert labels.negatives == ()

    def test_possible_infarct_is_uncertain_not_positive(self) -> None:
        labels = classify_report("Possible anterior infarct; otherwise normal ECG.")
        assert labels.severity == "info"
        assert labels.label_status == "partially_uncertain"
        assert "infarct" in labels.uncertain_concepts
        assert "infarct" not in labels.keywords
        assert labels.cant_miss == ()
        assert labels.negatives == ()


class TestCantMiss:
    def test_stemi_detected(self) -> None:
        labels = classify_report("Acute ST-elevation myocardial infarction, anterior.")
        assert labels.severity == "critical"
        assert "STEMI" in labels.cant_miss
        assert "stemi_pattern" in labels.target_axes

    def test_generic_st_elevation_is_not_automatically_stemi(self) -> None:
        labels = classify_report("Inferior ST elevation; abnormal ECG.")
        assert labels.severity == "warning"
        assert "st elevation" in labels.keywords
        assert "stemi" not in labels.keywords
        assert labels.cant_miss == ()

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
        labels = classify_report("Hyperkalemia with peaked T waves.")
        assert "hyperkalemia" in labels.cant_miss

    def test_suggestive_hyperkalemia_is_not_cant_miss_ground_truth(self) -> None:
        labels = classify_report("Peaked T waves suggestive of hyperkalemia.")
        assert labels.severity == "warning"
        assert "peaked t wave" in labels.keywords
        assert "hyperkalemia" in labels.uncertain_concepts
        assert "hyperkalemia" not in labels.keywords
        assert "hyperkalemia" not in labels.cant_miss

    def test_meeti_suggest_hyperkalemia_wording_stays_uncertain(self) -> None:
        labels = classify_report(
            "Sinus bradycardia; Probable left atrial enlargement; "
            "Tall T waves suggest hyperkalemia."
        )
        assert labels.severity == "warning"
        assert "tall t wave" in labels.keywords
        assert "hyperkalemia" in labels.uncertain_concepts
        assert "hyperkalemia" not in labels.keywords
        assert labels.cant_miss == ()

    def test_long_qt(self) -> None:
        labels = classify_report("Prolonged QT interval.")
        assert labels.severity == "warning"
        assert labels.cant_miss == ()

    def test_high_risk_long_qt_is_cant_miss(self) -> None:
        labels = classify_report("QTc 520 ms; prolonged QT interval.")
        assert labels.severity == "critical"
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
            "QTc 520 ms; prolonged QT",
            "Wellens syndrome",
        ):
            produced |= set(classify_report(report).cant_miss)
        assert produced == reference


class TestNegationGuard:
    def test_no_acute_infarct_not_critical(self) -> None:
        labels = classify_report("Sinus rhythm; no acute ST-elevation.")
        assert labels.severity == "info"
        assert "STEMI" not in labels.cant_miss

    def test_ruled_out_block(self) -> None:
        labels = classify_report("Sinus rhythm; no evidence of complete heart block.")
        assert "complete heart block" not in labels.cant_miss

    def test_st_elevation_without_stemi_is_not_critical(self) -> None:
        labels = classify_report(
            "ST elevation is present, but without STEMI; early repolarization."
        )
        assert labels.severity == "info"
        assert "st_elevation" in labels.uncertain_concepts
        assert "STEMI" not in labels.cant_miss

    def test_possible_early_repolarization_is_uncertain(self) -> None:
        labels = classify_report("Possible early repolarization.")
        assert labels.severity == "info"
        assert labels.label_status == "uncertain"
        assert labels.keywords == ()
        assert labels.uncertain_concepts == ("early_repol",)
        assert labels.cant_miss == ()

    def test_early_repolarization_explanation_does_not_create_stemi(self) -> None:
        labels = classify_report(
            "ST elevation is consistent with early repolarization."
        )
        assert labels.severity == "info"
        assert "early repolarization" in labels.keywords
        assert "st_elevation" in labels.uncertain_concepts
        assert "STEMI" not in labels.cant_miss

    def test_meeti_early_repolarization_differential_is_not_stemi(self) -> None:
        labels = classify_report(
            "SINUS RHYTHM, MARKED LEFT AXIS DEVIATION, RIGHT BUNDLE BRANCH "
            "BLOCK WITH LEFT ANTERIOR FASCICULAR BLOCK, Inferior and lateral "
            "ST elevation, POSSIBLE EARLY REPOLARIZATION, Summary: ABNORMAL ECG"
        )
        assert labels.severity == "warning"
        assert labels.cant_miss == ()
        assert "stemi" not in labels.keywords
        assert "st_elevation" in labels.uncertain_concepts

    def test_pericarditis_explanation_is_not_stemi(self) -> None:
        labels = classify_report("ST elevation suggests acute pericarditis.")
        assert labels.severity == "info"
        assert labels.cant_miss == ()
        assert "st_elevation" in labels.uncertain_concepts

    def test_consider_acute_mi_is_uncertain_not_asserted_ground_truth(self) -> None:
        labels = classify_report("CONSIDER ACUTE ST ELEVATION MI.")
        assert labels.severity == "critical"
        assert labels.cant_miss == ()
        assert labels.urgent_concerns == ("STEMI",)
        assert "stemi" in labels.uncertain_concepts

    def test_consider_acute_infarct_is_not_relabeled_as_stemi(self) -> None:
        labels = classify_report("Marked ST depression, CONSIDER ACUTE INFARCT.")
        assert labels.severity == "critical"
        assert labels.cant_miss == ()
        assert labels.urgent_concerns == ("acute MI",)
        assert "acute_mi" in labels.uncertain_concepts
        assert "stemi" not in labels.uncertain_concepts

    def test_stemi_banner_deduplicates_generic_acute_mi_urgency(self) -> None:
        labels = classify_report(
            "CONSIDER ACUTE ST ELEVATION MI, Inferior ST elevation, "
            "CONSIDER ACUTE INFARCT"
        )
        assert labels.urgent_concerns == ("STEMI",)

    def test_q_waves_with_possible_lvh_cause_stay_uncertain(self) -> None:
        labels = classify_report("Anterior Q waves, possibly due to LVH.")
        assert "q waves" not in labels.keywords
        assert "q_waves" in labels.uncertain_concepts

    def test_hyphenated_av_dissociation_is_recognized(self) -> None:
        labels = classify_report("A-V dissociation, Abnormal ECG")
        assert labels.severity == "warning"
        assert "av_dissociation" in labels.concepts
        assert labels.ungradable_reasons == ()

    def test_manifest_fields_keep_uncertainty_and_urgency_auditable(self) -> None:
        fields = classify_report("CONSIDER ACUTE ST ELEVATION MI.").manifest_fields()
        assert fields["label_status"] == "uncertain"
        assert fields["cant_miss"] == []
        assert fields["urgent_concerns"] == ["STEMI"]
        assert "stemi" in fields["uncertain_concepts"]
        assert "st_elevation" in fields["uncertain_concepts"]


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
