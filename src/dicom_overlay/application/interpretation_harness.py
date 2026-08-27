"""Prompt and context harness for medical image interpretation sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dicom_overlay.domain.entities import AnalysisResult, Modality, Severity


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
        "Run this systematic image interpretation protocol:\n"
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
            'do not output '
            "per-lead bboxes. Local pixel "
            "evidence will derive row geometry. For any other EKG layout, include "
            "only visibly labeled leads with normalized [x,y,w,h] bboxes. Check "
            "rhythm/ectopy, conduction, high versus low voltage, Q/QS or R-wave "
            "progression, and ST-T morphology without favoring one category. "
            "Treat minor concave/nonspecific ST-T variation as WNL unless a "
            "pathologic pattern persists across contiguous leads. Before choosing "
            "the top three, test contiguous territories for acute ST elevation, "
            "reciprocal depression, and hyperacute morphology. If a time-critical "
            "pattern remains visually plausible, reserve a finding slot and label "
            "it 'Possible acute ST-elevation ischemic pattern (STEMI cannot be "
            "excluded)' with critical triage severity and low confidence. "
            "Irregular R-R timing or poorly seen P waves alone cannot diagnose AF. "
            "At any abrupt abnormal interval, explicitly test whether at least "
            "three consecutive broad QRS complexes recur at the same horizontal "
            "positions across multiple leads. If so, evaluate NSVT/VT versus "
            "artifact or conduction before attributing secondary ST-T distortion "
            "to ischemia; a plausible ventricular run remains a critical, cautious "
            "differential for crop review. "
            "Do not call sinus from regular timing alone: require repeatable P "
            "waves before QRS complexes with a stable P-QRS relationship in at "
            "least one clear lead. If neither sinus nor AF/flutter has positive "
            "visible morphology, preserve other/indeterminate rather than forcing "
            "either diagnosis. "
            "Before proposing LVH, verify appropriate labeled leads and visible "
            "calibration, and compare V1-V6 R/S progression; high voltage alone "
            "must not become an LVH finding or displace poor R progression. "
            "For the compact 12-row layout, findings must name actual lead_* "
            "regions, never rhythm_strip. "
            "Normal/WNL is valid when no visible abnormality or unresolved candidate "
            "is present.\n"
        )
    return (
        "Bounded multi-pass TRIAGE turn for the attached medical image. Return a "
        "compact preliminary JSON promptly; separate crop/refine and final-report "
        "turns will perform the detailed read. Do not write the full modality "
        "checklist now. Inspect the whole image, localize at most three highest-value "
        "visible abnormalities or unresolved candidates, and use findings=[] with "
        "severity=normal for a supported normal/WNL image. Never invent a finding.\n"
        f"modality must be '{modality.value}'. Allowed regions: {allowed_regions}.\n"
        f"{ekg_contract}"
        f"{waveform_protocol}"
        "For every preliminary finding include id, label, one-sentence detail, "
        "severity, confidence, question, regions, and tight full-image normalized "
        "bboxes. Non-urgent uncertainty is info/low confidence with a concrete "
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
