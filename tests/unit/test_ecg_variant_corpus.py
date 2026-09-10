from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

import pytest
from PIL import Image

from dicom_overlay.application.interpretation_harness import (
    PARTIAL_ECG_VISIBLE_PIXELS_SCOPE,
    build_coarse_analysis_prompt,
)
from dicom_overlay.domain.entities import Modality
from dicom_overlay.infrastructure.ecg_variant_corpus import (
    EKG_CHECKLIST_AXES,
    EKG_NAMED_REGIONS,
    VARIANT_NAMES,
    build_ecg_variants,
    build_variant_corpus,
    parse_partial_ecg_input_contract,
    partial_ecg_text_claim_failures,
    sha256_bytes,
    verify_variant_corpus,
)

if TYPE_CHECKING:
    from pathlib import Path


def _synthetic_png(width: int = 120, height: int = 120) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    pixels = image.load()
    assert pixels is not None
    for y in range(height):
        for x in range(width):
            pixels[x, y] = (x % 251, y % 251, (x + y) % 251)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_build_ecg_variants_has_fixed_geometry_and_source_subset_pixels() -> None:
    source_png = _synthetic_png()
    variants = {item.name: item for item in build_ecg_variants(source_png)}

    assert tuple(variants) == VARIANT_NAMES
    assert (variants["crop_top_20"].width, variants["crop_top_20"].height) == (
        120,
        96,
    )
    assert variants["crop_top_20"].transform["crop_box_px"] == [0, 24, 120, 120]
    assert variants["crop_left_20"].transform["crop_box_px"] == [24, 0, 120, 120]
    assert variants["crop_vertical_middle_50"].height == 60
    assert variants["crop_horizontal_band_06_of_12"].height == 10
    assert "single_row_06_of_12" not in variants
    assert (
        min(
            variants["tiny_short_edge_48px"].width,
            variants["tiny_short_edge_48px"].height,
        )
        == 48
    )

    with (
        Image.open(io.BytesIO(source_png)) as source,
        Image.open(io.BytesIO(variants["crop_top_20"].png_bytes)) as cropped,
    ):
        assert cropped.getpixel((17, 0)) == source.getpixel((17, 24))
    with Image.open(io.BytesIO(variants["mask_labels_left_12"].png_bytes)) as masked:
        assert masked.getpixel((0, 50)) == (255, 255, 255)
        assert masked.getpixel((30, 50)) == (30, 50, 80)


def test_variant_generation_is_byte_deterministic() -> None:
    source = _synthetic_png(144, 96)
    first = build_ecg_variants(source)
    second = build_ecg_variants(source)

    assert [(row.name, sha256_bytes(row.png_bytes)) for row in first] == [
        (row.name, sha256_bytes(row.png_bytes)) for row in second
    ]


def test_corpus_manifest_is_answer_free_relocatable_and_opaque(tmp_path: Path) -> None:
    source = tmp_path / "patient-name-must-not-leak.png"
    source.write_bytes(_synthetic_png())
    output = tmp_path / "corpus"

    manifest = build_variant_corpus([source], output)
    persisted = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert persisted == manifest
    assert manifest["answer_free"] is True
    assert manifest["variant_count"] == len(VARIANT_NAMES)
    assert manifest["case_count"] == len(VARIANT_NAMES)
    serialized = json.dumps(manifest)
    assert "patient-name-must-not-leak" not in serialized
    assert str(tmp_path) not in serialized
    for record in manifest["variants"]:
        image_path = output / record["image"]
        assert image_path.is_file()
        assert sha256_bytes(image_path.read_bytes()) == record["variant_sha256"]
    forbidden_answer_fields = {
        "expected_severity",
        "keywords",
        "negatives",
        "target_axes",
        "cant_miss",
    }
    for case in manifest["cases"]:
        assert case["valid_regions"] == []
        assert forbidden_answer_fields.isdisjoint(case)
        contract = parse_partial_ecg_input_contract(
            case,
            image_path=output / case["image"],
        )
        assert contract is not None
        assert contract.analysis_regions == (PARTIAL_ECG_VISIBLE_PIXELS_SCOPE,)
        assert contract.claimable_regions == ()
        assert contract.non_claimable_regions == EKG_NAMED_REGIONS
        assert contract.required_output["incomplete"] is True
        assert contract.required_output["review_required"] is True
        assert contract.limitation_class
        assert set(contract.context_dependent_axes)
    assert len(
        {
            case["partial_input"]["expected_visibility"]["limitation_class"]
            for case in manifest["cases"]
        }
    ) == len(VARIANT_NAMES)
    assert verify_variant_corpus(output) == manifest

    tiny = next(
        case
        for case in manifest["cases"]
        if case["partial_input"]["variant"] == "tiny_short_edge_48px"
    )
    assert tiny["partial_input"]["expected_visibility"][
        "context_dependent_axes"
    ] == list(EKG_CHECKLIST_AXES)


