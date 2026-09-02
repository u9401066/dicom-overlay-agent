"""Build and verify the application-owned clinical quick-lookup SQLite file."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "build" / "clinical-knowledge.sqlite"
DB_SCHEMA_VERSION = "1"
CANONICAL_SOURCE = "clinical_knowledge canonical YAML/JSON inputs"

_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "rules": (
        "rule_id",
        "version",
        "modality",
        "status",
        "title",
        "rationale",
        "priority_tier",
        "priority_basis",
        "severity_floor",
        "reviewed_on",
        "review_due",
    ),
    "human_steps": ("rule_id", "ordinal", "step_id", "detail"),
    "agent_steps": ("rule_id", "ordinal", "step_id", "instruction"),
    "sources": (
        "rule_id",
        "ordinal",
        "authority",
        "title",
        "version",
        "effective_date",
        "url",
        "locator",
    ),
    "runtime_conditions": (
        "rule_id",
        "ordinal",
        "field",
        "operator",
        "values_json",
        "scalar_value",
    ),
    "lookup_terms": ("term_norm", "rule_id", "term", "term_kind"),
    "legacy_map": (
        "legacy_id",
        "canonical_rule",
        "layer",
        "status",
        "source",
        "locator",
        "parity_test",
    ),
    "axes": ("modality", "axis"),
}


def _load_validator() -> ModuleType:
    path = ROOT / "scripts" / "validate-clinical-knowledge.py"
    spec = importlib.util.spec_from_file_location("clinical_registry_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load clinical validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text(value: object) -> str:
    """Collapse YAML folding whitespace before materializing lookup text."""

    return " ".join(str(value).split())


def expected_rows(registry: dict[str, Any]) -> dict[str, list[tuple[object, ...]]]:
    """Return the canonical relational projection of one validated registry."""

    rows = {table: [] for table in _TABLE_COLUMNS}
    for rule in sorted(registry["rules"], key=lambda item: item["rule_id"]):
        rule_id = str(rule["rule_id"])
        human = rule["human"]
        priority = rule["priority"]
        output = rule["output"]
        runtime = rule.get("runtime") or {}
        rows["rules"].append(
            (
                rule_id,
                str(rule["version"]),
                str(rule["modality"]),
                str(rule["status"]),
                _text(human["title"]),
                _text(human["rationale"]),
                str(priority["tier"]),
                str(priority["basis"]),
                "" if output.get("severity_floor_if_confirmed") is None else str(output["severity_floor_if_confirmed"]),
                str(human["reviewed_on"]),
                str(human["review_due"]),
            )
        )
        for ordinal, step in enumerate(human["workflow"]):
            rows["human_steps"].append(
                (rule_id, ordinal, str(step["id"]), _text(step["detail"]))
            )
        for ordinal, step in enumerate(rule["agent"]["steps"]):
            rows["agent_steps"].append(
                (rule_id, ordinal, str(step["id"]), _text(step["instruction"]))
            )
        for ordinal, source in enumerate(human["sources"]):
            rows["sources"].append(
                (
                    rule_id,
                    ordinal,
                    _text(source["authority"]),
                    _text(source["title"]),
                    str(source["version"]),
                    str(source["effective_date"]),
                    str(source["url"]),
                    _text(source["locator"]),
                )
            )
        for ordinal, condition in enumerate(runtime.get("conditions") or []):
            values = [str(value) for value in condition.get("values") or []]
            scalar = condition.get("value")
            rows["runtime_conditions"].append(
                (
                    rule_id,
                    ordinal,
                    str(condition["field"]),
                    str(condition["op"]),
                    _json(values),
                    "" if scalar is None else str(scalar),
                )
            )
            for value in values:
                rows["lookup_terms"].append(
                    (value.casefold(), rule_id, value, "runtime_condition")
                )
        rows["lookup_terms"].extend(
            (
                text.casefold(),
                rule_id,
                text,
                kind,
            )
            for text, kind in (
                (_text(human["title"]), "title"),
                (_text(runtime.get("message") or ""), "runtime_message"),
            )
            if text
        )
    for row in sorted(
        registry["inventory"].get("entries") or [],
        key=lambda item: str(item["legacy_id"]),
    ):
        rows["legacy_map"].append(
            (
                str(row["legacy_id"]),
                str(row.get("canonical_rule") or ""),
                str(row["layer"]),
                str(row["status"]),
                str(row["source"]),
                str(row["locator"]),
                str(row["parity_test"]),
            )
        )
    rows["axes"] = sorted(
        (str(modality), str(axis))
        for modality, axes in registry["axes"].items()
        for axis in axes
    )
    for table in rows:
        rows[table] = sorted(set(rows[table]))
    return rows


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode=DELETE;
        PRAGMA synchronous=FULL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) STRICT;
        CREATE TABLE rules (
            rule_id TEXT PRIMARY KEY,
            version TEXT NOT NULL,
            modality TEXT NOT NULL,
            status TEXT NOT NULL,
            title TEXT NOT NULL,
            rationale TEXT NOT NULL,
            priority_tier TEXT NOT NULL,
            priority_basis TEXT NOT NULL,
            severity_floor TEXT NOT NULL,
            reviewed_on TEXT NOT NULL,
            review_due TEXT NOT NULL
        ) STRICT;
        CREATE TABLE human_steps (
            rule_id TEXT NOT NULL REFERENCES rules(rule_id),
            ordinal INTEGER NOT NULL,
            step_id TEXT NOT NULL,
            detail TEXT NOT NULL,
            PRIMARY KEY (rule_id, ordinal),
            UNIQUE (rule_id, step_id)
        ) STRICT;
        CREATE TABLE agent_steps (
            rule_id TEXT NOT NULL REFERENCES rules(rule_id),
            ordinal INTEGER NOT NULL,
            step_id TEXT NOT NULL,
            instruction TEXT NOT NULL,
            PRIMARY KEY (rule_id, ordinal),
            FOREIGN KEY (rule_id, step_id)
                REFERENCES human_steps(rule_id, step_id)
        ) STRICT;
        CREATE TABLE sources (
            rule_id TEXT NOT NULL REFERENCES rules(rule_id),
            ordinal INTEGER NOT NULL,
            authority TEXT NOT NULL,
            title TEXT NOT NULL,
            version TEXT NOT NULL,
            effective_date TEXT NOT NULL,
            url TEXT NOT NULL,
            locator TEXT NOT NULL,
            PRIMARY KEY (rule_id, ordinal)
        ) STRICT;
        CREATE TABLE runtime_conditions (
            rule_id TEXT NOT NULL REFERENCES rules(rule_id),
            ordinal INTEGER NOT NULL,
            field TEXT NOT NULL,
            operator TEXT NOT NULL,
            values_json TEXT NOT NULL,
            scalar_value TEXT NOT NULL,
            PRIMARY KEY (rule_id, ordinal)
        ) STRICT;
        CREATE TABLE lookup_terms (
            term_norm TEXT NOT NULL,
            rule_id TEXT NOT NULL REFERENCES rules(rule_id),
            term TEXT NOT NULL,
            term_kind TEXT NOT NULL,
            PRIMARY KEY (term_norm, rule_id, term_kind)
        ) STRICT;
        CREATE INDEX idx_lookup_terms_rule ON lookup_terms(rule_id);
        CREATE TABLE legacy_map (
            legacy_id TEXT PRIMARY KEY,
            canonical_rule TEXT NOT NULL,
            layer TEXT NOT NULL,
            status TEXT NOT NULL,
            source TEXT NOT NULL,
            locator TEXT NOT NULL,
            parity_test TEXT NOT NULL
        ) STRICT;
        CREATE TABLE axes (
            modality TEXT NOT NULL,
            axis TEXT NOT NULL,
            PRIMARY KEY (modality, axis)
        ) STRICT;
        """
    )


