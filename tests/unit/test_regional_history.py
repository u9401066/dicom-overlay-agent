from __future__ import annotations

import base64
import copy
import json
from dataclasses import replace

import pytest

from dicom_overlay.application.regional_conversation import RegionalConversations
from dicom_overlay.application.regional_history import (
    MAX_HISTORY_BYTES,
    decode_regional_history,
)
from dicom_overlay.application.review_chat import parse_region_review_response
from dicom_overlay.infrastructure.regional_history_io import load_regional_history
from medical_image_harness.models import RegionRect


@pytest.fixture
def store():
    result = RegionalConversations()
    result.bind(base64.b64encode(b"synthetic original ROI").decode())
    result.append(
        result.thread(RegionRect(0.1, 0.2, 0.3, 0.4), "f1"),
        question="<script>untrusted historical question</script>",
        answer="Historical answer, not verified evidence",
        proposal="Never apply this old suggestion",
        review_turn_id="a" * 32,
    )
    return result


def decode(payload, digest):
    return decode_regional_history(
        json.dumps(payload).encode(), source_image_sha256=digest
    )


def test_import_is_separate_from_live_finding_and_manual_at_identical_box(store):
    payload = store.export()
    history = decode(payload, store.image_sha256)[0]
    live = store.thread(history.region, "f1")
    manual = store.thread(history.region)
    restored = store.restore_archive(history)
    assert restored is not live and restored is not manual
    assert restored.finding_id == ""
    assert restored.turns == []
    assert restored.history.turns[0].review_turn_id == "a" * 32
    assert "unverified past-run context" in restored.transcript()
    assert "Never apply this old suggestion" not in restored.context()
    assert "Historical answer" in restored.context()
    assert store.export()["threads"] == payload["threads"]


def test_repeated_import_does_not_overwrite_new_turns_and_export_roundtrips(store):
    history = decode(store.export(), store.image_sha256)[0]
    restored = store.restore_archive(history)
    store.append(
        restored, question="New question", answer="New answer", review_turn_id="b" * 32
    )
    assert store.restore_archive(history) is restored
    payload = store.export()
    assert payload["schema_version"] == 3
    archived = payload["archived_threads"][0]
    assert archived["history"]["turns"][0]["review_turn_id"] == "a" * 32
    assert [turn["review_turn_id"] for turn in archived["turns"]] == ["b" * 32]
    histories = decode(payload, store.image_sha256)
    assert len(histories) == 2
    assert [turn.question for turn in histories[1].turns][-1] == "New question"
    # Re-exported past-run live turns become explicitly historical next run.
    second = RegionalConversations()
    second.bind(base64.b64encode(b"synthetic original ROI").decode())
    reopened = second.restore_archive(histories[1])
    assert reopened.turns == []
    assert len(reopened.history.turns) == 2


@pytest.mark.parametrize("same_pixels", [False, True])
def test_invalidated_archive_cannot_append_or_resurrect(store, same_pixels):
    history = decode(store.export(), store.image_sha256)[0]
    restored = store.restore_archive(history)
    store.clear()
    store.bind(
        base64.b64encode(
            b"synthetic original ROI" if same_pixels else b"new image"
        ).decode()
    )
    assert store.archived_thread(history.archive_id) is None
    assert not store.append(restored, question="Late reply", answer="Do not retain")
    assert not store.archived_threads
    if not same_pixels:
        with pytest.raises(ValueError, match="different original image"):
            store.restore_archive(history)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 1),
        ("schema_version", True),
        ("schema_version", 2.0),
        ("source_image_sha256", "b" * 64),
        ("source_image_sha256", None),
        ("coordinate_space", "full_screen"),
        ("content_role", "verified_findings"),
        ("threads", {}),
        ("threads", [None]),
    ],
)
def test_invalid_envelope_rejected_atomically(store, field, value):
    before = store.export()
    payload = copy.deepcopy(before)
    payload[field] = value
    with pytest.raises(ValueError):
        decode(payload, store.image_sha256)
    assert store.export() == before


@pytest.mark.parametrize(
    "value", [None, True, "0.1", -1, 2, float("nan"), float("inf"), 10**400]
)
def test_invalid_coordinates_rejected(store, value):
    payload = store.export()
    payload["threads"][0]["region"]["x"] = value
    with pytest.raises(ValueError):
        decode(payload, store.image_sha256)


@pytest.mark.parametrize(
    "field,value",
    [
        ("question", 123),
        ("answer", "x" * 64_001),
        ("proposal", "x" * 16_001),
        ("created_at", "2026-09-29"),
        ("created_at", "not a timestamp"),
        ("review_turn_id", ""),
        ("review_turn_id", "A" * 32),
        ("question", "nul\x00byte"),
    ],
    ids=[
        "type",
        "answer-limit",
        "proposal-limit",
        "no-zone",
        "invalid-date",
        "empty-id",
        "uppercase-id",
        "nul",
    ],
)
def test_invalid_turn_rejected(store, field, value):
    payload = store.export()
    payload["threads"][0]["turns"][0][field] = value
    with pytest.raises(ValueError):
        decode(payload, store.image_sha256)


