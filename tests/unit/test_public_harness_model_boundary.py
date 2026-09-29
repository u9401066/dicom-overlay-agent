"""Direct public model ownership; no local re-exports or duplicate definitions."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from dicom_overlay.domain import entities, services
from medical_image_harness import models, multipass, protocols

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_NAMES = frozenset(
    {
        "AnalysisResult",
        "ChecklistItem",
        "Finding",
        "Modality",
        "RegionRect",
        "Severity",
        "UserRegionAnnotation",
    }
)


@pytest.mark.parametrize("name", sorted(PUBLIC_NAMES))
def test_models_are_owned_only_by_public_harness(name):
    assert getattr(models, name).__module__ == "medical_image_harness.models"
    assert not hasattr(entities, name), "Do not add a compatibility re-export"


def test_all_consumers_import_public_types_directly():
    failures = []
    for folder in ("src", "scripts", "tests"):
        for path in (ROOT / folder).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text("utf-8"))):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module == "dicom_overlay.domain.entities"
                    and any(alias.name in PUBLIC_NAMES for alias in node.names)
                ):
                    failures.append(str(path.relative_to(ROOT)))
    assert not failures


def test_domain_does_not_redefine_public_model_classes():
    for path in (ROOT / "src/dicom_overlay/domain").glob("*.py"):
        classes = {
            n.name
            for n in ast.walk(ast.parse(path.read_text("utf-8")))
            if isinstance(n, ast.ClassDef)
        }
        assert not classes.intersection(PUBLIC_NAMES), path.name


def test_public_models_import_without_gui_capture_or_network_dependencies():
    process = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys,json; from medical_image_harness import models; "
            "print(json.dumps(sorted(n for n in sys.modules if "
            "n.split('.')[0] in {'PyQt6','mss','win32gui','websockets','dicom_overlay'})))",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert json.loads(process.stdout) == []


def test_app_draft_is_not_silently_promoted_to_canonical_clinical_contract():
    draft = models.AnalysisResult(
        modality=models.Modality.EKG,
        summary="Synthetic draft",
        severity=models.Severity.INFO,
        findings=[],
        checklist={},
    )
    with pytest.raises(ValueError):
        draft.to_contract_payload()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_public_bbox_rejects_nonfinite_coordinates(value):
    with pytest.raises(ValueError):
        models.RegionRect(value, 0.1, 0.2, 0.2)


def test_submodule_pin_and_packaged_contract_resources_exist():
    harness = ROOT / "third_party/medical-image-agent-harness"
    assert (harness / "schemas/analysis-result.schema.json").is_file()
    assert (harness / ".agents/skills/medical-image-reading/SKILL.md").is_file()
    result = subprocess.run(
        ["git", "-C", str(harness), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert (harness / "src/medical_image_harness/py.typed").is_file()
    assert result.stdout.strip() == "d9798dae0cf4ac3e25578da127801bce6d4391b3"


def test_engine_layout_and_analyzer_port_have_no_app_duplicates():
    assert not (ROOT / "src/dicom_overlay/application/multi_pass.py").exists()
    assert not (ROOT / "src/dicom_overlay/domain/ekg_layout.py").exists()
    assert not hasattr(services, "VisionAnalyzerService")
    assert (
        multipass.MultiPassInterpreter.__module__ == "medical_image_harness.multipass"
    )
    assert (
        protocols.VisionAnalyzerService.__module__ == "medical_image_harness.protocols"
    )
    forbidden = {
        "dicom_overlay.application.multi_pass",
        "dicom_overlay.domain.ekg_layout",
    }
    for folder in ("src", "scripts", "tests"):
        for path in (ROOT / folder).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text("utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    assert node.module not in forbidden, path
                    if node.module == "dicom_overlay.domain.services":
                        assert all(
                            n.name != "VisionAnalyzerService" for n in node.names
                        ), path
                elif isinstance(node, ast.Import):
                    assert all(n.name not in forbidden for n in node.names), path


def test_public_engine_imports_without_app_gui_capture_or_network():
    process = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys,json; from medical_image_harness import multipass,ekg_layout,protocols; "
            "print(json.dumps(sorted(n for n in sys.modules if "
            "n.split('.')[0] in {'PyQt6','mss','win32gui','websockets','dicom_overlay'})))",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert json.loads(process.stdout) == []


@pytest.mark.parametrize(
    "path", ["src/dicom_overlay/__main__.py", "scripts/run-eval.py"]
)
def test_live_entrypoints_use_public_engine_with_explicit_host_policy(path):
    tree = ast.parse((ROOT / path).read_text("utf-8"))
    assert any(
        isinstance(n, ast.ImportFrom)
        and n.module == "medical_image_harness.multipass"
        and "MultiPassInterpreter" in {a.name for a in n.names}
        for n in ast.walk(tree)
    )
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "MultiPassInterpreter"
    ]
    assert len(calls) == 1
    kwargs = {k.arg: k.value for k in calls[0].keywords}
    if path == "src/dicom_overlay/__main__.py":
        assert ast.literal_eval(kwargs["prefer_ekg_group_coverage"]) is True
    assert isinstance(kwargs["checklist_keys_for"], ast.Lambda)
    stage_tools = kwargs["stage_tools"]
    assert isinstance(stage_tools, ast.Call)
    assert (
        isinstance(stage_tools.func, ast.Name) and stage_tools.func.id == "StageTools"
    )
    assert {k.arg: ast.literal_eval(k.value) for k in stage_tools.keywords} == {
        "coarse": "openclaw_vision_analysis",
        "refinement": "crop_region_base64+openclaw_vision_analysis",
        "finalize": "openclaw_report_reconciliation",
    }
