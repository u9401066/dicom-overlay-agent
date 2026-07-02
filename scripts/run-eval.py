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
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog
import websockets

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from dicom_overlay.application.multi_pass import (  # noqa: E402
    MultiPassAnalyzer,
    MultiPassInterpreter,
)
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
_DEFAULT_TIMEOUT_SEC = 90
_EKG_VALID_REGIONS = (
    "lead_I", "lead_II", "lead_III",
    "lead_aVR", "lead_aVL", "lead_aVF",
    "lead_V1", "lead_V2", "lead_V3", "lead_V4", "lead_V5", "lead_V6",
    "rhythm_strip",
)
_CXR_VALID_REGIONS = (
    "trachea", "right_upper_lung", "right_middle_lung", "right_lower_lung",
    "left_upper_lung", "left_middle_lung", "left_lower_lung",
    "right_cp_angle", "left_cp_angle", "cardiac_silhouette", "mediastinum",
    "diaphragm",
)
_CT_BRAIN_VALID_REGIONS = (
    "right_frontal", "left_frontal", "right_temporal", "left_temporal",
    "right_basal_ganglia", "left_basal_ganglia", "ventricles", "midline",
    "posterior_fossa",
)
_DEFAULT_VALID_REGIONS = {
    Modality.EKG: _EKG_VALID_REGIONS,
    Modality.CXR: _CXR_VALID_REGIONS,
    Modality.CT_BRAIN: _CT_BRAIN_VALID_REGIONS,
}
_EKG_CHECKLIST_KEYS = [
    "heart_rate", "rhythm", "regularity", "axis", "p_wave", "pr_interval",
    "qrs_duration", "qrs_morphology", "st_segment", "t_wave", "qtc_interval",
    "chamber_enlargement", "conduction", "av_block", "stemi_pattern", "ischemia",
]
_CXR_CHECKLIST_KEYS = [
    "airway", "lungs", "pleura", "cardiac_silhouette", "mediastinum",
    "hila", "diaphragm", "bones", "soft_tissue", "lines_tubes",
]


def _valid_regions_for(entry: dict[str, Any], modality: Modality) -> tuple[str, ...]:
    explicit = entry.get("valid_regions")
    if explicit:
        return tuple(str(item) for item in explicit)
    return tuple(_DEFAULT_VALID_REGIONS.get(modality, ()))


def _load_cases(manifest_path: Path) -> list[EvalCase]:
    spec = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases: list[EvalCase] = []
    for entry in spec["cases"]:
        modality = Modality(entry["modality"])
        cases.append(
            EvalCase(
                image_path=manifest_path.parent / entry["image"],
                modality=modality,
                expected_severity=Severity(entry["expected_severity"]),
                expected_keywords=tuple(entry.get("keywords", [])),
                expected_negatives=tuple(entry.get("negatives", [])),
                target_axes=tuple(entry.get("target_axes", [])),
                cant_miss=tuple(entry.get("cant_miss", [])),
                label=entry.get("label", ""),
                valid_regions=_valid_regions_for(entry, modality),
            )
        )
    return cases


# ----------------------------------------------------------------------------
# Mock gateway -- emits a schema-valid payload derived from the case ground
# truth. Verifies the scoring pipeline end-to-end without a token.
# ----------------------------------------------------------------------------

