"""Run the recognition evaluation harness and write a scorecard.

Usage::

    # Pipeline verification (no token needed) -- proves how results are scored:
    uv run python scripts/run-eval.py --mock

    # Real accuracy benchmark (start the OpenClaw Gateway first, see RUNBOOK):
    set ANTHROPIC_API_KEY=...    # in your shell, NOT in code
    uv run python scripts/run-eval.py --gateway ws://127.0.0.1:18789

The two modes share identical scoring (``eval_harness.run_evaluation``); only the
source of the structured result differs. Artifacts land in
``data/eval/<timestamp>/`` (scorecard.json + per-image raw results).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import websockets

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dicom_overlay.domain.entities import Modality, Severity  # noqa: E402
from dicom_overlay.infrastructure.eval_harness import (  # noqa: E402
    EvalCase,
    EvalReport,
    run_evaluation,
)
from dicom_overlay.infrastructure.openclaw_client import OpenClawClient  # noqa: E402
from dicom_overlay.infrastructure.screen_monitor import ImageProcessor  # noqa: E402

_DATASET_DIR = _REPO_ROOT / "data" / "eval-datasets"
# Match the production default (entities.OpenClawConfig.max_image_edge_px).
_MAX_IMAGE_EDGE_PX = 1568
_EKG_CHECKLIST_KEYS = [
    "heart_rate", "rhythm", "regularity", "axis", "p_wave", "pr_interval",
    "qrs_duration", "qrs_morphology", "st_segment", "t_wave", "qtc_interval",
    "chamber_enlargement", "conduction", "av_block", "stemi_pattern", "ischemia",
]


def _load_cases(manifest_path: Path) -> list[EvalCase]:
    spec = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases: list[EvalCase] = []
    for entry in spec["cases"]:
        cases.append(
            EvalCase(
                image_path=manifest_path.parent / entry["image"],
                modality=Modality(entry["modality"]),
                expected_severity=Severity(entry["expected_severity"]),
                expected_keywords=tuple(entry.get("keywords", [])),
                label=entry.get("label", ""),
            )
        )
    return cases


# ----------------------------------------------------------------------------
# Mock gateway -- emits a schema-valid payload derived from the case ground
# truth. Verifies the scoring pipeline end-to-end without a token.
# ----------------------------------------------------------------------------

def _mock_payload_for(case: EvalCase) -> dict[str, Any]:
    keywords = list(case.expected_keywords)
    detail = ", ".join(keywords) if keywords else "no acute finding"
    findings = []
    if case.expected_severity in (Severity.WARNING, Severity.CRITICAL):
        findings.append({
            "id": "f1",
            "label": keywords[0] if keywords else "finding",
            "detail": detail,
            "severity": case.expected_severity.value,
            "regions": [],
            "bboxes": [{"x": 0.55, "y": 0.6, "w": 0.2, "h": 0.15}],
        })
    checklist: dict[str, Any] = {}
    if case.modality is Modality.EKG:
        for key in _EKG_CHECKLIST_KEYS:
            checklist[key] = {"value": "normal", "status": "normal"}
        if case.expected_severity is Severity.CRITICAL:
            checklist["st_segment"] = {"value": "ST elevation", "status": "critical"}
            checklist["stemi_pattern"] = {"value": "STEMI", "status": "critical"}
    summary = (
        f"{case.modality.value}: {detail}"
        if findings
        else f"{case.modality.value}: clear, no acute abnormality"
    )
    return {
        "modality": case.modality.value,
        "summary": summary,
        "severity": case.expected_severity.value,
        "model_used": "mock-eval-gateway",
        "findings": findings,
        "checklist": checklist,
    }


class _MockGateway:
    """In-process gateway answering connect + chat.send with queued payloads."""

    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self._payloads = payloads
        self._index = 0
        self._server: Any = None
        self.url = ""

    async def __aenter__(self) -> _MockGateway:
        # Match the client's raised frame limit so multi-MB real image
        # payloads are accepted instead of closing the socket (code 1009).
        self._server = await websockets.serve(
            self._handler, "127.0.0.1", 0, max_size=16 * 1024 * 1024
        )
        port = self._server.sockets[0].getsockname()[1]
        self.url = f"ws://127.0.0.1:{port}"
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handler(self, ws: Any) -> None:
        connect_raw = await ws.recv()
        connect = json.loads(connect_raw)
        await ws.send(json.dumps({
            "type": "res", "id": connect["id"], "ok": True,
            "payload": {"status": "connected"},
        }))
        while True:
            try:
                chat_raw = await ws.recv()
            except websockets.ConnectionClosed:
                return
            chat = json.loads(chat_raw)
            run_id = str(uuid4())
            await ws.send(json.dumps({
                "type": "res", "id": chat["id"], "ok": True,
                "payload": {"status": "accepted", "runId": run_id},
            }))
            payload = self._payloads[min(self._index, len(self._payloads) - 1)]
            self._index += 1
            await ws.send(json.dumps({
                "type": "event",
                "payload": {
                    "runId": run_id,
                    "state": "final",
                    "message": {
                        "content": [{"type": "text", "text": json.dumps(payload)}]
                    },
                },
            }))


async def _run(cases: list[EvalCase], gateway_url: str, mode: str,
               output_dir: Path) -> EvalReport:
    processor = ImageProcessor()

    async def analyze_with_client(client: OpenClawClient) -> EvalReport:
        if not client.is_connected():
            await client.connect()

        async def analyze(case: EvalCase) -> Any:
            image_bytes = case.image_path.read_bytes()
            # Mirror the production pipeline (overlay_agent): downscale to the
            # configured max edge BEFORE encoding so the eval measures what the
            # app actually sends, and avoids huge multi-MB payloads.
            image_bytes = processor.downscale_to_max_edge(image_bytes, _MAX_IMAGE_EDGE_PX)
            b64 = processor.to_base64(image_bytes)
            return await client.analyze(b64, case.modality, list(case.valid_regions))

        return await run_evaluation(
            cases, analyze, output_dir=output_dir, gateway_mode=mode
        )

    if mode == "mock":
        payloads = [_mock_payload_for(c) for c in cases]
        async with _MockGateway(payloads) as gw:
            client = OpenClawClient(gateway_url=gw.url)
            try:
                return await analyze_with_client(client)
            finally:
                await client.disconnect()

    client = OpenClawClient(gateway_url=gateway_url)
    try:
        return await analyze_with_client(client)
    finally:
        await client.disconnect()


def _print_summary(report: EvalReport, output_dir: Path) -> None:
    print("\n" + "=" * 60)
    print(f"  RECOGNITION SCORECARD  (mode={report.gateway_mode})")
    print("=" * 60)
    print(f"  cases scored ........ {report.scored}/{report.total} "
          f"(errors={report.error_count})")
    print(f"  severity accuracy ... {report.severity_accuracy:.0%} (exact)")
    print(f"  abnormal accuracy ... {report.severity_abnormal_accuracy:.0%} "
          f"(normal vs abnormal)")
    print(f"  keyword recall ...... {report.mean_keyword_recall:.0%} (mean)")
    print(f"  schema pass rate .... {report.schema_pass_rate:.0%}")
    print(f"  bbox in-bounds ...... {report.bbox_in_bounds_rate:.0%}")
    print(f"  mean latency ........ {report.mean_latency_ms:.0f} ms")
    print("-" * 60)
    for case in report.cases:
        flag = "OK " if case.severity_match else "MISS"
        if case.error:
            flag = "ERR"
        print(f"  [{flag}] {case.case_label:<24} "
              f"exp={case.expected_severity:<8} got={case.actual_severity:<8} "
              f"recall={case.keyword_recall:.0%}")
    print("=" * 60)
    print(f"  artifacts: {output_dir}")
    if report.gateway_mode == "mock":
        print("  NOTE: mock mode verifies the SCORING PIPELINE only, not model "
              "accuracy.\n        Provide a token + real gateway for a real "
              "benchmark.")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run recognition evaluation")
    parser.add_argument("--manifest", type=Path,
                        default=_DATASET_DIR / "manifest.json")
    parser.add_argument("--gateway", default="ws://127.0.0.1:18789",
                        help="Real OpenClaw Gateway URL")
    parser.add_argument("--mock", action="store_true",
                        help="Use in-process mock gateway (no token needed)")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}\n"
              f"Run: uv run python scripts/fetch-eval-datasets.py", file=sys.stderr)
        return 2

    cases = _load_cases(args.manifest)
    if not cases:
        print("No cases in manifest.", file=sys.stderr)
        return 2

    mode = "mock" if args.mock else "real"
    if mode == "real":
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY")
                       or os.environ.get("OPENAI_API_KEY"))
        if not has_key:
            print("WARNING: no ANTHROPIC_API_KEY/OPENAI_API_KEY in environment. "
                  "Real gateway will likely fail; use --mock for a pipeline "
                  "check.", file=sys.stderr)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_dir = args.output or (_REPO_ROOT / "data" / "eval" / f"{mode}-{stamp}")
    output_dir.mkdir(parents=True, exist_ok=True)

    start = time.monotonic()
    try:
        report = asyncio.run(_run(cases, args.gateway, mode, output_dir))
    except (ConnectionError, OSError) as exc:
        print(f"\nERROR: could not reach gateway at {args.gateway}: {exc}\n"
              f"Start the gateway (see REAL_TEST_RUNBOOK.md) or run with --mock.",
              file=sys.stderr)
        return 1
    elapsed = time.monotonic() - start
    _print_summary(report, output_dir)
    print(f"  total run time: {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
