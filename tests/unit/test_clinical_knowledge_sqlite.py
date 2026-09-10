from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path


def _module():
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "build-clinical-knowledge-sqlite.py"
    )
    spec = importlib.util.spec_from_file_location("clinical_knowledge_sqlite", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _registry(module):
    validator = module._load_validator()
    registry = validator.load_registry()
    assert validator.validate_registry(registry) == []
    return validator, registry


def test_quick_lookup_is_deterministic_and_matches_yaml(tmp_path: Path) -> None:
    module = _module()
    validator, registry = _registry(module)
    digest = validator.registry_digest(registry)
    first = tmp_path / "first.sqlite"
    second = tmp_path / "second.sqlite"

    module.build_quick_lookup_db(registry, first, registry_digest=digest)
    module.build_quick_lookup_db(registry, second, registry_digest=digest)

    assert first.read_bytes() == second.read_bytes()
    assert module.verify_quick_lookup_db(
        registry, first, registry_digest=digest
    ) == []
    with sqlite3.connect(first) as connection:
        assert connection.execute("SELECT count(*) FROM rules").fetchone() == (7,)
        assert connection.execute("SELECT count(*) FROM legacy_map").fetchone() == (
            10,
        )
        assert connection.execute(
            "SELECT count(*) FROM agent_steps"
        ).fetchone()[0] >= 28
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        assert metadata["registry_digest_scope"] == module._load_validator().REGISTRY_DIGEST_SCOPE


def test_quick_lookup_tamper_fails_closed(tmp_path: Path) -> None:
    module = _module()
    validator, registry = _registry(module)
    digest = validator.registry_digest(registry)
    database = tmp_path / "tampered.sqlite"
    module.build_quick_lookup_db(registry, database, registry_digest=digest)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE rules SET priority_tier='normal' "
            "WHERE rule_id='cxr.pneumothorax_undercall.v1'"
        )

    errors = module.verify_quick_lookup_db(
        registry, database, registry_digest=digest
    )

    assert "quick-lookup table diverged: rules" in errors


def test_quick_lookup_rejects_schema_version_and_metadata_spoofing(
    tmp_path: Path,
) -> None:
    module = _module()
    validator, registry = _registry(module)
    digest = validator.registry_digest(registry)
    database = tmp_path / "metadata-tampered.sqlite"
    module.build_quick_lookup_db(registry, database, registry_digest=digest)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE metadata SET value='2' WHERE key='db_schema_version'"
        )
        connection.execute(
            "UPDATE metadata SET value=? WHERE key='registry_sha256'",
            ("f" * 64,),
        )

    errors = module.verify_quick_lookup_db(
        registry,
        database,
        registry_digest=digest,
    )

    assert "quick-lookup metadata diverged from canonical registry" in errors


def test_quick_lookup_contains_no_eval_gold_or_openclaw_private_coupling(
    tmp_path: Path,
) -> None:
    module = _module()
    validator, registry = _registry(module)
    database = tmp_path / "clinical.sqlite"
    module.build_quick_lookup_db(
        registry,
        database,
        registry_digest=validator.registry_digest(registry),
    )
    raw = database.read_bytes().lower()
    source = Path(module.__file__).read_text(encoding="utf-8").casefold()

    assert b"cant_miss" not in raw
    assert b"expected_severity" not in raw
    assert b"ground_truth" not in raw
    assert "openclaw-home" not in source
    assert "main.sqlite" not in source
