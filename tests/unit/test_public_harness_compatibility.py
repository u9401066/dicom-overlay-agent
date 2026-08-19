from __future__ import annotations

import importlib

import pytest

WRAPPER_MAPPINGS = (
    (
        "dicom_overlay.domain.entities",
        "medical_image_harness.models",
        (
            "AnalysisResult",
            "ChecklistItem",
            "ClaimType",
            "Evidence",
            "Finding",
            "Modality",
            "Observation",
            "Polarity",
            "RegionRect",
            "Severity",
            "UserRegionAnnotation",
            "VerificationStatus",
        ),
    ),
    (
        "dicom_overlay.domain.hooks",
        "medical_image_harness.hooks",
        ("AnalyzeHook", "AnalyzeRequest", "HookError"),
    ),
    (
        "dicom_overlay.domain.services",
        "medical_image_harness.protocols",
        ("VisionAnalyzerService",),
    ),
    (
        "dicom_overlay.domain.ekg_layout",
        "medical_image_harness.ekg_layout",
        (
            "STANDARD_EKG_LEADS",
            "EkgLeadInventory",
            "EkgLeadRegion",
            "canonical_ekg_lead_name",
            "parse_ekg_lead_inventory",
        ),
    ),
    (
        "dicom_overlay.domain.modality_profile",
        "medical_image_harness.profiles",
        (
            "ModalityProfile",
            "ModalityRegistry",
            "build_registry",
            "default_registry",
            "get_active_registry",
            "set_active_registry",
        ),
    ),
    (
        "dicom_overlay.domain.clinical_rules",
        "medical_image_harness.clinical_rules",
        (
            "ClinicalConsistencyEngine",
            "ClinicalRule",
            "ConditionError",
            "RuleCondition",
            "RuleViolation",
            "builtin_rules",
            "default_engine",
            "group_by_modality",
        ),
    ),
    (
        "dicom_overlay.application.multi_pass",
        "medical_image_harness.multipass",
        (
            "DEFAULT_MAX_EKG_SYSTEMATIC_PROBES",
            "DEFAULT_MAX_LOCAL_CANDIDATE_AREA",
            "DEFAULT_MAX_NORMAL_SAFETY_PROBES",
            "DEFAULT_MIN_REFINE_CROP_EDGE_PX",
            "DEFAULT_MIN_ZOOM_SOURCE_EDGE_PX",
            "BboxCalibrator",
            "ImageCropper",
            "MultiPassAnalyzer",
            "MultiPassInterpreter",
            "RefinementAction",
            "RefinementAnalyzer",
            "RefinementDelta",
            "RefinementResult",
            "ReportFinalizer",
            "apply_refinement_delta",
            "build_manual_zoom_message",
            "clamp_unit",
            "covering_region",
            "expand_crop_to_min_source_edge",
            "needs_manual_zoom",
            "pad_region",
            "reconcile_final_report",
            "region_source_edge_px",
            "remap_bbox",
            "select_ekg_systematic_probe_regions",
            "select_local_candidate_targets",
            "select_normal_safety_probe_regions",
            "select_zoom_targets",
        ),
    ),
    (
        "dicom_overlay.application.rhythm_strip",
        "medical_image_harness.rhythm_strip",
        (
            "RHYTHM_AXES",
            "RhythmStripRefiningAnalyzer",
            "merge_rhythm_strip",
            "refine_rhythm_strip",
            "resolve_rhythm_strip_region",
        ),
    ),
    (
        "dicom_overlay.application.interpretation_harness",
        "medical_image_harness.prompting",
        (
            "InterpretationContext",
            "build_followup_prompt",
            "build_minimal_control_prompt",
            "summarize_result_for_followup",
        ),
    ),
    (
        "dicom_overlay.infrastructure.bbox_signal_calibrator",
        "medical_image_harness.bbox_signal_calibrator",
        ("calibrate_ekg_bboxes",),
    ),
    (
        "dicom_overlay.infrastructure.clinical_rule_loader",
        "medical_image_harness.rule_loader",
        (
            "RULE_PACK_GLOB",
            "build_clinical_engine",
            "load_rule_pack_dir",
            "merge_rules",
        ),
    ),
    (
        "dicom_overlay.infrastructure.hooks.output_validator",
        "medical_image_harness.output_validation",
        ("OutputValidator",),
    ),
    (
        "dicom_overlay.infrastructure.hooks.clinical_consistency",
        "medical_image_harness.clinical_consistency",
        ("ClinicalConsistencyHook",),
    ),
    (
        "dicom_overlay.infrastructure.hooks.bbox_calibration",
        "medical_image_harness.bbox_calibration",
        ("BboxCalibrationHook", "BboxCalibrator"),
    ),
    (
        "dicom_overlay.infrastructure.hooks.input_guard",
        "medical_image_harness.input_validation",
        ("InputGuard",),
    ),
)


@pytest.mark.parametrize(("private_name", "public_name", "symbols"), WRAPPER_MAPPINGS)
def test_legacy_imports_are_identity_preserving_public_exports(
    private_name: str,
    public_name: str,
    symbols: tuple[str, ...],
) -> None:
    private_module = importlib.import_module(private_name)
    public_module = importlib.import_module(public_name)

    for symbol in symbols:
        assert getattr(private_module, symbol) is getattr(public_module, symbol)
        exports = getattr(private_module, "__all__", ())
        if exports:
            assert symbol in exports

    identity_exports = {
        symbol
        for symbol in getattr(private_module, "__all__", ())
        if hasattr(public_module, symbol)
        and getattr(private_module, symbol) is getattr(public_module, symbol)
    }
    assert identity_exports == set(symbols)