def _mock_payload_for(case: EvalCase) -> dict[str, Any]:
    keywords = list(case.expected_keywords)
    # Fold the can't-miss labels into the synthesized read so the mock pipeline
    # self-test passes its own hard gate (mock mode proves the SCORING path,
    # not model skill -- a mock that drops the can't-miss would be a false fail).
    detail_parts = keywords + list(case.cant_miss) + list(case.expected_negatives)
    detail = ", ".join(detail_parts) if detail_parts else "no acute finding"
    findings = []
    if case.expected_severity in (Severity.WARNING, Severity.CRITICAL):
        findings.append({
            "id": "f1",
            "label": detail_parts[0] if detail_parts else "finding",
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
    elif case.modality is Modality.CXR:
        for key in _CXR_CHECKLIST_KEYS:
            checklist[key] = {"value": "normal", "status": "normal"}
        if case.expected_severity in (Severity.WARNING, Severity.CRITICAL):
            checklist["lungs"] = {"value": "consolidation", "status": "warning"}
    summary = f"{case.modality.value}: {detail}"
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


class _CountingAnalyzer:
    """Counts analyze calls while delegating to the real OpenClaw client."""

    def __init__(self, inner: OpenClawClient) -> None:
        self._inner = inner
        self.analyze_calls = 0

    async def analyze(
        self,
        image_base64: str,
        modality: Modality,
        valid_regions: list[str],
    ) -> Any:
        self.analyze_calls += 1
        return await self._inner.analyze(image_base64, modality, valid_regions)

    async def chat(self, message: str) -> str:
        return await self._inner.chat(message)

    async def connect(self) -> None:
        await self._inner.connect()

    async def disconnect(self) -> None:
        await self._inner.disconnect()

    def is_connected(self) -> bool:
        return self._inner.is_connected()


async def _run(cases: list[EvalCase], gateway_url: str, mode: str,
               output_dir: Path, timeout_sec: int, *, multi_pass: bool,
               multi_pass_max_targets: int) -> EvalReport:
    processor = ImageProcessor()

    async def analyze_with_client(client: OpenClawClient) -> EvalReport:
        analyzer: Any = client
        counter: _CountingAnalyzer | None = None
        crop_calls = 0
        trace_path = output_dir / "multipass-trace.jsonl"
        local_quality_by_case: dict[str, dict[str, object]] = {}
        local_signal_by_case: dict[str, dict[str, object]] = {}

        if multi_pass:
            counter = _CountingAnalyzer(client)

            def cropper(image_base64: str, region: Any) -> str:
                nonlocal crop_calls
                crop_calls += 1
                return processor.crop_region_base64(image_base64, region)

            interpreter = MultiPassInterpreter(
                analyzer=counter,
                cropper=cropper,
                max_zoom_targets=multi_pass_max_targets,
            )
            analyzer = MultiPassAnalyzer(inner=counter, interpreter=interpreter)

        if not analyzer.is_connected():
            await analyzer.connect()

        async def analyze(case: EvalCase) -> Any:
            nonlocal crop_calls
            case_key = case.label or case.image_path.stem
            image_bytes = case.image_path.read_bytes()
            # Mirror the production pipeline (overlay_agent): downscale to the
            # configured max edge BEFORE encoding so the eval measures what the
            # app actually sends, and avoids huge multi-MB payloads.
            image_bytes = processor.downscale_to_max_edge(image_bytes, _MAX_IMAGE_EDGE_PX)
            local_quality_by_case[case_key] = processor.image_quality_profile(image_bytes)
            local_signal_by_case[case_key] = processor.local_signal_candidates(
                image_bytes
            )
            source_size_px = processor.image_size(image_bytes)
            b64 = processor.to_base64(image_bytes)
            before_calls = counter.analyze_calls if counter else 0
            before_crops = crop_calls
            try:
                analyze_with_source_size = getattr(
                    analyzer, "analyze_with_source_size", None
                )
                if callable(analyze_with_source_size):
                    result = await analyze_with_source_size(
                        b64,
                        case.modality,
                        list(case.valid_regions),
                        source_size_px=source_size_px,
                    )
                else:
                    result = await analyzer.analyze(
                        b64, case.modality, list(case.valid_regions)
                    )
            finally:
                if multi_pass and counter:
                    calls = counter.analyze_calls - before_calls
                    crops = crop_calls - before_crops
                    trace = {
                        "case": case.label or case.image_path.stem,
                        "image": case.image_path.name,
                        "model_path": "MultiPassAnalyzer",
                        "openclaw_analyze_calls": calls,
                        "coarse_passes": 1 if calls else 0,
                        "zoom_passes": max(0, calls - 1),
                        "crop_calls": crops,
                        "max_zoom_targets": multi_pass_max_targets,
                    }
                    with trace_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(trace, ensure_ascii=False) + "\n")
            return result

        return await run_evaluation(
            cases,
            analyze,
            output_dir=output_dir,
            gateway_mode=mode,
            case_metadata=lambda case: {
                "local_image_quality": local_quality_by_case.get(
                    case.label or case.image_path.stem,
                    {},
                ),
                "local_signal_candidates": local_signal_by_case.get(
                    case.label or case.image_path.stem,
                    {},
                ),
            },
        )

    if mode == "mock":
        payloads = [_mock_payload_for(c) for c in cases]
        async with _MockGateway(payloads) as gw:
            client = _make_client(gw.url, timeout_sec=timeout_sec)
            try:
                return await analyze_with_client(client)
            finally:
                await client.disconnect()

    client = _make_client(gateway_url, timeout_sec=timeout_sec)
    try:
        return await analyze_with_client(client)
    finally:
        await client.disconnect()


def _make_client(gateway_url: str, *, timeout_sec: int) -> OpenClawClient:
    return OpenClawClient(
        gateway_url=gateway_url,
        timeout_sec=timeout_sec,
        connect_timeout_sec=timeout_sec,
        inference_timeout_sec=timeout_sec,
    )


def _limited_cases(cases: list[Any], limit: int) -> tuple[list[Any], int]:
    """Return the console preview slice and remaining count.

    ``limit <= 0`` means print all cases. Full per-case evidence is always
    written to ``scorecard.json`` and ``results/*.json``.
    """
    if limit <= 0 or len(cases) <= limit:
        return cases, 0
    return cases[:limit], len(cases) - limit


def _configure_eval_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level)
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(level))


