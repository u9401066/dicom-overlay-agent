from __future__ import annotations

import pytest

from dicom_overlay.infrastructure.public_cxr_dataset import (
    HuggingFaceImageRow,
    build_hf_rows_url,
    build_public_cxr_manifest,
)


def test_build_hf_rows_url_honors_endpoint_and_query() -> None:
    url = build_hf_rows_url(
        dataset_id="hf-vision/chest-xray-pneumonia",
        config="default",
        split="train",
        offset=200,
        length=100,
        endpoint="https://hf-mirror.com",
    )

    assert url.startswith("https://hf-mirror.com/datasets-server/rows?")
    assert "dataset=hf-vision%2Fchest-xray-pneumonia" in url
    assert "offset=200" in url
    assert "length=100" in url


def test_build_public_cxr_manifest_maps_rows_to_existing_eval_schema() -> None:
    rows = [
        HuggingFaceImageRow(
            image_url="https://example.invalid/normal.png",
            label="NORMAL",
            row_idx=0,
        ),
        HuggingFaceImageRow(
            image_url="https://example.invalid/pneumonia.png",
            label="PNEUMONIA",
            row_idx=1,
        ),
    ]

    manifest = build_public_cxr_manifest(
        rows,
        dataset_id="hf-vision/chest-xray-pneumonia",
        image_prefix="cxr",
        min_cases=2,
    )

    assert manifest["dataset"] == "public-cxr"
    assert manifest["source"]["dataset_id"] == "hf-vision/chest-xray-pneumonia"
    cases = manifest["cases"]
    assert len(cases) == 2
    assert cases[0]["expected_severity"] == "normal"
    assert "no pneumothorax" in cases[0]["negatives"]
    assert cases[1]["expected_severity"] == "warning"
    assert "pneumonia" in cases[1]["keywords"]
    assert "lungs" in cases[1]["target_axes"]
    assert cases[1]["source_url"] == "https://example.invalid/pneumonia.png"


def test_build_public_cxr_manifest_requires_minimum_public_cases() -> None:
    rows = [
        HuggingFaceImageRow(
            image_url=f"https://example.invalid/{i}.png",
            label="NORMAL",
            row_idx=i,
        )
        for i in range(999)
    ]

    with pytest.raises(ValueError, match="at least 1000"):
        build_public_cxr_manifest(
            rows,
            dataset_id="hf-vision/chest-xray-pneumonia",
            image_prefix="cxr",
            min_cases=1000,
        )
