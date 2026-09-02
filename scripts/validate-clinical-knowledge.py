"""Validate and render the versioned clinical-knowledge YAML registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import pprint
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_ROOT = ROOT / "clinical_knowledge"
HUMAN_VIEW = KNOWLEDGE_ROOT / "generated" / "human-catalogue.md"
AGENT_VIEW = KNOWLEDGE_ROOT / "generated" / "agent-steps.md"
RUNTIME_VIEW = ROOT / "src" / "dicom_overlay" / "domain" / "generated_clinical_rules.py"
CLINICAL_SCHEMA_VERSION = 1
CLINICAL_SCHEMA_ID = (
    "https://dicom-overlay-agent.local/schema/clinical-rule-v1.json"
)
REGISTRY_DIGEST_SCOPE = "canonical-input-documents-v1"
TEST_KINDS = frozenset({"positive", "negative", "uncertain", "partial"})
_TEXT_OPS = frozenset(
    {
        "contains_any",
        "contains_any_asserted",
        "contains_any_non_negated",
        "not_contains_any",
        "equals",
    }
)
_SEVERITY_OPS = frozenset({"severity_at_most", "severity_at_least", "equals"})
_SEVERITIES = frozenset({"normal", "info", "warning", "critical"})
_SCHEMA_TYPES = frozenset(
    {"object", "array", "string", "integer", "number", "boolean", "null"}
)
_SCHEMA_KEYS = frozenset(
    {
        "$schema",
        "$id",
        "$defs",
        "$ref",
        "title",
        "description",
        "type",
        "const",
        "enum",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minLength",
        "maxLength",
        "pattern",
        "format",
    }
)
_AGENT_BOILERPLATE = (
    re.compile(r"\bas an ai (?:language )?model\b", re.IGNORECASE),
    re.compile(
        r"\bi (?:cannot|can't|am unable to) (?:provide|offer|give) "
        r"(?:medical|clinical) (?:advice|diagnosis|guidance)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bnot (?:a )?substitute for (?:professional )?medical "
        r"(?:advice|care)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bseek (?:professional )?medical advice\b", re.IGNORECASE),
    re.compile(r"我(?:是|只是).{0,8}(?:AI|人工智慧).{0,12}(?:無法|不能)"),
    re.compile(r"(?:僅供參考|不能取代|無法提供).{0,16}(?:醫療|醫師|診斷)"),
)


def _yaml_mapping(path: Path, errors: list[str]) -> dict[str, Any]:
    if not path.is_file():
        errors.append(f"missing registry file: {path}")
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        errors.append(f"cannot load {path}: {exc}")
        return {}
    if not isinstance(raw, dict):
        errors.append(f"{path}: document root must be an object")
        return {}
    return raw


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _yaml_candidates(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}
    )


def load_registry(root: Path = KNOWLEDGE_ROOT) -> dict[str, Any]:
    """Load source documents without silently discarding malformed input."""
    load_errors: list[str] = []
    rule_documents: list[dict[str, Any]] = []
    rules: list[Any] = []
    versions: set[str] = set()
    rule_paths = _yaml_candidates(root / "rules")
    if not rule_paths:
        load_errors.append("no clinical rule documents found")
    for path in rule_paths:
        if not path.name.endswith(".rule.yaml"):
            load_errors.append(
                f"unsupported rule filename (expected *.rule.yaml): "
                f"{_relative(path, root)}"
            )
            continue
        raw = _yaml_mapping(path, load_errors)
        rule_documents.append({"path": _relative(path, root), "document": raw})
        version = raw.get("registry_version")
        if isinstance(version, str):
            versions.add(version)
        raw_rules = raw.get("rules")
        if isinstance(raw_rules, list):
            rules.extend(raw_rules)

    axis_documents: list[dict[str, Any]] = []
    axes: dict[str, set[str]] = {}
    axis_paths = _yaml_candidates(root / "axes")
    if not axis_paths:
        load_errors.append("no clinical axis documents found")
    for path in axis_paths:
        if not path.name.endswith(".axes.yaml"):
            load_errors.append(
                f"unsupported axis filename (expected *.axes.yaml): "
                f"{_relative(path, root)}"
            )
            continue
        raw = _yaml_mapping(path, load_errors)
        axis_documents.append({"path": _relative(path, root), "document": raw})
        modality, raw_axes = raw.get("modality"), raw.get("axes")
        if isinstance(modality, str) and isinstance(raw_axes, list):
            axes[modality] = {item for item in raw_axes if isinstance(item, str)}

    inventory_path = root / "legacy-inventory.yaml"
    inventory = _yaml_mapping(inventory_path, load_errors)
    schema_path = root / "schema" / "rule.schema.json"
    schema: dict[str, Any] = {}
    if not schema_path.is_file():
        load_errors.append(f"missing registry schema: {schema_path}")
    else:
        try:
            loaded_schema = json.loads(schema_path.read_text(encoding="utf-8"))
            if isinstance(loaded_schema, dict):
                schema = loaded_schema
            else:
                load_errors.append(f"{schema_path}: schema root must be an object")
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            load_errors.append(f"cannot load {schema_path}: {exc}")

    return {
        "versions": versions,
        "rules": rules,
        "axes": axes,
        "inventory": inventory,
        "schema": schema,
        "rule_documents": rule_documents,
        "axis_documents": axis_documents,
        "inventory_document": {
            "path": _relative(inventory_path, root),
            "document": inventory,
        },
        "registry_digest_scope": REGISTRY_DIGEST_SCOPE,
        "knowledge_root": root,
        "repository_root": root.parent,
        "load_errors": load_errors,
    }


def _json_value(value: Any) -> Any:
    """Convert YAML timestamp scalars to their JSON-schema representation."""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _schema_definition_errors(
    schema: Any, *, path: str = "$", root: dict[str, Any] | None = None
) -> list[str]:
    """Reject schema keywords our dependency-free walker cannot enforce."""
    if not isinstance(schema, dict):
        return [f"{path}: schema node must be an object"]
    root = schema if root is None else root
    errors: list[str] = []
    unknown = set(schema) - _SCHEMA_KEYS
    if unknown:
        errors.append(f"{path}: unsupported schema keywords {sorted(unknown)}")
    type_value = schema.get("type")
    if type_value is not None:
        if isinstance(type_value, str):
            types = [type_value]
        elif isinstance(type_value, list) and all(
            isinstance(item, str) for item in type_value
        ):
            types = type_value
        else:
            types = []
        if not types or any(item not in _SCHEMA_TYPES for item in types):
            errors.append(f"{path}.type: unsupported JSON type")
    if "$ref" in schema:
        _, ref_error = _resolve_ref(root, schema["$ref"])
        if ref_error:
            errors.append(f"{path}.$ref: {ref_error}")
    pattern = schema.get("pattern")
    if pattern is not None:
        try:
            re.compile(pattern)
        except (TypeError, re.error) as exc:
            errors.append(f"{path}.pattern: invalid regular expression ({exc})")
    format_value = schema.get("format")
    if format_value is not None and format_value != "date":
        errors.append(f"{path}.format: unsupported format")
    required = schema.get("required")
    if required is not None and (
        not isinstance(required, list)
        or not all(isinstance(item, str) for item in required)
        or len(required) != len(set(required))
    ):
        errors.append(f"{path}.required: must be a unique string array")
    enum = schema.get("enum")
    if enum is not None and not isinstance(enum, list):
        errors.append(f"{path}.enum: must be an array")
    for name in ("minItems", "maxItems", "minLength", "maxLength"):
        value = schema.get(name)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            errors.append(f"{path}.{name}: must be a non-negative integer")
    if "uniqueItems" in schema and not isinstance(schema["uniqueItems"], bool):
        errors.append(f"{path}.uniqueItems: must be boolean")
    for name in ("properties", "$defs"):
        children = schema.get(name, {})
        if not isinstance(children, dict):
            errors.append(f"{path}.{name}: must be an object")
            continue
        for key, child in children.items():
            errors.extend(
                _schema_definition_errors(child, path=f"{path}.{name}.{key}", root=root)
            )
    if "items" in schema:
        if isinstance(schema["items"], dict):
            errors.extend(
                _schema_definition_errors(
                    schema["items"], path=f"{path}.items", root=root
                )
            )
        else:
            errors.append(f"{path}.items: must be a schema object")
    if "additionalProperties" in schema and not isinstance(
        schema["additionalProperties"], bool
    ):
        errors.append(f"{path}.additionalProperties: only booleans are supported")
    return errors


def _resolve_ref(
    root: dict[str, Any], reference: Any
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(reference, str) or not reference.startswith("#/"):
        return None, "only local JSON pointers are supported"
    node: Any = root
    for raw_token in reference[2:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or token not in node:
            return None, f"unresolved reference {reference!r}"
        node = node[token]
    if not isinstance(node, dict):
        return None, f"reference {reference!r} is not a schema object"
    return node, None


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return value is None


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if left is None or right is None:
        return left is right
    return type(left) is type(right) and left == right


def _schema_errors(
    value: Any,
    schema: dict[str, Any],
    *,
    root: dict[str, Any],
    path: str,
) -> list[str]:
    if "$ref" in schema:
        resolved, error = _resolve_ref(root, schema["$ref"])
        if error:
            return [f"{path}: {error}"]
        assert resolved is not None
        return _schema_errors(value, resolved, root=root, path=path)

    errors: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        expected_types = expected if isinstance(expected, list) else [expected]
        if not any(_matches_type(value, item) for item in expected_types):
            return [f"{path}: expected type {' or '.join(expected_types)}"]
    if "const" in schema and not _json_equal(value, schema["const"]):
        errors.append(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and not any(
        _json_equal(value, item) for item in schema["enum"]
    ):
        errors.append(f"{path}: value {value!r} is not in the allowed enum")

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: string is shorter than minLength")
        max_length = schema.get("maxLength")
        if isinstance(max_length, int) and len(value) > max_length:
            errors.append(f"{path}: string is longer than maxLength")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            errors.append(f"{path}: value does not match required pattern")
        if schema.get("format") == "date":
            try:
                date.fromisoformat(value)
            except ValueError:
                errors.append(f"{path}: invalid ISO date")

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: array has fewer than minItems")
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            errors.append(f"{path}: array has more than maxItems")
        if schema.get("uniqueItems"):
            canonical = [
                json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
                for item in value
            ]
            if len(canonical) != len(set(canonical)):
                errors.append(f"{path}: array items must be unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(
                    _schema_errors(
                        item, item_schema, root=root, path=f"{path}[{index}]"
                    )
                )

    if isinstance(value, dict):
        non_string_keys = [key for key in value if not isinstance(key, str)]
        if non_string_keys:
            errors.append(f"{path}: object keys must be strings")
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required property {key!r}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(
                str(key)
                for key in value
                if not isinstance(key, str) or key not in properties
            )
            if unknown:
                errors.append(f"{path}: unknown properties {unknown}")
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(
                    _schema_errors(
                        value[key], child_schema, root=root, path=f"{path}.{key}"
                    )
                )
    return errors


def _schema_document_errors(
    document: Any,
    schema: dict[str, Any],
    *,
    root_schema: dict[str, Any],
    label: str,
) -> list[str]:
    return _schema_errors(
        _json_value(document), schema, root=root_schema, path=f"{label}: $"
    )


def _duplicates(values: list[str]) -> list[str]:
    return sorted(key for key, count in Counter(values).items() if count > 1)


def _parsed_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _runtime_condition_errors(
    rule_id: str,
    modality: str,
    runtime: dict[str, Any],
    known_axes: set[str] | None,
) -> list[str]:
    errors: list[str] = []
    conditions = runtime.get("conditions")
    if not isinstance(conditions, list):
        return errors
    fingerprints: list[str] = []
    for index, condition in enumerate(conditions):
        if not isinstance(condition, dict):
            continue
        fingerprints.append(
            json.dumps(condition, sort_keys=True, ensure_ascii=False, default=str)
        )
        field, op = condition.get("field"), condition.get("op")
        if not isinstance(field, str) or not isinstance(op, str):
            continue
        severity_field = field == "severity" or field.endswith(".status")
        allowed = _SEVERITY_OPS if severity_field else _TEXT_OPS
        if op not in allowed:
            errors.append(
                f"{rule_id}: runtime condition {index} operator {op!r} is invalid "
                f"for field {field!r}"
            )
        expects_values = not severity_field and op != "equals"
        if expects_values:
            if "values" not in condition or "value" in condition:
                errors.append(
                    f"{rule_id}: runtime condition {index} must use only values"
                )
        elif "value" not in condition or "values" in condition:
            errors.append(f"{rule_id}: runtime condition {index} must use only value")
        if severity_field and condition.get("value") not in _SEVERITIES:
            errors.append(
                f"{rule_id}: runtime condition {index} has invalid severity value"
            )
        if field.startswith("checklist."):
            axis = field.removeprefix("checklist.").removesuffix(".status")
            if known_axes is None or axis not in known_axes:
                errors.append(
                    f"{rule_id}: unknown {modality} runtime checklist axis {axis!r}"
                )
    if len(fingerprints) != len(set(fingerprints)):
        errors.append(f"{rule_id}: runtime conditions must be unique")
    return errors


def _safe_source_path(repository_root: Path, source: Any) -> Path | None:
    if not isinstance(source, str) or not source:
        return None
    base = repository_root.resolve()
    candidate = (base / source).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def validate_registry(
    registry: dict[str, Any],
    *,
    today: date | None = None,
    verify_repository_links: bool = True,
) -> list[str]:
    """Validate syntax, governance, clinical chronology, and runtime parity."""
    errors = [str(item) for item in registry.get("load_errors", [])]
    schema = registry.get("schema")
    if not isinstance(schema, dict) or not schema:
        errors.append("clinical rule schema is unavailable")
        return errors
    if schema.get("$id") != CLINICAL_SCHEMA_ID:
        errors.append(
            "clinical rule schema id/version mismatch: "
            f"expected {CLINICAL_SCHEMA_ID!r}"
        )
    if schema.get("additionalProperties") is not False:
        errors.append("clinical rule schema root must reject additional properties")
    properties = schema.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    definitions = schema.get("$defs")
    definitions = definitions if isinstance(definitions, dict) else {}
    axis_document = definitions.get("axisDocument")
    axis_document = axis_document if isinstance(axis_document, dict) else {}
    axis_properties = axis_document.get("properties")
    axis_properties = axis_properties if isinstance(axis_properties, dict) else {}
    inventory_document = definitions.get("inventoryDocument")
    inventory_document = (
        inventory_document if isinstance(inventory_document, dict) else {}
    )
    inventory_properties = inventory_document.get("properties")
    inventory_properties = (
        inventory_properties if isinstance(inventory_properties, dict) else {}
    )
    version_nodes = {
        "rule": properties.get("schema_version"),
        "axis": axis_properties.get("schema_version"),
        "inventory": inventory_properties.get("schema_version"),
    }
    for label, node in version_nodes.items():
        if not isinstance(node, dict) or node.get("const") != CLINICAL_SCHEMA_VERSION:
            errors.append(
                f"clinical {label} schema version must be "
                f"{CLINICAL_SCHEMA_VERSION}"
            )
    required_definitions = {
        "rule",
        "axisDocument",
        "inventoryDocument",
    }
    if not required_definitions.issubset(definitions):
        errors.append(
            "clinical rule schema is incomplete; required definitions are "
            "rule, axisDocument, and inventoryDocument"
        )
    schema_errors = _schema_definition_errors(schema)
    errors.extend(f"schema definition: {error}" for error in schema_errors)
    if not schema_errors:
        for item in registry.get("rule_documents", []):
            errors.extend(
                _schema_document_errors(
                    item.get("document"),
                    schema,
                    root_schema=schema,
                    label=str(item.get("path", "<rule document>")),
                )
            )
        axis_schema = schema.get("$defs", {}).get("axisDocument")
        inventory_schema = schema.get("$defs", {}).get("inventoryDocument")
        if isinstance(axis_schema, dict):
            for item in registry.get("axis_documents", []):
                errors.extend(
                    _schema_document_errors(
                        item.get("document"),
                        axis_schema,
                        root_schema=schema,
                        label=str(item.get("path", "<axis document>")),
                    )
                )
        else:
            errors.append("schema definition lacks $defs.axisDocument")
        inventory_item = registry.get("inventory_document", {})
        if isinstance(inventory_schema, dict):
            errors.extend(
                _schema_document_errors(
                    inventory_item.get("document"),
                    inventory_schema,
                    root_schema=schema,
                    label=str(inventory_item.get("path", "legacy-inventory.yaml")),
                )
            )
        else:
            errors.append("schema definition lacks $defs.inventoryDocument")

    raw_rules = registry.get("rules", [])
    rules = [rule for rule in raw_rules if isinstance(rule, dict)]
    ids = [rule["rule_id"] for rule in rules if isinstance(rule.get("rule_id"), str)]
    duplicate_ids = _duplicates(ids)
    if duplicate_ids:
        errors.append(f"rule ids must be unique: {duplicate_ids}")
    versions = registry.get("versions", set())
    if len(versions) != 1:
        errors.append("all rule files must declare one identical registry_version")
    known_ids = set(ids)
    rules_by_id = {
        rule["rule_id"]: rule for rule in rules if isinstance(rule.get("rule_id"), str)
    }
    axes = registry.get("axes", {})
    axis_modalities = [
        item.get("document", {}).get("modality")
        for item in registry.get("axis_documents", [])
        if isinstance(item.get("document"), dict)
        and isinstance(item.get("document", {}).get("modality"), str)
    ]
    duplicate_modalities = _duplicates(axis_modalities)
    if duplicate_modalities:
        errors.append(
            f"axis modalities must have one canonical document: {duplicate_modalities}"
        )
    check_date = today or date.today()

    for rule in rules:
        rule_id = str(rule.get("rule_id", "<missing>"))
        modality = rule.get("modality")
        version = rule.get("version")
        if isinstance(version, str):
            major_match = re.search(r"\.v([0-9]+)$", rule_id)
            major = version.split(".", 1)[0]
            if major_match is None or major_match.group(1) != major:
                errors.append(
                    f"{rule_id}: rule id .vN suffix must match semantic-version major"
                )
        known_axes = axes.get(modality) if isinstance(axes, dict) else None
        if not isinstance(modality, str) or known_axes is None:
            errors.append(f"{rule_id}: modality has no canonical axis registry")

        human = rule.get("human") if isinstance(rule.get("human"), dict) else {}
        workflow = human.get("workflow") if isinstance(human, dict) else []
        workflow_rows = workflow if isinstance(workflow, list) else []
        workflow_ids = [
            row["id"]
            for row in workflow_rows
            if isinstance(row, dict) and isinstance(row.get("id"), str)
        ]
        duplicates = _duplicates(workflow_ids)
        if duplicates:
            errors.append(f"{rule_id}: human workflow step ids duplicate {duplicates}")
        agent = rule.get("agent") if isinstance(rule.get("agent"), dict) else {}
        steps = agent.get("steps") if isinstance(agent, dict) else []
        agent_rows = steps if isinstance(steps, list) else []
        agent_ids = [
            row["id"]
            for row in agent_rows
            if isinstance(row, dict) and isinstance(row.get("id"), str)
        ]
        duplicates = _duplicates(agent_ids)
        if duplicates:
            errors.append(f"{rule_id}: agent step ids duplicate {duplicates}")
        unknown_steps = sorted(set(agent_ids) - set(workflow_ids))
        if unknown_steps:
            errors.append(
                f"{rule_id}: agent steps do not map to human workflow {unknown_steps}"
            )
        workflow_positions = {
            step_id: index for index, step_id in enumerate(workflow_ids)
        }
        mapped_positions = [
            workflow_positions[step_id]
            for step_id in agent_ids
            if step_id in workflow_positions
        ]
        if mapped_positions != sorted(mapped_positions):
            errors.append(f"{rule_id}: agent steps reorder the human workflow")
        for index, row in enumerate(agent_rows):
            if not isinstance(row, dict) or not isinstance(row.get("instruction"), str):
                continue
            if any(
                pattern.search(row["instruction"]) for pattern in _AGENT_BOILERPLATE
            ):
                errors.append(
                    f"{rule_id}: agent step {index} contains generic refusal/disclaimer "
                    "boilerplate"
                )

        reviewed_on = _parsed_date(human.get("reviewed_on"))
        review_due = _parsed_date(human.get("review_due"))
        if reviewed_on is not None and reviewed_on > check_date:
            errors.append(f"{rule_id}: reviewed_on cannot be in the future")
        if reviewed_on is not None and review_due is not None:
            if review_due <= reviewed_on:
                errors.append(f"{rule_id}: review_due must be after reviewed_on")
            if rule.get("status") == "active" and review_due < check_date:
                errors.append(f"{rule_id}: active clinical review is expired")
        sources = human.get("sources") if isinstance(human, dict) else []
        for index, source in enumerate(sources if isinstance(sources, list) else []):
            if not isinstance(source, dict):
                continue
            effective = _parsed_date(source.get("effective_date"))
            if (
                effective is not None
                and reviewed_on is not None
                and effective > reviewed_on
            ):
                errors.append(
                    f"{rule_id}: source {index} effective_date is after reviewed_on"
                )

        output = rule.get("output") if isinstance(rule.get("output"), dict) else {}
        output_axes = output.get("axes") if isinstance(output, dict) else []
        if isinstance(output_axes, list) and known_axes is not None:
            unknown_axes = sorted(
                axis
                for axis in output_axes
                if isinstance(axis, str) and axis not in known_axes
            )
            if unknown_axes:
                errors.append(
                    f"{rule_id}: unknown {modality} output axes {unknown_axes}"
                )
        priority = (
            rule.get("priority") if isinstance(rule.get("priority"), dict) else {}
        )
        severity_floor = output.get("severity_floor_if_confirmed")
        priority_tier = priority.get("tier")
        priority_basis = priority.get("basis")
        if severity_floor is None:
            if (
                priority_tier != "review"
                or priority_basis != "clinical_consistency_review"
            ):
                errors.append(
                    f"{rule_id}: review-only output requires review tier and "
                    "clinical_consistency_review basis"
                )
        elif severity_floor in _SEVERITIES and (
            priority_tier != severity_floor or priority_basis != "product_safety_policy"
        ):
            errors.append(
                f"{rule_id}: severity floor requires matching product-safety tier"
            )
        conflicts = priority.get("conflicts_with") if isinstance(priority, dict) else []
        if isinstance(conflicts, list):
            unknown = sorted(
                item
                for item in conflicts
                if isinstance(item, str) and item not in known_ids
            )
            if unknown:
                errors.append(f"{rule_id}: unknown conflicts {unknown}")
            if rule_id in conflicts:
                errors.append(f"{rule_id}: rule cannot conflict with itself")

        runtime = rule.get("runtime")
        if isinstance(runtime, dict):
            errors.extend(
                _runtime_condition_errors(rule_id, str(modality), runtime, known_axes)
            )
            if runtime.get("escalate_to") != output.get("severity_floor_if_confirmed"):
                errors.append(
                    f"{rule_id}: runtime escalation and output severity floor differ"
                )
        tests = rule.get("tests") if isinstance(rule.get("tests"), dict) else {}
        aliases: list[str] = []
        for kind in TEST_KINDS:
            values = tests.get(kind) if isinstance(tests, dict) else None
            if isinstance(values, list):
                aliases.extend(item for item in values if isinstance(item, str))
        duplicate_aliases = _duplicates(aliases)
        if duplicate_aliases:
            errors.append(
                f"{rule_id}: test aliases must be unique across categories "
                f"{duplicate_aliases}"
            )

    inventory = registry.get("inventory", {})
    entries = inventory.get("entries") if isinstance(inventory, dict) else []
    inventory_rows = entries if isinstance(entries, list) else []
    legacy_ids = [
        row["legacy_id"]
        for row in inventory_rows
        if isinstance(row, dict) and isinstance(row.get("legacy_id"), str)
    ]
    duplicates = _duplicates(legacy_ids)
    if duplicates:
        errors.append(f"legacy ids must be unique: {duplicates}")
    mapped_canonical = [
        row["canonical_rule"]
        for row in inventory_rows
        if isinstance(row, dict)
        and row.get("status") == "mapped"
        and isinstance(row.get("canonical_rule"), str)
    ]
    duplicates = _duplicates(mapped_canonical)
    if duplicates:
        errors.append(f"canonical rules mapped more than once: {duplicates}")
    repository_root = registry.get("repository_root", ROOT)
    if not isinstance(repository_root, Path):
        repository_root = Path(repository_root)
    inventory_by_legacy = {
        row["legacy_id"]: row
        for row in inventory_rows
        if isinstance(row, dict) and isinstance(row.get("legacy_id"), str)
    }
    for row in inventory_rows:
        if not isinstance(row, dict):
            continue
        legacy_id = str(row.get("legacy_id", "<missing>"))
        status = row.get("status")
        canonical_id = row.get("canonical_rule")
        if status == "mapped" and not isinstance(canonical_id, str):
            errors.append(f"{legacy_id}: mapped entry requires canonical_rule")
        if status != "mapped" and canonical_id is not None:
            errors.append(
                f"{legacy_id}: only mapped entries may declare canonical_rule"
            )
        if status == "intentional_local" and not row.get("note"):
            errors.append(f"{legacy_id}: intentional_local entry requires note")
        source_path = _safe_source_path(repository_root, row.get("source"))
        source_text = ""
        if source_path is None:
            errors.append(f"{legacy_id}: legacy source must stay inside repository")
        elif verify_repository_links:
            if not source_path.is_file():
                errors.append(f"{legacy_id}: legacy source is missing")
            else:
                try:
                    source_text = source_path.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as exc:
                    errors.append(
                        f"{legacy_id}: cannot read legacy source: {type(exc).__name__}"
                    )
        locator = row.get("locator")
        if isinstance(locator, str) and source_text and locator not in source_text:
            errors.append(f"{legacy_id}: locator is absent from legacy source")
        parity_test = row.get("parity_test")
        if isinstance(parity_test, str) and "::" in parity_test:
            parity_source, *test_nodes = parity_test.split("::")
            parity_path = _safe_source_path(repository_root, parity_source)
            if (
                parity_path is None
                or parity_path.suffix != ".py"
                or "tests" not in parity_path.parts
            ):
                errors.append(
                    f"{legacy_id}: parity_test must target a repository test module"
                )
            elif verify_repository_links and not parity_path.is_file():
                errors.append(f"{legacy_id}: parity test source is missing")
            elif verify_repository_links:
                try:
                    parity_text = parity_path.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as exc:
                    errors.append(
                        f"{legacy_id}: cannot read parity test: {type(exc).__name__}"
                    )
                else:
                    missing_nodes = []
                    for test_node in test_nodes:
                        declaration = re.compile(
                            rf"^\s*(?:(?:async\s+)?def|class)\s+"
                            rf"{re.escape(test_node)}\s*(?:\(|:)",
                            re.MULTILINE,
                        )
                        if declaration.search(parity_text) is None:
                            missing_nodes.append(test_node)
                    if missing_nodes:
                        errors.append(
                            f"{legacy_id}: parity test node is not declared "
                            f"{missing_nodes}"
                        )
        if status != "mapped":
            continue
        canonical = rules_by_id.get(canonical_id)
        if canonical is None:
            errors.append(f"{legacy_id}: mapped canonical rule is missing")
            continue
        if canonical.get("status") != "active":
            errors.append(f"{legacy_id}: mapped canonical rule must be active")
        legacy = canonical.get("legacy")
        if not isinstance(legacy, dict):
            errors.append(f"{legacy_id}: canonical legacy linkage is missing")
        else:
            if legacy.get("runtime_id") != legacy_id:
                errors.append(f"{legacy_id}: canonical runtime_id parity failed")
            if legacy.get("source") != row.get("source"):
                errors.append(f"{legacy_id}: canonical source parity failed")
        runtime = canonical.get("runtime")
        if not isinstance(runtime, dict):
            errors.append(
                f"{legacy_id}: mapped rule lacks auditable runtime parity data"
            )

    for rule in rules:
        legacy = rule.get("legacy")
        if not isinstance(legacy, dict) or not isinstance(
            legacy.get("runtime_id"), str
        ):
            continue
        runtime_id = legacy["runtime_id"]
        row = inventory_by_legacy.get(runtime_id)
        if (
            row is None
            or row.get("status") != "mapped"
            or row.get("canonical_rule") != rule.get("rule_id")
        ):
            errors.append(
                f"{rule.get('rule_id', '<missing>')}: canonical legacy rule is not "
                "a parity-verified mapped inventory entry"
            )
    return errors


def registry_digest(registry: dict[str, Any]) -> str:
    """Hash every canonical input document, including its relative path.

    Scope ``canonical-input-documents-v1`` covers parsed rule YAML, axis YAML,
    ``legacy-inventory.yaml``, and ``schema/rule.schema.json``. Generated
    Markdown, generated Python, and SQLite are projections and are deliberately
    excluded so they can carry this digest without making it self-referential.
    """

    payload = {
        "scope": REGISTRY_DIGEST_SCOPE,
        "rule_documents": sorted(
            registry["rule_documents"], key=lambda item: item["path"]
        ),
        "axis_documents": sorted(
            registry["axis_documents"], key=lambda item: item["path"]
        ),
        "inventory_document": registry["inventory_document"],
        "schema": registry["schema"],
    }
    canonical = json.dumps(
        _json_value(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _markdown_text(value: object) -> str:
    """Collapse YAML folding whitespace for stable, readable generated Markdown."""

    return " ".join(str(value).split())


def render_views(registry: dict[str, Any]) -> tuple[str, str]:
    digest = registry_digest(registry)
    scope_line = f"Registry digest scope: `{REGISTRY_DIGEST_SCOPE}`"
    human = [
        "# Clinical knowledge catalogue",
        "",
        f"Registry SHA-256: `{digest}`",
        scope_line,
        "",
    ]
    agent = [
        "# Agent clinical steps",
        "",
        f"Registry SHA-256: `{digest}`",
        scope_line,
        "",
        "This generated view contains no evaluation gold labels or scorer aliases.",
        "",
    ]
    for rule in sorted(registry["rules"], key=lambda row: row["rule_id"]):
        human.extend(
            [
                f"## {_markdown_text(rule['human']['title'])}",
                "",
                f"Rule: `{rule['rule_id']}` v{rule['version']} ({rule['modality']})",
                "",
                _markdown_text(rule["human"]["rationale"]),
                "",
                "### Differential workflow",
                "",
            ]
        )
        human.extend(
            f"1. **{row['id']}** — {_markdown_text(row['detail'])}"
            for row in rule["human"]["workflow"]
        )
        human.extend(["", "### Sources", ""])
        human.extend(
            f"- {_markdown_text(source['authority'])}: "
            f"{_markdown_text(source['title'])} ({source['version']}), "
            f"{_markdown_text(source['locator'])} — {source['url']}"
            for source in rule["human"]["sources"]
        )
        human.append("")
        agent.extend([f"## `{rule['rule_id']}`", ""])
        agent.extend(
            f"- [{row['id']}] {_markdown_text(row['instruction'])}"
            for row in rule["agent"]["steps"]
        )
        agent.append("")
    return "\n".join(human).rstrip() + "\n", "\n".join(agent).rstrip() + "\n"


def runtime_rule_specs(registry: dict[str, Any]) -> tuple[dict[str, object], ...]:
    """Compile canonical YAML into the pure-data domain runtime representation."""

    specs: list[dict[str, object]] = []
    for rule in sorted(registry["rules"], key=lambda row: row["rule_id"]):
        if rule["status"] != "active":
            continue
        sources = rule["human"]["sources"]
        primary_source = sources[0]
        runtime = rule["runtime"]
        specs.append(
            {
                "canonical_rule_id": rule["rule_id"],
                "id": rule["legacy"]["runtime_id"],
                "modality": rule["modality"],
                "description": _markdown_text(rule["human"]["rationale"]),
                "conditions": runtime["conditions"],
                "message": runtime["message"],
                "guideline": (
                    f"{primary_source['authority']}: {primary_source['title']}"
                ),
                "guideline_version": str(primary_source["version"]),
                "effective_date": str(primary_source["effective_date"]),
                "source_url": primary_source["url"],
                "escalate_to": runtime["escalate_to"],
                "require_review": runtime["require_review"],
            }
        )
    return tuple(specs)


def render_runtime_view(registry: dict[str, Any]) -> str:
    digest = registry_digest(registry)
    specs = pprint.pformat(runtime_rule_specs(registry), width=88, sort_dicts=False)
    return (
        '"""Generated from clinical_knowledge YAML; do not edit by hand."""\n\n'
        "from __future__ import annotations\n\n"
        f'REGISTRY_SHA256 = "{digest}"\n\n'
        f'REGISTRY_DIGEST_SCOPE = "{REGISTRY_DIGEST_SCOPE}"\n\n'
        "BUILTIN_RULE_SPECS: tuple[dict[str, object], ...] = "
        f"{specs}\n"
    )


def write_or_check_views(registry: dict[str, Any], *, check: bool) -> list[str]:
    expected = dict(zip((HUMAN_VIEW, AGENT_VIEW), render_views(registry), strict=True))
    expected[RUNTIME_VIEW] = render_runtime_view(registry)
    errors: list[str] = []
    for path, content in expected.items():
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                errors.append(f"generated view is stale: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-generated", action="store_true")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    registry = load_registry()
    errors = validate_registry(registry)
    if not errors and args.render:
        errors.extend(write_or_check_views(registry, check=False))
    if not errors and args.check_generated:
        errors.extend(write_or_check_views(registry, check=True))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(
        f"Clinical knowledge OK: {len(registry['rules'])} rules, "
        f"{registry_digest(registry)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