def build_quick_lookup_db(
    registry: dict[str, Any], output: Path, *, registry_digest: str
) -> None:
    """Atomically build the SQLite projection from validated canonical YAML."""

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=output.parent, prefix=f".{output.name}.", suffix=".tmp", delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        connection = sqlite3.connect(temporary)
        try:
            _create_schema(connection)
            rows = expected_rows(registry)
            metadata = {
                "canonical_source": CANONICAL_SOURCE,
                "db_schema_version": DB_SCHEMA_VERSION,
                "registry_digest_scope": str(registry["registry_digest_scope"]),
                "registry_sha256": registry_digest,
                "rule_count": str(len(rows["rules"])),
            }
            connection.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                sorted(metadata.items()),
            )
            for table, table_rows in rows.items():
                columns = _TABLE_COLUMNS[table]
                placeholders = ",".join("?" for _ in columns)
                connection.executemany(
                    f"INSERT INTO {table} ({','.join(columns)}) "
                    f"VALUES ({placeholders})",
                    table_rows,
                )
            connection.commit()
            connection.execute("PRAGMA optimize")
        finally:
            connection.close()
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def verify_quick_lookup_db(
    registry: dict[str, Any], path: Path, *, registry_digest: str
) -> list[str]:
    """Fail closed when the quick-lookup database diverges from canonical YAML."""

    if not path.is_file():
        return [f"quick-lookup database is missing: {path}"]
    errors: list[str] = []
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        expected = expected_rows(registry)
        validator = _load_validator()
        expected_metadata = {
            "canonical_source": CANONICAL_SOURCE,
            "db_schema_version": DB_SCHEMA_VERSION,
            "registry_digest_scope": validator.REGISTRY_DIGEST_SCOPE,
            "registry_sha256": registry_digest,
            "rule_count": str(len(expected["rules"])),
        }
        if metadata != expected_metadata:
            errors.append("quick-lookup metadata diverged from canonical registry")
        quick_check = connection.execute("PRAGMA quick_check").fetchone()
        if quick_check != ("ok",):
            errors.append("quick-lookup database quick_check failed")
        foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_rows:
            errors.append("quick-lookup database foreign-key check failed")
        actual_tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        expected_tables = {"metadata", *_TABLE_COLUMNS}
        if actual_tables != expected_tables:
            errors.append("quick-lookup database table set mismatch")
        metadata_columns = tuple(
            str(row[1]) for row in connection.execute("PRAGMA table_info(metadata)")
        )
        if metadata_columns != ("key", "value"):
            errors.append("quick-lookup table schema diverged: metadata")
        for table, columns in _TABLE_COLUMNS.items():
            actual_columns = tuple(
                str(row[1])
                for row in connection.execute(f"PRAGMA table_info({table})")
            )
            if actual_columns != columns:
                errors.append(f"quick-lookup table schema diverged: {table}")
                continue
            actual = connection.execute(
                f"SELECT {','.join(columns)} FROM {table} ORDER BY "
                + ",".join(columns)
            ).fetchall()
            if actual != expected[table]:
                errors.append(f"quick-lookup table diverged: {table}")
    except sqlite3.Error as exc:
        errors.append(f"quick-lookup database is unreadable: {exc}")
    finally:
        if "connection" in locals():
            connection.close()
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    validator = _load_validator()
    registry = validator.load_registry()
    errors = validator.validate_registry(registry)
    digest = validator.registry_digest(registry)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    if not args.check:
        build_quick_lookup_db(registry, args.output, registry_digest=digest)
    errors = verify_quick_lookup_db(registry, args.output, registry_digest=digest)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"Clinical quick lookup OK: {args.output} ({digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
