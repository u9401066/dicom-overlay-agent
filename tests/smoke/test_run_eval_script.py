from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

from dicom_overlay.domain.entities import Modality, Severity
from dicom_overlay.infrastructure.eval_harness import EvalCase, score_case
from dicom_overlay.infrastructure.openclaw_client import OpenClawClient


def _load_run_eval_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "run-eval.py"
    spec = importlib.util.spec_from_file_location("run_eval_script", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_load_cases_defaults_valid_regions_from_modality(tmp_path: Path) -> None:
    module = _load_run_eval_module()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "image": "ekg.png",
                        "modality": "EKG",
                        "expected_severity": "normal",
                    },
                    {
                        "image": "cxr.png",
                        "modality": "CXR",
                        "expected_severity": "normal",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = module._load_cases(manifest)

    assert "lead_I" in cases[0].valid_regions
    assert "rhythm_strip" in cases[0].valid_regions
    assert "right_upper_lung" in cases[1].valid_regions
    assert "left_cp_angle" in cases[1].valid_regions


def test_mock_payload_scores_perfect_for_normal_case(tmp_path: Path) -> None:
    module = _load_run_eval_module()
    case = EvalCase(
        image_path=tmp_path / "cxr.png",
        modality=Modality.CXR,
        expected_severity=Severity.NORMAL,
        expected_keywords=("clear", "no acute", "normal"),
        expected_negatives=("no pneumothorax", "no effusion", "no consolidation"),
        label="normal_cxr",
    )
    payload = module._mock_payload_for(case)

    client = OpenClawClient.__new__(OpenClawClient)
    result = client._parse_result(payload, elapsed_ms=0, request_modality=case.modality)
    score = score_case(case, result, latency_ms=0)

    assert score.severity_match is True
    assert score.keyword_misses == []
    assert score.negative_misses == []


def test_make_client_uses_eval_timeout_for_inference() -> None:
    module = _load_run_eval_module()

    client = module._make_client("ws://example.invalid", timeout_sec=90)

    assert client._timeout == 90
    assert client._connect_timeout == 90
    assert client._inference_timeout == 90


def test_counting_analyzer_counts_delegated_analyze_calls() -> None:
    module = _load_run_eval_module()

    class Inner:
        async def analyze(
            self,
            image_base64: str,
            modality: Modality,
            valid_regions: list[str],
        ) -> tuple[str, Modality, list[str]]:
            return image_base64, modality, valid_regions

        async def chat(self, message: str) -> str:
            return message

        async def connect(self) -> None:
            return None

        async def disconnect(self) -> None:
            return None

        def is_connected(self) -> bool:
            return True

    counter = module._CountingAnalyzer(Inner())

    asyncio.run(counter.analyze("img", Modality.EKG, ["lead_I"]))
    asyncio.run(counter.analyze("img", Modality.EKG, ["lead_II"]))

    assert counter.analyze_calls == 2


def test_limited_cases_caps_console_preview() -> None:
    module = _load_run_eval_module()

    shown, remaining = module._limited_cases(list(range(1000)), limit=50)

    assert shown == list(range(50))
    assert remaining == 950


def test_limited_cases_zero_prints_all() -> None:
    module = _load_run_eval_module()

    shown, remaining = module._limited_cases([1, 2, 3], limit=0)

    assert shown == [1, 2, 3]
    assert remaining == 0
