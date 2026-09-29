"""Portable public plugin configuration; do not load a previous App copy."""

import json

import pytest

from dicom_overlay.infrastructure.gateway_manager import (
    GatewayManager,
    _managed_harness_load_paths,
)

SUFFIX = "openclaw-home/.openclaw/workspace/plugins/dicom-overlay-agent-harness"


@pytest.mark.parametrize(
    "old",
    [
        "C:/old/" + SUFFIX,
        "C:\\old\\" + SUFFIX.replace("/", "\\") + "\\",
        "C:/OLD/" + SUFFIX.upper() + "/index.js",
        "//server/share/old/" + SUFFIX,
        "/opt/old/" + SUFFIX,
        "C:/old/moved/../" + SUFFIX,
    ],
)
def test_relocation_removes_old_managed_load_entry_only(tmp_path, old):
    current = (tmp_path / SUFFIX).resolve()
    unrelated = ["C:/custom/plugin", "C:/custom/dicom-overlay-agent-harness"]
    original = [old, *unrelated, str(current), old]
    assert _managed_harness_load_paths(original, current) == [*unrelated, str(current)]
    assert original == [old, *unrelated, str(current), old]


@pytest.mark.parametrize(
    "unrelated",
    [
        SUFFIX,
        "C:/custom/dicom-overlay-agent-harness/index.js",
        "C:/old/" + SUFFIX + "-custom",
        "C:/old/" + SUFFIX + "/custom.js",
        "C:/old/" + SUFFIX + "/../different-plugin",
        "https://example.test/" + SUFFIX,
        None,
        1,
    ],
)
def test_relocation_does_not_remove_unowned_entries(tmp_path, unrelated):
    current = (tmp_path / SUFFIX).resolve()
    assert _managed_harness_load_paths([unrelated], current) == [
        unrelated,
        str(current),
    ]


def test_real_public_config_rebinding_is_idempotent_and_preserves_other_plugins(
    tmp_path,
):
    old = tmp_path / "old" / SUFFIX
    old.mkdir(parents=True)
    sentinel = old / "index.js"
    sentinel.write_text("// old file must not be deleted", encoding="utf-8")
    new_root = tmp_path / "new"
    config = new_root / "openclaw/openclaw.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "plugins": {
                    "load": {"paths": [str(old), "C:/custom/independent"]},
                    "entries": {
                        "independent": {"enabled": True, "config": {"mode": "user"}}
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    manager = GatewayManager(repo_root=new_root)
    manager._ensure_openclaw_config()
    first = config.read_bytes()
    manager._ensure_openclaw_config()
    assert config.read_bytes() == first
    payload = json.loads(first)
    assert payload["plugins"]["load"]["paths"] == [
        "C:/custom/independent",
        str((new_root / SUFFIX).resolve()),
    ]
    assert payload["plugins"]["entries"]["independent"] == {
        "enabled": True,
        "config": {"mode": "user"},
    }
    assert sentinel.read_text("utf-8") == "// old file must not be deleted"
