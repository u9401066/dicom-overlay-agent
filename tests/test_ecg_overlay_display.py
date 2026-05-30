"""Test: ECG analyze → verify overlay display formatting.

Sends ECG image to GPT-5-mini, then simulates SummaryPanel rendering
to verify checklist/findings display correctly.
"""

import asyncio
import base64
import time
from pathlib import Path


async def main():
    from dicom_overlay.domain.entities import Modality
    from dicom_overlay.infrastructure.openclaw_client import OpenClawClient
    from dicom_overlay.presentation.overlay_window import (
        _humanize_checklist_key,
        _humanize_checklist_value,
    )

    img_path = Path(__file__).parent / "ecg_sample.jpg"
    with img_path.open("rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    print(f"Image base64 length: {len(img_b64)}")

    client = OpenClawClient(timeout_sec=120)
    await client.connect()
    print("Connected to Gateway")

    t0 = time.monotonic()
    result = await client.analyze(
        image_base64=img_b64,
        modality=Modality.EKG,
        valid_regions=[
            "rhythm_strip", "lead_I", "lead_II", "lead_III",
            "lead_aVR", "lead_aVL", "lead_aVF",
            "lead_V1", "lead_V2", "lead_V3", "lead_V4", "lead_V5", "lead_V6",
        ],
    )
    elapsed = time.monotonic() - t0
    print(f"\n=== ANALYZE RESULT ({elapsed:.1f}s) ===")

    # --- Simulate SummaryPanel display ---
    print(f"\n{'='*50}")
    modality_icons = {"EKG": "🫀", "CXR": "🫁", "CT_BRAIN": "🧠"}
    icon = modality_icons.get(result.modality.value, "📊")
    print(f"  {icon} {result.modality.value} Analysis")
    print(f"  {'─'*40}")

    print("\n  📋 Checklist:")
    for key, item in result.checklist.items():
        status_icons = {"normal": "✅", "warning": "⚠️", "critical": "🔴", "info": "🔵"}
        sicon = status_icons.get(item.status.value, "🔵")
        dkey = _humanize_checklist_key(key)
        dval = _humanize_checklist_value(item.value)
        print(f"    {sicon} {dkey}: {dval}")

    print(f"\n  🔎 Findings ({len(result.findings)}):")
    for f in result.findings:
        print(f"    [{f.severity.value.upper()}] {f.label or '(no label)'}")
        if f.detail:
            print(f"         {f.detail}")
        if f.regions:
            print(f"         regions: {', '.join(f.regions)}")

    sev_icon = {"critical": "🔴", "warning": "⚠️", "normal": "🟢"}.get(
        result.severity.value, "🔵"
    )
    print(f"\n  {sev_icon} {result.summary}")
    print(f"{'='*50}")

    await client.disconnect()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
