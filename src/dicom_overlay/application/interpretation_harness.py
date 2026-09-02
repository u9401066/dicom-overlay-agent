"""Prompt and context harness for medical image interpretation sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dicom_overlay.domain.entities import AnalysisResult, Modality, Severity


# Eval-only region scope used when a deliberately cropped ECG has no lead name
# that can be guaranteed from geometry alone.  It is intentionally not a
# clinical region name: prompts must keep ``finding.regions`` empty while still
# giving InputGuard a non-empty, fail-closed scope.
PARTIAL_ECG_VISIBLE_PIXELS_SCOPE = "partial_ecg_visible_pixels_no_named_leads"

PROFESSIONAL_CO_READER_GUIDANCE = (
    "Act as professional image-interpretation software assisting a specialist "
    "physician. Complete the medically relevant review of the visible image; do "
    "not refuse solely because the task is medical or because you are an AI. "
    "Do not add generic medical-advice disclaimers or tell the specialist to "
    "consult another professional. State only concrete image limitations, "
    "uncertainty, missing clinical inputs, and focused review actions that affect "
    "this case."
)


def _partial_ecg_input_guidance(
    modality: Modality,
    valid_regions: list[str],
) -> str:
    if modality.value != "EKG" or valid_regions != [PARTIAL_ECG_VISIBLE_PIXELS_SCOPE]:
        return ""
    return (
        "This is a deliberately incomplete/cropped ECG robustness case. "
        "The scope token describes visible pixels, not a verified lead name. "
        "Do not copy that token into finding.regions; use regions=[] and ground "
        "any visible abnormality only with tight bboxes. Do not infer or locally "
        "reconstruct a complete 12-lead inventory. Use layout format partial or "
        "non_standard with leads=[] unless a separate trusted lead map is supplied. "
        "Set incomplete=true and review_required=true with concrete reasons. For "
        "a checklist axis that depends on unavailable leads or resolution, use "
        "not_assessable/indeterminate with info status; a visibly supported "
        "abnormal axis may remain warning or critical, never a fabricated normal. "
        "Describe the concrete visible degradation (which edge is cropped, a "
        "masked label margin, an isolated horizontal band, or low resolution); a "
        "generic incomplete-image template is insufficient.\n"
    )


EKG_LVH_BALANCE_GUIDANCE = (
    "High voltage alone cannot establish definite LVH, and a missing calibration "
    "pulse prevents a definite LVH claim. When a standard ECG grid and appropriate "
    "labeled leads show reproducible LVH-compatible voltage in more than one "
    "qualifying lead group plus secondary discordant ST-T/strain, axis deviation, "
    "or other supporting morphology, do not suppress the candidate solely because "
    "the calibration pulse is missing. Retain a low-confidence finding labeled "
    "'Possible LVH-compatible pattern' with a concrete calibration/criteria "
    "reviewer question; choose severity from visible support and do not automatically "
    "force warning. Assess and report R-wave progression independently; voltage "
    "must not displace it."
)

EKG_PRECORDIAL_REVIEW_GUIDANCE = (
    "For every crop containing mapped precordial leads, inspect the visible "
    "V1-V4 sequence for both R/S transition and ST-T/T-wave morphology, "
    "regardless of the coarse hypothesis. Poor R-wave progression requires a "
    "lack of the expected transition across V1-V4; deep S waves or small R "
    "waves in V1/V2 alone are insufficient. If R amplitude increases and R "
    "becomes dominant by V3/V4, retract poor R-wave progression. Separately "
    "check V2-V4 for persistent T-wave inversion or flattening and nonspecific "
    "ST-T change across adjacent beats/leads, distinguishing reproducible "
    "waveform-locked morphology from baseline wander, grid interference, and "
    "isolated noise. Absence of acute ST elevation or reciprocal change can "
    "exclude an acute pattern but cannot exclude a reproducible nonspecific "
    "ST-T/T-wave abnormality. If inversion, flattening, or discordant "
    "repolarization morphology recurs across adjacent beats in at least two "
    "mapped contiguous or anatomically related leads, report a low-confidence "
    "nonspecific ST-T/T-wave change after comparing benign variation and noise; "
    "use the existing non-urgent severity contract and do not imply acute "
    "ischemia. One lead or non-reproducible noise alone is not a finding."
)


@dataclass(frozen=True)
class InterpretationContext:
    """Compact state carried across multiple turns for the same image."""

    modality: Modality
    summary: str
    severity: Severity
    finding_summaries: list[str] = field(default_factory=list)
    model_used: str = ""

    @classmethod
    def from_result(cls, result: AnalysisResult) -> InterpretationContext:
        return cls(
            modality=result.modality,
            summary=result.summary,
            severity=result.severity,
            finding_summaries=[
                (
                    f"{finding.id}: {finding.label} "
                    f"({finding.severity.value}; regions={','.join(finding.regions)}) "
                    f"- {finding.detail}"
                )
                for finding in result.findings
            ],
            model_used=result.model_used,
        )


def build_initial_analysis_prompt(
    *,
    modality: Modality,
    valid_regions: list[str],
    skill_name: str,
    skill_prompt: str,
    waveform_artifact_id: str = "",
    waveform_lead_mode: str = "",
    waveform_evidence_nonce: str = "",
    bbox_source_image_sha256: str = "",
    bbox_evidence_nonce: str = "",
) -> str:
    """Build the initial structured analysis prompt for an attached image."""
    allowed_regions = ", ".join(valid_regions) if valid_regions else "(none provided)"
    partial_input_guidance = _partial_ecg_input_guidance(modality, valid_regions)
    waveform_protocol = ""
    if waveform_artifact_id:
        waveform_protocol = (
            "\nMatched raw-waveform evidence is available for this EKG case:\n"
            "- First inspect the attached image independently and form a provisional "
            "visual interpretation.\n"
            "- Then call ecg_founder_analyze_waveform exactly once with "
            f"artifact_id='{waveform_artifact_id}', "
            f"lead_mode='{waveform_lead_mode or '12_lead'}', and "
            f"evidence_nonce='{waveform_evidence_nonce}', and max_predictions=10. "
            "Do not alter or invent the artifact id or evidence nonce.\n"
            "- After that tool result returns, never call it again for this nonce; "
            "duplicate attempts are suppressed and waste the bounded initial-turn "
            "budget. Proceed directly to visual reconciliation, bbox validation "
            "when needed, and the final JSON.\n"
            "- Treat returned probabilities only as supporting waveform evidence. "
            "An uncalibrated_score is neither a positive nor a negative diagnosis.\n"
            "- A ranked normal/otherwise-normal label, or omission of a condition "
            "from top-k, is not negative evidence. It cannot override visually "
            "plausible contiguous ST-T, conduction, or voltage morphology.\n"
            "- Explicitly reconcile agreement or disagreement in the summary and "
            "retain uncertainty when the image and waveform evidence differ.\n"
            "- For each clinically relevant ranked candidate, explicitly classify "
            "the screenshot relationship as visually supported, visually "
            "unsupported, or not assessable. Do not silently leave that checklist "
            "axis normal or absent when the two evidence sources disagree.\n"
            "- Use ranked labels to route visual checks, not to set the conclusion. "
            "Test defining morphology and nearby confounders across rhythm/ectopy, "
            "QRS conduction, high versus low voltage, Q/QS or R-wave progression, "
            "and ST-T patterns without giving any candidate automatic priority.\n"
            "- Irregular R-R timing alone cannot diagnose atrial fibrillation; "
            "ectopy, missed peaks, pacing, and artifact can also make it irregular. "
            "If a top-three candidate is PVC/PAC/ectopy and AF/flutter is not in "
            "the top three, explicitly test the ectopic-beat explanation and do "
            "not infer AF solely from irregular timing or poor P-wave visibility.\n"
            "- If rhythm_measurement is present with status=ok, use its unrounded "
            "heart_rate_bpm_from_median_rr as supporting rate-category evidence; "
            "a value above 100 bpm is tachycardic even when a visual estimate "
            "rounds to about 100. It cannot diagnose the rhythm.\n"
            "- ECGFounder has no image localization. Every finding bbox must still "
            "be grounded in the attached image and validated by dicom_bbox_validate.\n"
        )
    return (
        f"Use the {skill_name} instructions below to analyze the attached image.\n\n"
        f"{skill_prompt}\n\n"
        f"{PROFESSIONAL_CO_READER_GUIDANCE}\n\n"
        "Run this systematic image interpretation protocol:\n"
        f"{partial_input_guidance}"
        "This is the bounded initial whole-image turn. Return the complete coarse "
        "JSON promptly; the app will schedule separate crop/refine turns. Do not "
        "simulate crop work or delay for optional analysis beyond the tools "
        "explicitly required below.\n"
        "1. Confirm modality and image quality before interpreting.\n"
        "2. Inspect the image systematically using the modality checklist.\n"
        "3. Report only findings visible in the image.\n"
        "4. Put normal and negative observations in summary/checklist, not in "
        "overlay findings. For every abnormal or unresolved finding, include "
        "label, detail, severity, regions, and tight bboxes with normalized 0-1 "
        "coordinates (x, y, w, h).\n"
        "5. Before finalizing any abnormal or uncertain bbox, call the "
        "dicom_bbox_validate tool with modality set to the requested modality, "
        f"source_image_sha256='{bbox_source_image_sha256}', and "
        f"evidence_nonce='{bbox_evidence_nonce}', "
        "and copy only its accepted full-image boxes "
        "into the corresponding finding. Copy both binding values exactly; never "
        "invent or reuse them. The final bbox multiset must exactly match the "
        "accepted boxes from one validator call, not a subset or superset; validate "
        "only boxes you intend to retain. Never substitute crop-local coordinates.\n"
        "6. Provide next_steps that explain what the user should inspect next.\n"
        "7. A normal or within-normal-limits interpretation is valid; never invent "
        "an abnormality merely to return a finding.\n"
        "Top-level severity describes clinical abnormality, not screenshot quality. "
        "When no actionable abnormality or unresolved visual candidate is present, "
        "use severity normal even if image_quality is limited or incomplete is true. "
        "Do not use info solely for artifact, missing measurements, or other "
        "limitations.\n"
        "8. For a non-urgent unresolved candidate, set severity to info, confidence "
        "to low, include a tight bbox, and provide a concrete question for human "
        "review. If the unresolved differential is time-critical, severity is the "
        "triage priority rather than diagnostic certainty: use critical with "
        "cautious wording, confidence, and a concrete urgent-review question. Do "
        "not phrase an uncertain candidate as a confirmed diagnosis.\n"
        "9. Set incomplete=true and list incomplete_reasons when image quality, "
        "labels, or captured leads are insufficient.\n"
        "10. Use cautious medical language and do not overstate certainty.\n\n"
        f"{waveform_protocol}"
        "Return a single JSON object only. Do not wrap it in markdown. Use "
        "concise clinical English for every JSON string value so terminology "
        "remains stable for audit and scoring.\n"
        f"modality must be '{modality.value}'.\n"
        f"Only reference region names from this allow-list: {allowed_regions}.\n"
        "Required top-level keys: modality, summary, severity, findings, "
        "checklist, layout, next_steps, image_quality, model_used, incomplete, "
        "incomplete_reasons. Before sending, verify that each layout bbox has four "
        "numbers inside [x,y,w,h] and that all JSON delimiters are balanced.\n"
    )


def build_coarse_analysis_prompt(
    *,
    modality: Modality,
    valid_regions: list[str],
    waveform_artifact_id: str = "",
    waveform_lead_mode: str = "",
    waveform_evidence_nonce: str = "",
    bbox_source_image_sha256: str = "",
    bbox_evidence_nonce: str = "",
) -> str:
    """Build the bounded first-look prompt used by the multi-pass analyzer."""

    allowed_regions = ", ".join(valid_regions) if valid_regions else "(none provided)"
    partial_input_guidance = _partial_ecg_input_guidance(modality, valid_regions)
    waveform_protocol = ""
    if waveform_artifact_id:
        waveform_protocol = (
            "After an independent image review, call "
            "ecg_founder_analyze_waveform exactly once with "
            f"artifact_id='{waveform_artifact_id}', "
            f"lead_mode='{waveform_lead_mode or '12_lead'}', "
            f"evidence_nonce='{waveform_evidence_nonce}', and max_predictions=5. "
            "Use its top candidates only to route visual checks; a score is not a "
            "diagnosis and has no spatial localization. Never call it twice. "
            "A normal/otherwise-normal label or top-k omission is not negative "
            "evidence and cannot override visible contiguous morphology. "
            "If it returns ineligible, continue image-only and do not create a "
            "finding from unavailable waveform evidence. "
            "Explicitly test ectopy before atrial fibrillation when PVC/PAC is "
            "ranked and AF/flutter is not.\n"
        )
    ekg_contract = ""
    if modality.value == "EKG":
        ekg_contract = (
            'For a full-width 12-row EKG strip, use compact layout={"format":'
            '"12lead_12x1","lead_order":["I","II","III","aVR","aVL",'
            '"aVF","V1","V2","V3","V4","V5","V6"],'
            '"rhythm_strip_leads":[],"rhythm_strip_bbox":null,"leads":[]}; '
            "do not output "
            "per-lead bboxes. Local pixel "
            "evidence will derive row geometry. For any other EKG layout, include "
            "only visibly labeled leads with normalized [x,y,w,h] bboxes. Check "
            "rhythm/ectopy, conduction, high versus low voltage, Q/QS or R-wave "
            "progression, and ST-T morphology without favoring one category. "
            "Treat an isolated one-lead or non-reproducible concave/nonspecific "
            "ST-T variation as WNL after comparing benign variation and noise. "
            "Do not use absent acute ST elevation or reciprocal change to exclude "
            "a separate reproducible nonspecific ST-T/T-wave abnormality. Before "
            "choosing "
            "the top three, test contiguous territories for acute ST elevation, "
            "reciprocal depression, and hyperacute morphology. If a time-critical "
            "pattern remains visually plausible, reserve a finding slot and label "
            "it 'Possible acute ST-elevation ischemic pattern (STEMI cannot be "
            "excluded)' with critical triage severity and low confidence. "
            "Irregular R-R timing or poorly seen P waves alone cannot diagnose AF. "
            "At any abrupt abnormal interval, first separate the dominant intrinsic "
            "beat class from intermittent abnormal beats. Count unique horizontal "
            "timestamps, not the same beat repeated across lead rows. Three or more "
            "consecutive broad beats are required before proposing a ventricular "
            "run; one or two abnormal broad beats still require an intermittent "
            "pacing versus PVC, aberrancy, fusion, and artifact comparison. Normal "
            "intrinsic beats do not exclude demand/intermittent pacing. Treat a "
            "sharp narrow deflection immediately before an abnormal QRS as a pacing-"
            "spike candidate, not automatically as a P wave. Evaluate NSVT/VT "
            "versus artifact or conduction before attributing secondary ST-T "
            "distortion to ischemia. "
            "Do not call sinus from regular timing alone: require repeatable P "
            "waves before QRS complexes with a stable P-QRS relationship in at "
            "least one clear lead. If neither sinus nor AF/flutter has positive "
            "visible morphology, preserve other/indeterminate rather than forcing "
            "either diagnosis. "
            "When lead II and the ECG grid are clear, classify PR qualitatively "
            "across multiple beats and inspect premature P-QRS complexes, coupling, "
            "and pauses; a screenshot forbids invented milliseconds, not a visible "
            "normal/prolonged category. "
            f"{EKG_LVH_BALANCE_GUIDANCE} "
            f"{EKG_PRECORDIAL_REVIEW_GUIDANCE} "
            "Clearly tall or broad T waves that persist across contiguous leads can "
            "be abnormal without ST elevation; compare hyperkalemia, hyperacute "
            "ischemia, and benign variants instead of downgrading them solely for "
            "lack of reciprocal change. "
            "For the compact 12-row layout, findings must name actual lead_* "
            "regions, never rhythm_strip. "
            "Normal/WNL is valid when no visible abnormality or unresolved candidate "
            "is present.\n"
        )
    return (
        "Bounded multi-pass TRIAGE turn for the attached medical image. Return a "
        "compact preliminary JSON promptly; separate crop/refine and final-report "
        "turns will perform the detailed read. Do not write the full modality "
        "checklist now. Inspect the whole image. For EKG, preserve a compact "
        "mechanism inventory of at most six distinct visible abnormalities or "
        "unresolved candidates across rhythm/pacing, conduction, voltage/chamber, "
        "axis, ST elevation, and ST-depression/T-wave families; the later crop "
        "budget does not delete a distinct candidate. For other modalities, "
        "localize at most three highest-value candidates. Use findings=[] with "
        "severity=normal for a supported normal/WNL image. Never invent a finding.\n"
        f"{PROFESSIONAL_CO_READER_GUIDANCE}\n"
        f"modality must be '{modality.value}'. Allowed regions: {allowed_regions}.\n"
        f"{partial_input_guidance}"
        f"{ekg_contract}"
        f"{waveform_protocol}"
        "For every preliminary finding include id, label, one-sentence detail, "
        "severity, confidence, question, regions, and tight full-image normalized "
        "bboxes. Every EKG bbox must satisfy w<=0.35, h<=0.30, and w*h<=0.08. "
        "For a synchronized EKG event, use one to three small representative "
        "lead/beat boxes at the same timestamp; never use a full-height time band "
        "or a full-width lead row as a diagnostic bbox. Non-urgent uncertainty is "
        "info/low confidence with a concrete "
        "review question. Every boxed info finding must declare confidence; low "
        "confidence requires that concrete question. Time-critical uncertainty "
        "keeps critical triage wording. "
        "Normal observations have no boxes.\n"
        "If any boxes are retained, call dicom_bbox_validate exactly once with "
        f"modality={modality.value}, source_image_sha256="
        f"'{bbox_source_image_sha256}', evidence_nonce='{bbox_evidence_nonce}', "
        "and the complete intended bbox multiset. Copy only accepted coordinates; "
        "never use crop-local coordinates. If accepted=[] then every finding "
        "must have bboxes=[]; never return a rejected coordinate.\n"
        "Return one JSON object only with keys modality, summary, severity, findings, "
        "checklist, layout, next_steps, image_quality, model_used, incomplete, and "
        "incomplete_reasons. Set checklist={} in this triage turn. severity must be "
        "exactly normal, info, warning, or critical; never emit urgent/emergent as "
        "a severity value. Keep the entire "
        "JSON under 2200 characters: summary <=25 words, each detail <=18 words, "
        "at most two next_steps, and image_quality <=8 words. Do not output markdown "
        "or hidden reasoning. Verify all delimiters before sending."
    )


def build_minimal_control_prompt(
    *,
    modality: Modality,
    valid_regions: list[str],
) -> str:
    """Build the single-look control prompt with only a parseable JSON envelope."""

    allowed_regions = ", ".join(valid_regions) if valid_regions else "(none provided)"
    return (
        "Experimental minimal-control read. Inspect the attached medical image "
        "once and do not call tools or use external files. Return one JSON object "
        "only, without markdown. Do not invent an abnormality when the image is "
        "within normal limits. Use concise clinical English for every JSON "
        "string value.\n"
        f"{PROFESSIONAL_CO_READER_GUIDANCE}\n"
        f"modality must be '{modality.value}'.\n"
        f"Allowed region names: {allowed_regions}.\n"
        "Required top-level keys: modality, summary, severity, findings, "
        "checklist, layout, next_steps, image_quality, model_used, incomplete, "
        "incomplete_reasons. Each finding should include id, label, detail, "
        "severity, regions, and normalized 0-1 bboxes when localization is "
        "available."
    )


def build_followup_prompt(
    *,
    user_question: str,
    context: InterpretationContext,
) -> str:
    """Build a multi-turn prompt for questions about the same attached image."""
    finding_lines = "\n".join(context.finding_summaries) or "(no findings recorded)"
    return (
        "Answer the user's follow-up question about the same attached medical image.\n"
        "Use the prior structured interpretation as context, but re-check the image "
        "before answering. Do not invent findings that are not visible.\n\n"
        f"{PROFESSIONAL_CO_READER_GUIDANCE}\n\n"
        f"Prior modality: {context.modality.value}\n"
        f"Prior severity: {context.severity.value}\n"
        f"Prior summary: {context.summary}\n"
        f"Prior findings:\n{finding_lines}\n\n"
        f"User question: {user_question}\n\n"
        "Reply with concise clinical guidance, mention the relevant labels/regions, "
        "and say when the image is insufficient for the requested conclusion."
    )


def summarize_result_for_followup(result: AnalysisResult) -> str:
    """Create compact text context for log output and follow-up chat prompts."""
    context = InterpretationContext.from_result(result)
    findings = "; ".join(context.finding_summaries) or "no findings"
    return (
        f"{context.modality.value} {context.severity.value}: "
        f"{context.summary}. Findings: {findings}"
    )
