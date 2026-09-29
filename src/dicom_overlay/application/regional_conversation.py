"""Image-scoped regional conversation state, owned by the desktop UI thread.

This is review context, not scientific evidence or permission to mutate findings.
Only explicit desktop export persists it; a new analysis resets the scope.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from medical_image_harness.models import RegionRect


def validate_review_turn_id(turn_id: str) -> None:
    """Accept only opaque host-generated IDs, never free-text evidence labels."""
    if len(turn_id) != 32 or any(char not in "0123456789abcdef" for char in turn_id):
        raise ValueError("Review turn ID must be 32 lowercase hexadecimal characters")


@dataclass(frozen=True)
class RegionalTurn:
    question: str
    answer: str
    created_at: str
    proposal: str = ""
    review_turn_id: str = ""


@dataclass(frozen=True)
class ArchivedConversation:
    """Untrusted past-run context, never a current finding or evidence receipt."""

    source_image_sha256: str
    finding_id: str
    region: RegionRect
    turns: tuple[RegionalTurn, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "source_image_sha256": self.source_image_sha256,
            "finding_id": self.finding_id,
            "region": {
                name: getattr(self.region, name) for name in ("x", "y", "w", "h")
            },
            "turns": [asdict(turn) for turn in self.turns],
        }

    @property
    def archive_id(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_payload(), sort_keys=True, ensure_ascii=False).encode(
                "utf-8"
            )
        ).hexdigest()


@dataclass
class RegionalThread:
    region: RegionRect
    finding_id: str
    turns: list[RegionalTurn] = field(default_factory=list)
    history: ArchivedConversation | None = None

    @property
    def all_turns(self) -> list[RegionalTurn]:
        return [*(self.history.turns if self.history else ()), *self.turns]

    def context(self) -> str:
        """Bound context cost without deleting the full visible/export history."""
        selected: list[dict[str, str]] = []
        remaining = 12_000
        turns = self.all_turns
        for turn in reversed(turns[-6:]):
            pair = {"question": turn.question[:2_000], "answer": turn.answer[:8_000]}
            size = len(json.dumps(pair, ensure_ascii=False))
            if size > remaining:
                break
            selected.insert(0, pair)
            remaining -= size
        return json.dumps(
            {"omitted_turns": len(turns) - len(selected), "turns": selected},
            ensure_ascii=False,
        )

    def transcript(self) -> str:
        text = "\n\n".join(
            f"{index}. Q: {turn.question}\nA: {turn.answer}"
            + (
                f"\nSuggested change (not confirmation): {turn.proposal}"
                if turn.proposal
                else ""
            )
            for index, turn in enumerate(self.all_turns, 1)
        )
        if self.history:
            return (
                f"Imported history: first {len(self.history.turns)} turns are "
                "unverified past-run context, not current report evidence. "
                "Continuation is Q&A only; use Inspect/Mark for report changes.\n\n"
                + text
            )
        return text


class RegionalConversations:
    def __init__(self) -> None:
        self.image_sha256 = ""
        self._threads: dict[tuple[object, ...], RegionalThread] = {}
        self._archives: dict[str, RegionalThread] = {}

    def clear(self) -> None:
        self.image_sha256 = ""
        self._threads.clear()
        self._archives.clear()

    @property
    def archived_threads(self) -> list[RegionalThread]:
        return list(self._archives.values())

    def archived_thread(self, archive_id: str) -> RegionalThread | None:
        return self._archives.get(archive_id)

    def restore_archive(self, history: ArchivedConversation) -> RegionalThread:
        """Activate only an explicitly selected, same-source archive, separately.

        IDs/boxes in an imported file cannot identify findings in a new analysis.
        Do not merge with live/manual threads, even for identical geometry.
        """
        if not self.image_sha256 or history.source_image_sha256 != self.image_sha256:
            raise ValueError("History belongs to a different original image")
        key = history.archive_id
        if key not in self._archives:
            histories = [
                current.history
                for current in self._archives.values()
                if current.history is not None
            ]
            histories.append(history)
            if (
                len(histories) > 64
                or sum(len(item.turns) for item in histories) > 512
                or sum(
                    len(
                        json.dumps(item.to_payload(), ensure_ascii=False).encode(
                            "utf-8"
                        )
                    )
                    for item in histories
                )
                > 4 * 1024 * 1024
            ):
                raise ValueError("Too many imported conversations for this image")
            self._archives[key] = RegionalThread(history.region, "", history=history)
        return self._archives[key]

    def bind(self, image_base64: str) -> None:
        digest = hashlib.sha256(
            base64.b64decode(image_base64, validate=True)
        ).hexdigest()
        if digest != self.image_sha256:
            self.clear()
            self.image_sha256 = digest

    def thread(self, region: RegionRect, finding_id: str = "") -> RegionalThread:
        values = (region.x, region.y, region.w, region.h)
        if not self.image_sha256:
            raise ValueError("No current image for regional conversation")
        if not all(math.isfinite(value) for value in values) or not (
            0 <= region.x < region.x + region.w <= 1 + 1e-9
            and 0 <= region.y < region.y + region.h <= 1 + 1e-9
        ):
            raise ValueError("Conversation region must be inside the original ROI")
        key = (finding_id, *(round(value, 6) for value in values))
        return self._threads.setdefault(key, RegionalThread(region, finding_id))

    def append(
        self,
        thread: RegionalThread,
        *,
        question: str,
        answer: str,
        proposal: str = "",
        review_turn_id: str | None = None,
    ) -> bool:
        # Detached objects from an invalidated image must never enter new history.
        current_threads = [*self._threads.values(), *self._archives.values()]
        if not any(current is thread for current in current_threads):
            return False
        turn_id = uuid4().hex if review_turn_id is None else review_turn_id
        validate_review_turn_id(turn_id)
        if any(
            turn.review_turn_id == turn_id
            for current in current_threads
            for turn in current.all_turns
        ):
            raise ValueError("Review turn ID already belongs to a conversation turn")
        thread.turns.append(
            RegionalTurn(
                question, answer, datetime.now(UTC).isoformat(), proposal, turn_id
            )
        )
        return True

    def promote_manual_region(
        self, region: RegionRect, finding_id: str, *, source_image_sha256: str
    ) -> bool:
        """Move history only after a confirmed ADD on the same source image.

        Never infer correspondence from overlap or merge unrelated histories.
        The caller must verify successful writeback before invoking this method.
        """
        if (
            not self.image_sha256
            or source_image_sha256 != self.image_sha256
            or not finding_id.strip()
        ):
            return False
        coordinates = tuple(
            round(getattr(region, name), 6) for name in ("x", "y", "w", "h")
        )
        old_key = ("", *coordinates)
        new_key = (finding_id, *coordinates)
        thread = self._threads.get(old_key)
        if thread is None or new_key in self._threads:
            return False
        del self._threads[old_key]
        thread.finding_id = finding_id
        self._threads[new_key] = thread
        return True

    def export(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 3 if self._archives else 2,
            "source_image_sha256": self.image_sha256,
            "coordinate_space": "normalized_original_roi",
            "content_role": "review_conversation_not_verified_findings",
            "threads": [
                {
                    "finding_id": thread.finding_id,
                    "region": {
                        name: getattr(thread.region, name)
                        for name in ("x", "y", "w", "h")
                    },
                    "turns": [asdict(turn) for turn in thread.turns],
                }
                for thread in self._threads.values()
                if thread.turns
            ],
        }
        if self._archives:
            payload["archived_threads"] = [
                {
                    # Past-run turn IDs stay here, never in this run's turns.
                    "history": thread.history.to_payload(),
                    "turns": [asdict(turn) for turn in thread.turns],
                }
                for thread in self._archives.values()
                if thread.history is not None
            ]
        return payload
