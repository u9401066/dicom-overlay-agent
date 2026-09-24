from __future__ import annotations

import base64
import json

import pytest

from dicom_overlay.application.regional_conversation import RegionalConversations
from dicom_overlay.application.review_chat import build_region_review_prompt
from medical_image_harness.models import RegionRect


def _image(value: bytes = b"synthetic image identity") -> str:
    return base64.b64encode(value).decode()


def test_threads_are_isolated_by_region_and_finding_identity():
    store = RegionalConversations()
    store.bind(_image())
    a = store.thread(RegionRect(0.1, 0.2, 0.3, 0.4), "f1")
    store.append(a, question="Synthetic question", answer="Synthetic answer")
    assert store.thread(a.region, "f1") is a
    assert not store.thread(a.region, "f2").turns
    assert not store.thread(a.region).turns
    assert not store.thread(RegionRect(0.2, 0.2, 0.3, 0.4), "f1").turns
    assert "Synthetic answer" in a.transcript()
    assert json.loads(a.context())["turns"][0]["question"] == "Synthetic question"


@pytest.mark.parametrize("same_pixels", [False, True])
def test_new_image_or_new_analysis_rejects_late_thread_results(same_pixels):
    store = RegionalConversations()
    store.bind(_image())
    old = store.thread(RegionRect(0, 0, 1, 1))
    store.append(old, question="Old question", answer="Old answer")
    if same_pixels:
        store.clear()  # New analysis is a new scope even if pixels are identical.
    store.bind(_image() if same_pixels else _image(b"new image"))
    assert not store.append(old, question="Late", answer="Must not leak")
    assert store.export()["threads"] == []


def test_report_revision_without_image_change_keeps_thread():
    store = RegionalConversations()
    store.bind(_image())
    thread = store.thread(RegionRect(0, 0, 1, 1))
    store.append(thread, question="First", answer="First answer")
    store.bind(_image())
    assert store.thread(thread.region) is thread
    store.append(thread, question="Second", answer="Second answer")
    payload = store.export()
    assert len(payload["threads"][0]["turns"]) == 2
    payload["threads"][0]["turns"].clear()
    assert len(thread.turns) == 2  # Export is detached from live state.


def test_bounded_model_history_preserves_full_export_and_visible_history():
    store = RegionalConversations()
    store.bind(_image())
    thread = store.thread(RegionRect(0, 0, 1, 1))
    for i in range(10):
        store.append(thread, question=f"Q{i}" + "q" * 2500, answer=f"A{i}" + "a" * 9000)
    context = json.loads(thread.context())
    assert context["omitted_turns"] == 9
    assert context["turns"][0]["question"].startswith("Q9")
    assert len(thread.context()) < 12_100
    assert len(store.export()["threads"][0]["turns"]) == 10
    assert "A0" in thread.transcript()
    prompt = build_region_review_prompt(
        user_question="Follow up",
        prior_context="",
        selected_region=thread.region,
        selected_finding=None,
        regional_history=thread.context(),
    )
    assert "untrusted context" in prompt and "approval of a report change" in prompt
    assert "Q9" in prompt and "Q0" not in prompt


@pytest.mark.parametrize(
    "values", [(-0.1, 0, 1, 1), (0, 0, 0, 1), (0, 0, 2, 1), (float("nan"), 0, 1, 1)]
)
def test_rejects_invalid_region(values):
    store = RegionalConversations()
    store.bind(_image())
    with pytest.raises(ValueError):
        store.thread(RegionRect(*values))


def test_no_thread_without_current_image():
    with pytest.raises(ValueError, match="No current image"):
        RegionalConversations().thread(RegionRect(0, 0, 1, 1))


