from __future__ import annotations

import copy
import importlib.util
from datetime import date
from pathlib import Path


def _module():
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "validate-clinical-knowledge.py"
    )
    spec = importlib.util.spec_from_file_location("clinical_knowledge_validator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _registry(module):
    return copy.deepcopy(module.load_registry())


def _rule(registry, index: int = 0):
    return registry["rules"][index]


def test_registry_is_strictly_valid_and_generated_views_are_current() -> None:
    module = _module()
    registry = module.load_registry()

    assert module.validate_registry(registry, today=date(2026, 8, 28)) == []
    assert module.write_or_check_views(registry, check=True) == []
    assert registry["rules"]
    assert len(registry["axes"]["EKG"]) == 16


def test_registry_digest_covers_inventory_schema_and_document_paths() -> None:
    module = _module()
    baseline = _registry(module)
    baseline_digest = module.registry_digest(baseline)

    inventory_changed = _registry(module)
    inventory_changed["inventory"]["entries"][0]["locator"] += "_changed"
    schema_changed = _registry(module)
    schema_changed["schema"]["title"] += " changed"
    path_changed = _registry(module)
    path_changed["rule_documents"][0]["path"] = "rules/renamed.rule.yaml"

    assert module.REGISTRY_DIGEST_SCOPE == "canonical-input-documents-v1"
    assert module.registry_digest(inventory_changed) != baseline_digest
    assert module.registry_digest(schema_changed) != baseline_digest
    assert module.registry_digest(path_changed) != baseline_digest


def test_registry_rejects_empty_schema_and_wrong_schema_version() -> None:
    module = _module()
    empty = _registry(module)
    empty["schema"] = {"type": "object", "additionalProperties": False}

    errors = module.validate_registry(empty, today=date(2026, 8, 28))

    assert any("schema id/version mismatch" in error for error in errors)
    assert any("schema is incomplete" in error for error in errors)

    wrong_version = _registry(module)
    wrong_version["schema"]["properties"]["schema_version"]["const"] = 2
    errors = module.validate_registry(wrong_version, today=date(2026, 8, 28))
    assert any("clinical rule schema version must be 1" in error for error in errors)


def test_agent_view_excludes_eval_gold_vocabulary() -> None:
    module = _module()
    _human, agent = module.render_views(module.load_registry())

    assert "no evaluation gold labels or scorer aliases" in agent
    assert "cant_miss" not in agent
    assert "expected_severity" not in agent


def test_schema_rejects_unknown_missing_wrong_type_pattern_status_and_basis() -> None:
    module = _module()
    registry = _registry(module)
    rule = _rule(registry)
    rule["invented_key"] = True
    del rule["human"]["title"]
    rule["version"] = "v1"
    rule["status"] = ["active"]
    del rule["priority"]["basis"]
    del rule["runtime"]

    errors = module.validate_registry(registry, today=date(2026, 8, 28))

    assert any("unknown properties ['invented_key']" in error for error in errors)
    assert any("missing required property 'title'" in error for error in errors)
    assert any(
        "version: value does not match required pattern" in error for error in errors
    )
    assert any("status: expected type string" in error for error in errors)
    assert any("missing required property 'basis'" in error for error in errors)
    assert any("missing required property 'runtime'" in error for error in errors)


def test_axis_and_inventory_documents_also_reject_unknown_keys() -> None:
    module = _module()
    registry = _registry(module)
    registry["axis_documents"][0]["document"]["axis_typo"] = True
    registry["inventory"]["entries"][0]["inventory_typo"] = True

    errors = module.validate_registry(registry, today=date(2026, 8, 28))

    assert any("unknown properties ['axis_typo']" in error for error in errors)
    assert any("unknown properties ['inventory_typo']" in error for error in errors)


def test_dependency_free_walker_rejects_unsupported_schema_keywords() -> None:
    module = _module()
    registry = _registry(module)
    registry["schema"]["unevaluatedProperties"] = False

    errors = module.validate_registry(registry, today=date(2026, 8, 28))

    assert any(
        "unsupported schema keywords ['unevaluatedProperties']" in error
        for error in errors
    )


def test_semver_major_must_match_rule_id_suffix() -> None:
    module = _module()
    registry = _registry(module)
    _rule(registry)["rule_id"] = "ekg.renamed_rule.v2"

    errors = module.validate_registry(registry, today=date(2026, 8, 28))

    assert any(
        ".vN suffix must match semantic-version major" in error for error in errors
    )


def test_workflow_ids_are_unique_ordered_and_mapped_by_agent_steps() -> None:
    module = _module()
    registry = _registry(module)
    rule = _rule(registry)
    rule["human"]["workflow"].append(copy.deepcopy(rule["human"]["workflow"][0]))
    rule["agent"]["steps"][0]["id"] = "unmapped_step"
    rule["agent"]["steps"].append(copy.deepcopy(rule["agent"]["steps"][1]))

    errors = module.validate_registry(registry, today=date(2026, 8, 28))

    assert any("human workflow step ids duplicate" in error for error in errors)
    assert any("agent step ids duplicate" in error for error in errors)
    assert any("agent steps do not map to human workflow" in error for error in errors)

    registry = _registry(module)
    steps = _rule(registry)["agent"]["steps"]
    steps[0], steps[1] = steps[1], steps[0]
    errors = module.validate_registry(registry, today=date(2026, 8, 28))
    assert any("agent steps reorder the human workflow" in error for error in errors)


def test_agent_steps_reject_generic_refusal_or_disclaimer_boilerplate() -> None:
    module = _module()
    registry = _registry(module)
    _rule(registry)["agent"]["steps"][0]["instruction"] = (
        "As an AI language model, I cannot provide medical advice."
    )

    errors = module.validate_registry(registry, today=date(2026, 8, 28))

    assert any("generic refusal/disclaimer boilerplate" in error for error in errors)


def test_clinical_dates_must_be_ordered_and_active_review_current() -> None:
    module = _module()
    registry = _registry(module)
    human = _rule(registry)["human"]
    human["reviewed_on"] = "2026-09-01"
    human["review_due"] = "2026-08-01"
    human["sources"][0]["effective_date"] = "2027-01-01"

    errors = module.validate_registry(registry, today=date(2026, 8, 28))

    assert any("reviewed_on cannot be in the future" in error for error in errors)
    assert any("review_due must be after reviewed_on" in error for error in errors)
    assert any("effective_date is after reviewed_on" in error for error in errors)

    registry = _registry(module)
    _rule(registry)["human"]["review_due"] = "2026-08-27"
    errors = module.validate_registry(registry, today=date(2026, 8, 28))
    assert any("active clinical review is expired" in error for error in errors)


def test_unknown_modality_axis_and_output_severity_fail_closed() -> None:
    module = _module()
    registry = _registry(module)
    rule = _rule(registry)
    rule["modality"] = "MRI"
    rule["output"]["axes"].append("invented_axis")
    rule["output"]["severity_floor_if_confirmed"] = "urgent"

    errors = module.validate_registry(registry, today=date(2026, 8, 28))

    assert any(
        "modality: value 'MRI' is not in the allowed enum" in error for error in errors
    )
    assert any("modality has no canonical axis registry" in error for error in errors)
    assert any(
        "severity_floor_if_confirmed" in error and "enum" in error for error in errors
    )

    registry = _registry(module)
    rule = _rule(registry)
    rule["output"]["axes"].append("invented_axis")
    errors = module.validate_registry(registry, today=date(2026, 8, 28))
    assert any("unknown EKG output axes ['invented_axis']" in error for error in errors)


def test_priority_basis_and_tier_disclose_product_policy() -> None:
    module = _module()
    registry = _registry(module)
    rule = _rule(registry)
    rule["priority"]["basis"] = "product_safety_policy"

    errors = module.validate_registry(registry, today=date(2026, 8, 28))

    if rule["output"]["severity_floor_if_confirmed"] is None:
        assert any(
            "review-only output requires review tier" in error for error in errors
        )
    else:
        rule["priority"]["tier"] = "review"
        errors = module.validate_registry(registry, today=date(2026, 8, 28))
        assert any("requires matching product-safety tier" in error for error in errors)


def test_runtime_conditions_validate_operator_operand_axis_and_severity_parity() -> (
    None
):
    module = _module()
    registry = _registry(module)
    rule = _rule(registry)
    rule["runtime"]["conditions"][0] = {
        "field": "checklist.invented_axis",
        "op": "severity_at_most",
        "value": "info",
    }
    rule["runtime"]["escalate_to"] = (
        "critical"
        if rule["output"]["severity_floor_if_confirmed"] != "critical"
        else "warning"
    )

    errors = module.validate_registry(registry, today=date(2026, 8, 28))

    assert any("operator 'severity_at_most' is invalid" in error for error in errors)
    assert any("unknown EKG runtime checklist axis" in error for error in errors)
    assert any(
        "runtime escalation and output severity floor differ" in error
        for error in errors
    )


def test_generated_runtime_requires_exact_canonical_behavior_parity() -> None:
    module = _module()
    registry = _registry(module)
    entry = next(
        row for row in registry["inventory"]["entries"] if row["status"] == "mapped"
    )
    canonical = next(
        rule for rule in registry["rules"] if rule["rule_id"] == entry["canonical_rule"]
    )
    canonical["runtime"]["message"] += " changed"

    errors = module.validate_registry(registry, today=date(2026, 8, 28))
    generated_errors = module.write_or_check_views(registry, check=True)

    assert errors == []
    assert any("generated view is stale" in error for error in generated_errors)


def test_inventory_locator_and_pytest_node_are_verified() -> None:
    module = _module()
    registry = _registry(module)
    entry = registry["inventory"]["entries"][0]
    entry["locator"] = "symbol_that_does_not_exist"
    entry["parity_test"] = (
        "tests/unit/test_clinical_knowledge_registry.py::missing_parity_test"
    )

    errors = module.validate_registry(registry, today=date(2026, 8, 28))

    assert any("locator is absent from legacy source" in error for error in errors)
    assert any("parity test node is not declared" in error for error in errors)


def test_inventory_status_and_mapped_linkage_are_fail_closed() -> None:
    module = _module()
    registry = _registry(module)
    mapped = [
        row for row in registry["inventory"]["entries"] if row["status"] == "mapped"
    ]
    del mapped[0]["canonical_rule"]
    mapped[1]["status"] = "mapped_pending"

    errors = module.validate_registry(registry, today=date(2026, 8, 28))

    assert any("mapped entry requires canonical_rule" in error for error in errors)
    assert any(
        "mapped_pending" in error and "allowed enum" in error for error in errors
    )
