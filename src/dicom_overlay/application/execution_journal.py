"""Host-owned execution facts, not a ledger reconstructed from model prose.

Callbacks must implement the named stage and retain their raw artifacts outside
this bounded metadata journal. Successful callback execution is not independent
attestation of clinical correctness or of what an opaque provider did internally.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from functools import lru_cache
from hashlib import sha256
from time import monotonic_ns
from typing import TYPE_CHECKING, Any, Generic, TypeVar
from uuid import uuid4

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from medical_image_harness.provenance import canonical_json_sha256
from medical_image_harness.schema import load_schema

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_VALUE = TypeVar("_VALUE")
_STAGES = (
    "intake",
    "quality_gate",
    "blind_pass",
    "independent_evidence",
    "reconcile",
    "targeted_second_look",
    "contract_validation",
    "human_handoff",
)
_OPTIONAL = {"independent_evidence", "targeted_second_look"}
_INTERPRETATION = {
    "blind_pass",
    "independent_evidence",
    "reconcile",
    "targeted_second_look",
}
_MAX_ARTIFACTS = 128
_MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
_MAX_STAGE_BYTES = 64 * 1024 * 1024


class ExecutionJournalError(ValueError):
    """Fixed failure categories only; no exception text, model prose or PHI."""


@dataclass(frozen=True)
class StageOutput(Generic[_VALUE]):
    """Callback output and original byte artifacts, not a scientific data model."""

    value: _VALUE = field(repr=False)
    artifacts: tuple[bytes, ...] = field(repr=False)


@dataclass(frozen=True)
class StageRecord:
    run_id: str
    source_image_sha256: str
    sequence: int
    stage: str
    status: str
    started_utc: str
    started_ns: int
    finished_ns: int | None
    artifact_sha256: tuple[str, ...]
    category: str
    previous_record_sha256: str
    record_sha256: str = ""


@lru_cache(maxsize=1)
def _quality_validator() -> Any:
    return Draft202012Validator(load_schema()["$defs"]["imageQuality"])


def _require(condition: bool, category: str) -> None:
    if not condition:
        raise ExecutionJournalError(category)


class ExecutionJournal:
    """Single-run stage runner with explicit order, failure and skip boundaries.

    There is intentionally no append-completed/import-existing-events API. This
    records actual callback invocation and return, not the truth of its contents.
    A trusted host can still supply a no-op or false artifacts; a hash chain is
    not a signature. Runtime integration must use real operations and receipts.
    """

    def __init__(self, source_bytes: bytes, *, deidentified: bool) -> None:
        _require(deidentified is True, "untrusted_deidentification")
        _require(
            type(source_bytes) is bytes
            and 0 < len(source_bytes) <= _MAX_ARTIFACT_BYTES,
            "invalid_immutable_source",
        )
        self._run_id = uuid4().hex
        self._source_sha = sha256(source_bytes).hexdigest()
        self._records: list[StageRecord] = []
        self._active: StageRecord | None = None
        self._blocked = False
        self._adequacy: str | None = None

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def source_image_sha256(self) -> str:
        return self._source_sha

    def snapshot(self) -> tuple[StageRecord, ...]:
        return tuple(self._records) + ((self._active,) if self._active else ())

    def _check_next(self, stage: str) -> None:
        _require(self._active is None, "stage_already_running")
        _require(not self._blocked, "failed_run_cannot_continue")
        _require(len(self._records) < len(_STAGES), "run_already_finished")
        _require(stage == _STAGES[len(self._records)], "stage_out_of_order")

    def _start(self, stage: str) -> None:
        self._active = StageRecord(
            self._run_id,
            self._source_sha,
            len(self._records) + 1,
            stage,
            "running",
            datetime.now(UTC).isoformat(),
            monotonic_ns(),
            None,
            (),
            "",
            self._records[-1].record_sha256 if self._records else "",
        )

    def _finish(self, status: str, category: str, hashes: tuple[str, ...] = ()) -> None:
        assert self._active is not None
        record = replace(
            self._active,
            status=status,
            category=category,
            finished_ns=monotonic_ns(),
            artifact_sha256=hashes,
        )
        record = replace(record, record_sha256=canonical_json_sha256(asdict(record)))
        self._records.append(record)
        self._active = None
        self._blocked = status in {"failed", "cancelled"}

    async def execute(
        self, stage: str, operation: Callable[[], Awaitable[StageOutput[_VALUE]]]
    ) -> _VALUE:
        self._check_next(stage)
        _require(
            not (self._adequacy == "non_diagnostic" and stage in _INTERPRETATION),
            "non_diagnostic_inference_forbidden",
        )
        _require(callable(operation), "stage_operation_required")
        self._start(stage)
        hashes: tuple[str, ...] = ()
        task = asyncio.current_task()
        cancellations = task.cancelling() if task else 0
        try:
            output = await operation()
            # A callback swallowing a newly requested cancellation must not
            # turn the interrupted stage into a completed execution receipt.
            if task and task.cancelling() > cancellations:
                raise asyncio.CancelledError
            _require(isinstance(output, StageOutput), "invalid_stage_output")
            artifacts = output.artifacts
            _require(
                type(artifacts) is tuple and 0 < len(artifacts) <= _MAX_ARTIFACTS,
                "missing_or_excessive_stage_artifacts",
            )
            _require(
                all(
                    type(raw) is bytes and 0 < len(raw) <= _MAX_ARTIFACT_BYTES
                    for raw in artifacts
                ),
                "invalid_stage_artifact_bytes",
            )
            _require(
                sum(map(len, artifacts)) <= _MAX_STAGE_BYTES,
                "stage_artifact_size_limit",
            )
            hashes = tuple(sha256(raw).hexdigest() for raw in artifacts)
            if stage == "intake":
                _require(self._source_sha in hashes, "intake_source_artifact_missing")
            if stage == "quality_gate":
                _require(
                    isinstance(output.value, dict)
                    and not list(_quality_validator().iter_errors(output.value)),
                    "invalid_public_quality_result",
                )
                # Keep only the validated category, not clinical text or mutable
                # callback output. Public assembly must still validate the draft.
                quality = output.value
                assert isinstance(quality, dict)
                self._adequacy = quality["adequacy"]
        except asyncio.CancelledError:
            self._finish("cancelled", "operation_cancelled", hashes)
            raise
        except BaseException:
            self._finish("failed", "operation_failed", hashes)
            raise
        self._finish("completed", "operation_returned", hashes)
        return output.value

    def skip(self, stage: str, *, reason: str) -> None:
        self._check_next(stage)
        if self._adequacy == "non_diagnostic" and stage in _INTERPRETATION:
            _require(reason == "non_diagnostic_input", "invalid_skip_reason")
        else:
            _require(stage in _OPTIONAL, "required_stage_cannot_be_skipped")
            _require(reason == "not_requested", "invalid_skip_reason")
        self._start(stage)
        self._finish("skipped", reason)

    def workflow_events(self) -> list[dict[str, str]]:
        """Project only recorded facts into the pinned public event shape.

        Partial/failed projections remain partial/failed and do not pass full
        contract validation. No missing step is appended, sorted or upgraded.
        """
        _require(self._active is None, "stage_still_running")
        return [
            {
                "stage": record.stage,
                "status": "failed" if record.status == "cancelled" else record.status,
                "detail": (
                    f"Host {record.category}; run={record.run_id}; "
                    f"source_sha256={record.source_image_sha256}; "
                    f"record_sha256={record.record_sha256}"
                ),
            }
            for record in self._records
        ]
