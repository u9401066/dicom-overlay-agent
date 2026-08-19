"""Compatibility exports for the public clinical consistency engine."""

from medical_image_harness.clinical_rules import (
    ClinicalConsistencyEngine,
    ClinicalRule,
    ConditionError,
    RuleCondition,
    RuleViolation,
    builtin_rules,
    default_engine,
    group_by_modality,
)

__all__ = [
    "ClinicalConsistencyEngine",
    "ClinicalRule",
    "ConditionError",
    "RuleCondition",
    "RuleViolation",
    "builtin_rules",
    "default_engine",
    "group_by_modality",
]
