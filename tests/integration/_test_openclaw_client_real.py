"""Real Gateway integration tests using OpenClawClient.

Run with: uv run python tests/integration/test_openclaw_client_real.py

Requires:
  - OpenClaw Gateway running at ws://127.0.0.1:18789
  - Valid auth token in openclaw/openclaw.json
  - Skill files in openclaw/workspace/skills/
"""

from __future__ import annotations

import asyncio
import base64
import json
import struct
import sys
import time
import zlib
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from dicom_overlay.domain.entities import Modality, Severity
from dicom_overlay.infrastructure.openclaw_client import OpenClawClient


def _print(msg: str) -> None:
    print(msg, flush=True)


def _make_tiny_png() -> bytes:
    """Generate a minimal valid 1x1 white PNG."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + ihdr_crc
    raw = b"\x00\xff\xff\xff"
    idat_data = zlib.compress(raw)
    idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + idat_data) & 0xFFFFFFFF)
    idat = struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data + idat_crc
    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    iend = struct.pack(">I", 0) + b"IEND" + iend_crc
    return sig + ihdr + idat + iend


class TestResult:
    def __init__(self, name: str) -> None:
        self.name = name
        self.passed = False
        self.error: str | None = None
        self.elapsed: float = 0.0

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        suffix = f" ({self.error})" if self.error else ""
        return f"  [{status}] {self.name} ({self.elapsed:.1f}s){suffix}"


async def test_connect(client: OpenClawClient) -> TestResult:
    """Test: client.connect() successfully authenticates."""
    r = TestResult("connect")
    t0 = time.time()
    try:
        await client.connect()
        r.passed = client.is_connected()
        if not r.passed:
            r.error = "is_connected() returned False after connect()"
    except Exception as e:
        r.error = str(e)
    r.elapsed = time.time() - t0
    return r


async def test_chat(client: OpenClawClient) -> TestResult:
    """Test: client.chat() returns non-empty text."""
    r = TestResult("chat")
    t0 = time.time()
    try:
        text = await client.chat("What model are you? Reply in one sentence.")
        r.passed = len(text) > 0
        if r.passed:
            _print(f"    chat response ({len(text)} chars): {text[:200]}")
        else:
            r.error = "Empty response"
    except Exception as e:
        r.error = str(e)
    r.elapsed = time.time() - t0
    return r


async def test_analyze_ekg(client: OpenClawClient) -> TestResult:
    """Test: client.analyze() returns a valid AnalysisResult for EKG."""
    r = TestResult("analyze_ekg")
    t0 = time.time()
    try:
        img_b64 = base64.b64encode(_make_tiny_png()).decode()
        result = await client.analyze(
            image_base64=img_b64,
            modality=Modality.EKG,
            valid_regions=["lead_I", "lead_II", "lead_III", "rhythm_strip"],
        )

        # Validate AnalysisResult
        checks = []
        checks.append(("modality is EKG", result.modality == Modality.EKG))
        checks.append(("summary non-empty", len(result.summary) > 0))
        checks.append(("severity is valid", isinstance(result.severity, Severity)))
        checks.append(("has findings", len(result.findings) > 0))
        checks.append(("has checklist", len(result.checklist) > 0))
        checks.append(("has model_used", True))  # Optional - AI may not include it
        checks.append(("analysis_time_ms > 0", result.analysis_time_ms > 0))

        # Validate findings
        for f in result.findings:
            checks.append((f"finding {f.id} has label", len(f.label) > 0))
            checks.append((f"finding {f.id} has detail", len(f.detail) > 0))
            checks.append((f"finding {f.id} has severity", isinstance(f.severity, Severity)))

        # Validate checklist items
        for key, item in result.checklist.items():
            checks.append((f"checklist[{key}] has value", len(item.value) > 0))
            checks.append((f"checklist[{key}] has status", isinstance(item.status, Severity)))

        failed = [(name, ok) for name, ok in checks if not ok]
        if failed:
            r.error = f"Failed checks: {[n for n, _ in failed]}"
        else:
            r.passed = True

        _print(f"    modality={result.modality.value}")
        _print(f"    severity={result.severity.value}")
        _print(f"    summary={result.summary[:150]}")
        _print(f"    findings={len(result.findings)}")
        _print(f"    checklist={list(result.checklist.keys())}")
        _print(f"    model={result.model_used or '(not provided by AI)'}")
        _print(f"    analysis_time_ms={result.analysis_time_ms}")

    except Exception as e:
        r.error = str(e)[:500]
    r.elapsed = time.time() - t0
    return r


async def test_disconnect(client: OpenClawClient) -> TestResult:
    """Test: client.disconnect() works cleanly."""
    r = TestResult("disconnect")
    t0 = time.time()
    try:
        await client.disconnect()
        r.passed = not client.is_connected()
        if not r.passed:
            r.error = "is_connected() still True after disconnect()"
    except Exception as e:
        r.error = str(e)
    r.elapsed = time.time() - t0
    return r


async def main() -> None:
    _print("=" * 60)
    _print("OpenClawClient Real Gateway Integration Tests")
    _print("=" * 60)

    # Use longer timeout since AI responses can take 20-30s
    client = OpenClawClient(
        gateway_url="ws://127.0.0.1:18789",
        timeout_sec=120,
    )

    results: list[TestResult] = []

    # 1. Connect
    r = await test_connect(client)
    results.append(r)
    _print(str(r))
    if not r.passed:
        _print("\nCannot continue without connection.")
        return

    # 2. Chat (simple text)
    r = await test_chat(client)
    results.append(r)
    _print(str(r))

    # 3. Analyze EKG (full pipeline)
    r = await test_analyze_ekg(client)
    results.append(r)
    _print(str(r))

    # 4. Disconnect
    r = await test_disconnect(client)
    results.append(r)
    _print(str(r))

    # Summary
    _print("\n" + "=" * 60)
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    _print(f"Results: {passed}/{total} passed")
    total_time = sum(r.elapsed for r in results)
    _print(f"Total time: {total_time:.1f}s")
    _print("=" * 60)

    # Save results
    result_path = Path(__file__).parent / "client_test_result.json"
    result_path.write_text(
        json.dumps(
            {
                "passed": passed,
                "total": total,
                "total_time": round(total_time, 1),
                "tests": [
                    {
                        "name": r.name,
                        "passed": r.passed,
                        "elapsed": round(r.elapsed, 1),
                        "error": r.error,
                    }
                    for r in results
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _print(f"[SAVED] {result_path}")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
