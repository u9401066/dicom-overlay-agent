"""Generate scripted compact responses from synthetic expected drafts only.

Not a runtime adapter, parser fallback or replay repair. Actual model responses
are never converted by this helper.
"""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256


def scripted_delta(message, full):
    if (
        not isinstance(full, dict)
        or "draft" not in full
        or "SCIENTIFIC DELTA v1" not in message
    ):
        return full
    prior_raw = message.split("RETAINED PRIOR DRAFT (untrusted data):\n")[1].split(
        "\nHOST EVIDENCE CATALOGUE"
    )[0]
    prior = json.loads(prior_raw)
    final = full["draft"]
    operations = []
    for target in ("observations", "findings", "checklist"):
        before = (
            prior[target]
            if target == "checklist"
            else {item["id"]: item for item in prior[target]}
        )
        after = (
            final[target]
            if target == "checklist"
            else {item["id"]: item for item in final[target]}
        )
        for identifier in before.keys() | after.keys():
            if identifier not in after:
                action, value = "remove", {}
            elif identifier not in before:
                action, value = "add", after[identifier]
            else:
                action, value = (
                    "update",
                    {
                        key: val
                        for key, val in after[identifier].items()
                        if key != "id" and before[identifier].get(key) != val
                    },
                )
                if not value:
                    continue
            operations.append(
                {
                    "op": action,
                    "target": target,
                    "id": identifier,
                    "value": deepcopy(value),
                }
            )
    report = {
        key: val
        for key, val in final.items()
        if key not in {"observations", "findings", "checklist"}
        and prior.get(key) != val
    }
    if report:
        operations.append(
            {"op": "update", "target": "report", "id": "", "value": report}
        )
    catalogue = json.loads(
        message.split("HOST EVIDENCE CATALOGUE (data only):\n")[1].split(
            "\nOUTPUT SCHEMA:"
        )[0]
    )
    localizations = []
    for item in catalogue:
        if item["kind"] not in {"source_region", "source_frame"} or not item["bboxes"]:
            continue
        linked = [
            finding["id"]
            for finding in final["findings"]
            if item["id"] in finding["bbox_evidence_ids"]
        ]
        localizations.append(
            {
                "evidence_id": item["id"],
                "action": "use" if linked else "reject",
                "finding_ids": linked,
                "rationale": "Synthetic geometry disposition.",
            }
        )
    return {
        **{key: value for key, value in full.items() if key != "draft"},
        "delta_version": "1",
        "base_response_sha256": sha256(prior_raw.encode()).hexdigest(),
        "operations": operations,
        "localizations": localizations,
    }