def test_turn_ids_are_unique_and_survive_promotion_without_entering_model_context():
    store = RegionalConversations()
    store.bind(_image())
    thread = store.thread(RegionRect(0, 0, 1, 1))
    store.append(thread, question="First", answer="Answer", review_turn_id="a" * 32)
    store.append(thread, question="Second", answer="Answer")
    before = store.export()
    assert before["schema_version"] == 2
    ids = [turn["review_turn_id"] for turn in before["threads"][0]["turns"]]
    assert len(set(ids)) == 2 and all(len(value) == 32 for value in ids)
    assert "review_turn_id" not in thread.context()
    assert store.promote_manual_region(
        thread.region, "confirmed", source_image_sha256=store.image_sha256
    )
    assert store.export()["threads"][0]["turns"] == before["threads"][0]["turns"]
    other = store.thread(RegionRect(0, 0, 0.5, 0.5))
    with pytest.raises(ValueError, match="already belongs"):
        store.append(other, question="Duplicate", answer="No", review_turn_id=ids[0])
    assert not other.turns


@pytest.mark.parametrize("turn_id", ["", "private free text", "A" * 32, "g" * 32])
def test_explicit_invalid_turn_id_does_not_append(turn_id):
    store = RegionalConversations()
    store.bind(_image())
    thread = store.thread(RegionRect(0, 0, 1, 1))
    with pytest.raises(ValueError, match="32 lowercase"):
        store.append(
            thread, question="Question", answer="Answer", review_turn_id=turn_id
        )
    assert not thread.turns


def test_confirmed_manual_promotion_preserves_history_under_new_finding_only():
    store = RegionalConversations()
    store.bind(_image())
    box = RegionRect(0.1, 0.2, 0.3, 0.4)
    manual = store.thread(box)
    store.append(manual, question="First", answer="Answer", proposal="Add marker")
    other = store.thread(box, "unrelated")
    store.append(other, question="Other", answer="Separate")
    assert store.promote_manual_region(
        box, "confirmed", source_image_sha256=store.image_sha256
    )
    assert store.thread(box, "confirmed") is manual
    assert manual.finding_id == "confirmed"
    assert not store.thread(box).turns
    assert store.thread(box, "unrelated") is other
    store.append(manual, question="Follow-up", answer="Continued")
    exported = store.export()["threads"]
    assert len(exported) == 2
    promoted = next(item for item in exported if item["finding_id"] == "confirmed")
    assert [turn["question"] for turn in promoted["turns"]] == ["First", "Follow-up"]
    assert promoted["turns"][0]["proposal"] == "Add marker"


@pytest.mark.parametrize(
    "reason", ["wrong_image", "empty_id", "collision", "different_box"]
)
def test_manual_promotion_never_merges_or_reassigns_unrelated_history(reason):
    store = RegionalConversations()
    store.bind(_image())
    box = RegionRect(0.1, 0.2, 0.3, 0.4)
    manual = store.thread(box)
    store.append(manual, question="Keep", answer="Original")
    if reason == "collision":
        store.append(store.thread(box, "new"), question="Other", answer="Other")
    before = store.export()
    assert not store.promote_manual_region(
        RegionRect(0.11, 0.2, 0.3, 0.4) if reason == "different_box" else box,
        " " if reason == "empty_id" else "new",
        source_image_sha256="different"
        if reason == "wrong_image"
        else store.image_sha256,
    )
    assert store.export() == before
    assert store.thread(box) is manual


def test_manual_promotion_is_one_time_and_cannot_restore_invalidated_image():
    store = RegionalConversations()
    store.bind(_image())
    box = RegionRect(0, 0, 1, 1)
    old = store.thread(box)
    store.append(old, question="Before", answer="Answer")
    image_sha = store.image_sha256
    assert store.promote_manual_region(box, "new", source_image_sha256=image_sha)
    assert not store.promote_manual_region(box, "new", source_image_sha256=image_sha)
    store.bind(_image(b"new source"))
    assert not store.promote_manual_region(box, "new", source_image_sha256=image_sha)
    assert not store.append(old, question="Late", answer="Do not restore")
    assert store.export()["threads"] == []