def test_reject_empty_turns_unknown_fields_and_duplicate_turn_ids(store):
    for transform in (
        lambda p: p.update(source_path="some/arbitrary/file"),
        lambda p: p["threads"][0].update(turns=[]),
        lambda p: p["threads"][0]["turns"].append(p["threads"][0]["turns"][0]),
        lambda p: p["threads"][0]["region"].update(w=0),
        lambda p: p["threads"][0]["region"].update(w=1),
    ):
        payload = store.export()
        transform(payload)
        with pytest.raises(ValueError):
            decode(payload, store.image_sha256)


@pytest.mark.parametrize(
    "raw",
    [b"\xff", b"[]", b"null", b"{}{}", b'{"a":1,"a":2}', b"[" * 2000 + b"]" * 2000],
)
def test_malformed_or_ambiguous_json_rejected(store, raw):
    with pytest.raises(ValueError):
        decode_regional_history(raw, source_image_sha256=store.image_sha256)


def test_bounded_file_read_and_no_path_following_in_json(store, tmp_path):
    path = tmp_path / "history.json"
    path.write_text(json.dumps(store.export()), encoding="utf-8")
    assert len(load_regional_history(path, source_image_sha256=store.image_sha256)) == 1
    path.write_bytes(b" " * (MAX_HISTORY_BYTES + 1))
    with pytest.raises(ValueError):
        load_regional_history(path, source_image_sha256=store.image_sha256)
    with pytest.raises(ValueError):
        load_regional_history(tmp_path, source_image_sha256=store.image_sha256)


def test_count_limits_and_identical_archive_dedup(store):
    payload = store.export()
    payload["threads"] *= 2
    assert len(decode(payload, store.image_sha256)) == 1
    payload["threads"] *= 33
    with pytest.raises(ValueError):
        decode(payload, store.image_sha256)
    payload = store.export()
    turn = payload["threads"][0]["turns"][0]
    payload["threads"][0]["turns"] = [
        dict(turn, review_turn_id=f"{i:032x}") for i in range(513)
    ]
    with pytest.raises(ValueError):
        decode(payload, store.image_sha256)


def test_v3_nested_image_and_duplicate_ids_checked(store):
    history = decode(store.export(), store.image_sha256)[0]
    restored = store.restore_archive(history)
    store.append(restored, question="new", answer="new", review_turn_id="b" * 32)
    payload = store.export()
    payload["archived_threads"][0]["history"]["source_image_sha256"] = "c" * 64
    with pytest.raises(ValueError):
        decode(payload, store.image_sha256)
    payload = store.export()
    payload["archived_threads"][0]["turns"][0]["review_turn_id"] = "a" * 32
    with pytest.raises(ValueError):
        decode(payload, store.image_sha256)


def test_good_first_thread_does_not_hide_bad_later_thread(store):
    payload = store.export()
    payload["threads"].append({"finding_id": "bad"})
    with pytest.raises(ValueError):
        decode(payload, store.image_sha256)
    assert not store.archived_threads


def test_collection_cap_is_atomic_across_multiple_files(store):
    history = decode(store.export(), store.image_sha256)[0]
    for index in range(64):
        store.restore_archive(replace(history, finding_id=f"historical-{index}"))
    before = store.export()
    with pytest.raises(ValueError, match="Too many"):
        store.restore_archive(replace(history, finding_id="one too many"))
    assert store.export() == before


def test_archived_context_budget_and_historical_id_not_reused(store):
    history = decode(store.export(), store.image_sha256)[0]
    turns = tuple(
        replace(history.turns[0], review_turn_id=f"{index:032x}", answer="x" * 20_000)
        for index in range(10)
    )
    thread = store.restore_archive(replace(history, turns=turns))
    context = json.loads(thread.context())
    assert len(context["turns"]) <= 6
    assert len(thread.context()) < 12_100
    assert len(thread.all_turns) == 10
    with pytest.raises(ValueError, match="already belongs"):
        store.append(
            thread, question="new", answer="new", review_turn_id=turns[0].review_turn_id
        )


@pytest.mark.parametrize("op", ["add", "revise", "retract"])
def test_real_parser_blocks_all_report_operations_in_archive_scope(store, op):
    history = decode(store.export(), store.image_sha256)[0]
    response = parse_region_review_response(
        json.dumps(
            {
                "answer": "Still visible to reviewer",
                "proposal": {"op": op, "target_id": "f1"},
            }
        ),
        selected_region=history.region,
        selected_finding=None,
        new_finding_id="not-used",
        local_signal_audit={"status": "ok", "low_signal": False},
        allow_add=False,
    )
    assert response.delta is None
    assert response.warning
    assert response.answer == "Still visible to reviewer"
