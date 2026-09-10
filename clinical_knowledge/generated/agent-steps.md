# Agent clinical steps

Registry SHA-256: `d22a03e037293636c86ca029452a8486f93f5625cb5655b3381088b8cc1fc22c`
Registry digest scope: `canonical-input-documents-v1`

This generated view contains no evaluation gold labels or scorer aliases.

## `cxr.pneumothorax_undercall.v1`

- [verify_assertion] Separate affirmed pneumothorax from negated and uncertain wording.
- [inspect_pleural_evidence] Verify pleural evidence and exclude folds, clothing, scapular edges, and exposure artifacts.
- [assess_extent_and_tension_signs] State visible side and extent; do not infer tension physiology without supporting image and clinical evidence.
- [check_capture_completeness] Mark cropped apices or chest wall not assessable and do not create negative claims for unseen regions.
- [reconcile_critical_review] Align pleura, finding, summary, critical review, and tight evidence boxes.

## `cxr.widened_mediastinum.v1`

- [verify_projection_quality] Check AP/PA projection, rotation, inspiration, magnification, and supine technique before judging width.
- [verify_mediastinal_observation] Confirm the contour abnormality on the source image and place a tight box on relevant anatomy.
- [inspect_supporting_aortic_signs] Inspect visible aortic contour, apical cap, tube or tracheal displacement, and pleural fluid without treating absence as exclusion.
- [compare_mediastinal_differentials] Compare technical, aortic, mass, nodal, fat, hemorrhagic, and structural explanations.
- [reconcile_warning_review] Set at least warning review, keep the finding nonspecific, and state concrete clinical or definitive-imaging context needed.

## `ekg.explicit_stemi_undercall.v1`

- [classify_assertion] Separate affirmed acute injury from negated, uncertain, and differential wording.
- [verify_visible_pattern] Verify the claimed morphology in named visible contiguous leads and keep boxes on source evidence.
- [assess_capture_completeness] Preserve urgent triage while marking unsupported territory or axes not assessable on partial captures.
- [separate_injury_from_infarction] Distinguish an image pattern of acute injury from a clinical MI diagnosis requiring additional evidence.
- [reconcile_all_outputs] Align findings, checklist, summary, critical severity, review state, and traceable evidence.

## `ekg.peaked_t_hyperkalemia.v1`

- [verify_t_morphology] Confirm repeatable T-wave morphology in named visible leads and reject gain, crop, overlap, or noise artifacts.
- [inventory_associated_changes] Check visible P waves, PR, QRS, ST-T merging, rhythm, and rate; mark unavailable measurements not assessable.
- [compare_repolarization_differentials] Compare potassium, ischemic, repolarization, hypertrophy, and technical explanations without diagnosing potassium from ECG alone.
- [reconcile_warning_floor] Align checklist and summary, set at least warning severity, and require focused clinician review.

## `ekg.possible_hyperacute_ischemia_triage.v1`

- [verify_regional_morphology] Confirm repeatable regional T-wave morphology and supporting ST or reciprocal evidence in visible leads.
- [assess_temporal_and_capture_limits] Mark missing leads, territories, serial change, and unreadable measurements not assessable.
- [compare_urgent_mimics] Compare acute coronary occlusion with potassium, repolarization, hypertrophy, conduction, and technical alternatives.
- [preserve_uncertainty_with_urgency] Keep the differential uncertain, set critical review, and state the visible evidence and missing data that drive it.

## `ekg.st_elevation_not_flagged.v1`

- [verify_capture_support] Inventory only visible leads and record every crop, label, calibration, or artifact limitation.
- [verify_st_observation] Confirm repeatable ST deviation in named visible leads; do not infer unseen leads.
- [compare_st_mimics] Compare acute ischemia with repolarization, LVH, conduction, pacing, pericardial, and artifact alternatives.
- [reconcile_triage] Make ST, ischemia, summary, severity, and review state internally consistent without converting observation into MI.

## `ekg.uncertain_acute_injury_with_st_elevation_triage.v1`

- [establish_st_evidence] Confirm abnormal ST elevation in named visible leads and verify every evidence box.
- [classify_acute_differential] Separate asserted, negated, and unresolved acute injury, ischemia, or occlusion wording.
- [compare_st_elevation_differentials] Compare ischemic, repolarization, pericardial, hypertrophy, conduction, ventricular, aneurysm, electrolyte, and artifact explanations.
- [check_territory_completeness] Restrict localization and negative claims to visible leads; mark cropped territories not assessable.
- [reconcile_critical_triage] Preserve uncertainty, set critical review, and name the serial ECG, symptom, and biomarker context still needed.