def _print_summary(
    report: EvalReport,
    output_dir: Path,
    *,
    case_print_limit: int = 50,
) -> None:
    print("\n" + "=" * 60)
    print(f"  RECOGNITION SCORECARD  (mode={report.gateway_mode})")
    print("=" * 60)
    print(f"  cases scored ........ {report.scored}/{report.total} "
          f"(errors={report.error_count})")
    print(f"  severity accuracy ... {report.severity_accuracy:.0%} (exact)")
    print(f"  abnormal accuracy ... {report.severity_abnormal_accuracy:.0%} "
          f"(normal vs abnormal)")
    print(f"  strict pass rate .... {report.strict_pass_rate:.0%}")
    print(f"  partial credit ...... {report.mean_partial_credit:.0%} (mean)")
    print(f"  keyword recall ...... {report.mean_keyword_recall:.0%} (mean)")
    print(f"  negative recall ..... {report.mean_negative_recall:.0%} (mean)")
    print(f"  schema pass rate .... {report.schema_pass_rate:.0%}")
    print(f"  bbox in-bounds ...... {report.bbox_in_bounds_rate:.0%}")
    print(f"  mean latency ........ {report.mean_latency_ms:.0f} ms")
    print("-" * 60)
    printable_cases, remaining_cases = _limited_cases(
        report.cases,
        limit=case_print_limit,
    )
    for case in printable_cases:
        flag = "OK " if case.strict_pass else "MISS"
        if case.error:
            flag = "ERR"
        print(f"  [{flag}] {case.case_label:<24} "
              f"exp={case.expected_severity:<8} got={case.actual_severity:<8} "
              f"partial={case.partial_credit:.0%} "
              f"recall={case.keyword_recall:.0%}")
    if remaining_cases:
        print(
            f"      ... {remaining_cases} more case rows in scorecard.json "
            f"(use --case-print-limit 0 to print all)"
        )
    # Framework coverage matrix (Task B): which checklist axes were exercised
    # by at least one normal AND one abnormal case.
    if report.axis_coverage:
        print("-" * 60)
        print("  FRAMEWORK COVERAGE  (checklist axes exercised by the dataset)")
        for mod_key, cov in sorted(report.axis_coverage.items()):
            print(f"    {mod_key}: {cov['covered_axes']}/{cov['total_axes']} axes "
                  f"touched ({cov['coverage_rate']:.0%}), "
                  f"{cov['fully_covered_axes']} fully covered "
                  f"(normal+abnormal, {cov['full_coverage_rate']:.0%})")
            if cov["missing_axes"]:
                print(f"      untested axes: {', '.join(cov['missing_axes'])}")
    if report.target_axis_performance:
        print("-" * 60)
        print("  TARGET AXIS PERFORMANCE  (paired to manifest target_axes)")
        for axis, perf in sorted(report.target_axis_performance.items()):
            print(
                f"    {axis}: n={perf['case_count']} "
                f"strict={perf['strict_pass_rate']:.0%} "
                f"partial={perf['mean_partial_credit']:.0%} "
                f"keyword={perf['mean_keyword_recall']:.0%}"
            )
    # Can't-miss hard gate (Task C).
    print("-" * 60)
    if report.cant_miss_total == 0:
        print("  CAN'T-MISS GATE ..... (no can't-miss cases in dataset)")
    elif report.cant_miss_passed:
        print(f"  CAN'T-MISS GATE ..... PASS "
              f"({report.cant_miss_caught_count}/{report.cant_miss_total} caught)")
    else:
        print(f"  CAN'T-MISS GATE ..... FAIL "
              f"({report.cant_miss_caught_count}/{report.cant_miss_total} caught)")
        for miss in report.cant_miss_missed:
            print(f"      MISSED: {miss}")
    strict_failures = report.perfect_failures()
    if strict_failures:
        print("-" * 60)
        print(f"  PERFECT GATE ........ FAIL ({len(strict_failures)} issue(s))")
        for failure in strict_failures[:20]:
            print(f"      {failure}")
        if len(strict_failures) > 20:
            print(f"      ... {len(strict_failures) - 20} more")
    else:
        print("-" * 60)
        print("  PERFECT GATE ........ PASS")
    print("=" * 60)
    print(f"  artifacts: {output_dir}")
    if report.gateway_mode == "mock":
        print("  NOTE: mock mode verifies the SCORING PIPELINE only, not model "
              "accuracy.\n        Provide a token + real gateway for a real "
              "benchmark.")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run recognition evaluation")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument(
        "--dataset",
        default="",
        help="Dataset directory under data/eval-datasets, e.g. 'meeti'.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Evaluate only the first N cases (0 = all).",
    )
    parser.add_argument("--gateway", default="ws://127.0.0.1:18789",
                        help="Real OpenClaw Gateway URL")
    parser.add_argument("--mock", action="store_true",
                        help="Use in-process mock gateway (no token needed)")
    parser.add_argument(
        "--require-perfect",
        action="store_true",
        help="Fail non-zero unless every case has perfect severity/recall/schema/bbox.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=_DEFAULT_TIMEOUT_SEC,
        help="Per-request Gateway/LLM timeout in seconds.",
    )
    parser.add_argument(
        "--multi-pass",
        action="store_true",
        help="Use app MultiPassAnalyzer: coarse read, crop abnormal bboxes, refine.",
    )
    parser.add_argument(
        "--multi-pass-max-targets",
        type=int,
        default=3,
        help="Maximum abnormal findings to crop/refine per image in --multi-pass mode.",
    )
    parser.add_argument(
        "--case-print-limit",
        type=int,
        default=50,
        help="Max per-case rows to print to console (0 = print all).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable per-request structlog debug/info logs.",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    _configure_eval_logging(args.verbose)

    manifest_path = args.manifest or (
        _DATASET_DIR / args.dataset / "manifest.json"
        if args.dataset
        else _DATASET_DIR / "manifest.json"
    )

    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}\n"
              f"Run: uv run python scripts/fetch-eval-datasets.py", file=sys.stderr)
        return 2

    cases = _load_cases(manifest_path)
    if args.limit:
        cases = cases[: args.limit]
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

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    output_dir = args.output or (_REPO_ROOT / "data" / "eval" / f"{mode}-{stamp}")
    output_dir.mkdir(parents=True, exist_ok=True)

    start = time.monotonic()
    try:
        report = asyncio.run(
            _run(
                cases,
                args.gateway,
                mode,
                output_dir,
                args.timeout_sec,
                multi_pass=args.multi_pass,
                multi_pass_max_targets=args.multi_pass_max_targets,
            )
        )
    except (ConnectionError, OSError) as exc:
        print(f"\nERROR: could not reach gateway at {args.gateway}: {exc}\n"
              f"Start the gateway (see REAL_TEST_RUNBOOK.md) or run with --mock.",
              file=sys.stderr)
        return 1
    elapsed = time.monotonic() - start
    _print_summary(report, output_dir, case_print_limit=args.case_print_limit)
    print(f"  total run time: {elapsed:.1f}s")
    # Task C hard gate: a missed can't-miss diagnosis fails CI (non-zero exit),
    # so a dropped STEMI blocks the build instead of just logging a line.
    if report.cant_miss_missed:
        print(f"\nFAIL: {len(report.cant_miss_missed)} can't-miss diagnosis(es) "
              f"were not caught. See CAN'T-MISS GATE above.", file=sys.stderr)
        return 3
    if args.require_perfect:
        failures = report.perfect_failures()
        if failures:
            print(f"\nFAIL: {len(failures)} strict evaluation issue(s). "
                  f"See PERFECT GATE above.", file=sys.stderr)
            return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
