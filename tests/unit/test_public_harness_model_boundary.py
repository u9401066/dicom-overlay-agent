"""Direct public model ownership; no local re-exports or duplicate definitions."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from dicom_overlay.domain import entities
from medical_image_harness import models

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_NAMES = frozenset({
    "AnalysisResult", "ChecklistItem", "Finding", "Modality", "RegionRect",
    "Severity", "UserRegionAnnotation",
})


@pytest.mark.parametrize("name", sorted(PUBLIC_NAMES))
def test_models_are_owned_only_by_public_harness(name):
    assert getattr(models, name).__module__ == "medical_image_harness.models"
    assert not hasattr(entities, name), "Do not add a compatibility re-export"


def test_all_consumers_import_public_types_directly():
    failures = []
    for folder in ("src", "scripts", "tests"):
        for path in (ROOT / folder).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text("utf-8"))):
                if (isinstance(node, ast.ImportFrom)
                        and node.module == "dicom_overlay.domain.entities"
                        and any(alias.name in PUBLIC_NAMES for alias in node.names)):
                    failures.append(str(path.relative_to(ROOT)))
    assert not failures


def test_domain_does_not_redefine_public_model_classes():
    for path in (ROOT / "src/dicom_overlay/domain").glob("*.py"):
        classes = {n.name for n in ast.walk(ast.parse(path.read_text("utf-8")))
                   if isinstance(n, ast.ClassDef)}
        assert not classes.intersection(PUBLIC_NAMES), path.name


def test_public_models_import_without_gui_capture_or_network_dependencies():
    process = subprocess.run(
        [sys.executable, "-I", "-c",
         "import sys,json; from medical_image_harness import models; "
         "print(json.dumps(sorted(n for n in sys.modules if "
         "n.split('.')[0] in {'PyQt6','mss','win32gui','websockets','dicom_overlay'})))"],
        check=True, capture_output=True, text=True, timeout=15,
    )
    assert json.loads(process.stdout) == []


def test_app_draft_is_not_silently_promoted_to_canonical_clinical_contract():
    draft = models.AnalysisResult(modality=models.Modality.EKG, summary="Synthetic draft",
                                  severity=models.Severity.INFO, findings=[], checklist={})
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
    result = subprocess.run(["git", "-C", str(harness), "rev-parse", "HEAD"],
                            check=True, capture_output=True, text=True, timeout=10)
    assert (harness / "src/medical_image_harness/py.typed").is_file()
    assert result.stdout.strip() == "efeff23d8dc07c74e90cb9900cad5bdb45875c4b"
