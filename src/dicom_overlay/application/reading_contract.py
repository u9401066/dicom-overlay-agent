"""Pure prompt projection of the audited, generated YAML reading contract."""

from __future__ import annotations

import json
from typing import Any, cast

from dicom_overlay.domain.generated_clinical_rules import (
    READING_CONTRACT,
    REGISTRY_DIGEST_SCOPE,
    REGISTRY_SHA256,
)


def contract_identity(stage: str) -> dict[str, str]:
    if stage not in cast("dict[str, Any]", READING_CONTRACT["stages"]):
        raise ValueError("unknown_reading_contract_stage")
    return {
        "stage": stage,
        "version": str(READING_CONTRACT["version"]),
        "registry_sha256": REGISTRY_SHA256,
        "digest_scope": REGISTRY_DIGEST_SCOPE,
    }


def stage_instructions(stage: str, modality: str) -> str:
    identity = contract_identity(stage)
    focus = cast("dict[str, str]", READING_CONTRACT["quality_focus"])
    if modality not in focus:
        raise ValueError("unknown_reading_contract_modality")
    stages = cast("dict[str, list[dict[str, str]]]", READING_CONTRACT["stages"])
    result = (
        f"SCIENTIFIC STAGE: {stage}.\nREADING CONTRACT: "
        + json.dumps(identity, sort_keys=True)
        + "\n"
        + "\n".join(f"[{step['id']}] {step['instruction']}" for step in stages[stage])
    )
    if stage == "quality_gate":
        result += "\n" + focus[modality]
    if stage in cast("list[str]", READING_CONTRACT["rule_guidance_stages"]):
        rules = [
            rule
            for rule in cast("list[dict[str, Any]]", READING_CONTRACT["rules"])
            if rule["modality"] == modality
        ]
        if rules:
            result += (
                "\nCONDITIONAL CLINICAL GUIDANCE: Apply only when its preconditions "
                "and visible evidence hold; respect exclusions. These rules are not "
                "observations or proof of a diagnosis. Keep this stage's no-tool and "
                "validated-evidence restrictions; do not create or move boxes.\n"
                + json.dumps(rules, ensure_ascii=False, separators=(",", ":"))
            )
    return result + "\n"