def test_duplicate_source_content_fails_closed(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(_synthetic_png())
    second.write_bytes(first.read_bytes())

    with pytest.raises(ValueError, match="duplicate source image content"):
        build_variant_corpus([first, second], tmp_path / "out")


def test_rejects_non_png_and_nonempty_output(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be a PNG"):
        build_ecg_variants(b"not-a-png")

    source = tmp_path / "source.png"
    source.write_bytes(_synthetic_png())
    output = tmp_path / "corpus"
    output.mkdir()
    (output / "stale.png").write_bytes(b"stale")

    with pytest.raises(ValueError, match="output directory must be empty"):
        build_variant_corpus([source], output)


def test_corpus_verifier_rejects_tamper_and_residue(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(_synthetic_png())
    output = tmp_path / "corpus"
    manifest = build_variant_corpus([source], output)
    first_image = output / manifest["variants"][0]["image"]
    first_image.write_bytes(first_image.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="image digest mismatch"):
        verify_variant_corpus(output)

    first_image.write_bytes(
        next(
            variant.png_bytes
            for variant in build_ecg_variants(source.read_bytes())
            if variant.name == manifest["variants"][0]["variant"]
        )
    )
    (output / "stale.png").write_bytes(b"stale")
    with pytest.raises(ValueError, match="stale or unmanifested"):
        verify_variant_corpus(output)


def test_partial_contract_rejects_answer_leak_and_hash_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(_synthetic_png())
    output = tmp_path / "corpus"
    manifest = build_variant_corpus([source], output)
    case = dict(manifest["cases"][0])
    case["keywords"] = ["hidden answer"]

    with pytest.raises(ValueError, match="answer-free"):
        parse_partial_ecg_input_contract(
            case,
            image_path=output / case["image"],
        )

    nested = dict(manifest["cases"][0])
    nested["metadata"] = {"ground_truth": {"diagnosis": "hidden answer"}}
    with pytest.raises(ValueError, match="answer-free"):
        parse_partial_ecg_input_contract(
            nested,
            image_path=output / nested["image"],
        )

    case.pop("keywords")
    image_path = output / case["image"]
    image_path.write_bytes(image_path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="does not match image bytes"):
        parse_partial_ecg_input_contract(
            case,
            image_path=image_path,
        )


def _persist_manifest(output: Path, manifest: dict[str, object]) -> None:
    digest_payload = dict(manifest)
    digest_payload.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = sha256_bytes(
        json.dumps(
            digest_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    (output / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("target", "field", "expected"),
    [
        ("root", "metadata", "root keys"),
        ("variant", "metadata", "record keys"),
        ("case", "metadata", "case keys"),
    ],
)
def test_partial_manifest_nodes_use_closed_allow_lists(
    tmp_path: Path,
    target: str,
    field: str,
    expected: str,
) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(_synthetic_png())
    output = tmp_path / "corpus"
    manifest = build_variant_corpus([source], output)
    node = (
        manifest
        if target == "root"
        else manifest["variants"][0]
        if target == "variant"
        else manifest["cases"][0]
    )
    assert isinstance(node, dict)
    node[field] = "non-clinical-extra"
    _persist_manifest(output, manifest)

    with pytest.raises(ValueError, match=expected):
        verify_variant_corpus(output)


def test_partial_manifest_rejects_answer_field_at_root_or_variant(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(_synthetic_png())
    output = tmp_path / "corpus"
    manifest = build_variant_corpus([source], output)
    manifest["variants"][0]["diagnosis"] = "hidden"
    _persist_manifest(output, manifest)

    with pytest.raises(ValueError, match="recursively answer-free"):
        verify_variant_corpus(output)


def test_partial_text_gate_allows_explicit_layout_limitation_but_not_claim() -> None:
    assert (
        partial_ecg_text_claim_failures(
            (
                "Full 12-lead context is unavailable.",
                "No complete lead inventory can be verified.",
            )
        )
        == []
    )
    assert partial_ecg_text_claim_failures(("This is a complete 12-lead ECG.",)) == [
        "partial ECG text asserts an unverified full lead layout"
    ]


def test_partial_runtime_scope_adds_fail_closed_prompt_guidance() -> None:
    prompt = build_coarse_analysis_prompt(
        modality=Modality.EKG,
        valid_regions=[PARTIAL_ECG_VISIBLE_PIXELS_SCOPE],
    )

    assert "deliberately incomplete/cropped ECG robustness case" in prompt
    assert "Do not infer or locally reconstruct a complete 12-lead inventory" in prompt
    assert "use regions=[]" in prompt
