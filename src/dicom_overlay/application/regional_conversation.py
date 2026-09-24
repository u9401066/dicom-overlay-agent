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


@dataclass
class RegionalThread:
    region: RegionRect
    finding_id: str
    turns: list[RegionalTurn] = field(default_factory=list)

    def context(self) -> str:
        """Bound context cost without deleting the full visible/export history."""
        selected: list[dict[str, str]] = []
        remaining = 12_000
        for turn in reversed(self.turns[-6:]):
            pair = {"question": turn.question[:2_000], "answer": turn.answer[:8_000]}
            size = len(json.dumps(pair, ensure_ascii=False))
            if size > remaining:
                break
            selected.insert(0, pair)
            remaining -= size
        return json.dumps(
            {"omitted_turns": len(self.turns) - len(selected), "turns": selected},
            ensure_ascii=False,
        )

    def transcript(self) -> str:
        return "\n\n".join(
            f"{index}. Q: {turn.question}\nA: {turn.answer}"
            + (
                f"\nSuggested change (not confirmation): {turn.proposal}"
                if turn.proposal
                else ""
            )
            for index, turn in enumerate(self.turns, 1)
        )


class RegionalConversations:
    def __init__(self) -> None:
        self.image_sha256 = ""
        self._threads: dict[tuple[object, ...], RegionalThread] = {}

    def clear(self) -> None:
        self.image_sha256 = ""
        self._threads.clear()

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
        if not any(current is thread for current in self._threads.values()):
            return False
        turn_id = uuid4().hex if review_turn_id is None else review_turn_id
        validate_review_turn_id(turn_id)
        if any(
            turn.review_turn_id == turn_id
            for current in self._threads.values()
            for turn in current.turns
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
        return {
            "schema_version": 2,
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
