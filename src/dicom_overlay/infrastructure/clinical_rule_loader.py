"""Compatibility exports for the public clinical rule-pack loader."""

from medical_image_harness.rule_loader import (
    RULE_PACK_GLOB,
    build_clinical_engine,
    load_rule_pack_dir,
    merge_rules,
)

__all__ = [
    "RULE_PACK_GLOB",
    "build_clinical_engine",
    "load_rule_pack_dir",
    "merge_rules",
]
