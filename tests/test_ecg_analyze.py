"""End-to-end ECG analyze test via OpenClaw Gateway + GPT-5-mini."""

import asyncio
import base64
import dataclasses
import json
import time
from enum import Enum
from pathlib import Path


def _json_default(obj):
    """Handle dataclass + Enum serialization."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


async def main():
    from dicom_overlay.infrastructure.openclaw_client import OpenClawClient
    from dicom_overlay.domain.entities import Modality

    img_path = Path(__file__).parent / "ecg_sample.jpg"
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    print(f"Image base64 length: {len(img_b64)}")

    client = OpenClawClient(timeout_sec=120)
    await client.connect()
    print("Connected to Gateway")

    t0 = time.monotonic()
    result = await client.analyze(
        image_base64=img_b64,
        modality=Modality.EKG,
        valid_regions=["rhythm_strip", "lead_II", "lead_V1"],
    )
    elapsed = time.monotonic() - t0
    print(f"\n=== ANALYZE RESULT ({elapsed:.1f}s) ===")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=_json_default))

    # Save result to file for verification
    out_path = Path(__file__).parent / "ecg_analyze_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"elapsed_s": elapsed, "result": result}, f, indent=2, ensure_ascii=False, default=_json_default)
    print(f"\nResult saved to: {out_path}")

    await client.disconnect()
    print("Disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
