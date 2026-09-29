# Regional QA: selected crop plus same-snapshot context

## Why

The [frozen desktop check](../evidence/2026-09/frozen-regional-desktop-2026-09-29.md)
exposed a46x20px selected ECG marker. Enlarging it did not restore the lead label,
calibration or neighboring waveform. The model correctly reported those limits,
but lacked the surrounding pixels already present in the authorized image ROI.

The source candidate now attaches two PNGs in one structured regional-review
`chat.send`. This is not an extra inference turn or a new screen capture. It does
increase image input volume; no token, latency or clinical accuracy improvement
is claimed without an actual comparison.

| Attachment | Origin | Purpose |
| --- | --- | --- |
| 1 | Existing selected-region crop, optionally enlarged | Local morphology |
| 2 | Unchanged `ReviewSnapshot.image_base64` | Same-image lead labels, visible calibration and surrounding morphology |

The crop coordinates remain normalized to attachment2, the original approved ROI.
The current/live screen is never substituted for that immutable snapshot. All
questions and reopen actions continue to use per-image/per-region thread identity.
Neither attachment can reveal pixels outside the prior user-approved ROI.

## Boundaries retained

- The prompt distinguishes observations inside the selected box from supporting
  surrounding context. Missing labels/calibration must not be invented.
- The model still cannot return new coordinates or enlarge/move the selected box.
- The mechanical signal audit uses the unscaled source crop. Additional context
  cannot upgrade an insufficient-resolution crop or bypass its writeback block.
- A selected multi-marker finding remains read-only even if other markers happen
  to be visible in the original ROI. One regional question is not a full re-review.
- Report changes still require explicit local reviewer confirmation. Context is
  not approval, a new diagnosis, or a modification of the canonical report.
- Existing stale-image/revision guards reject a late response after image change.
- The refine stage remains crop-only. Only structured QA receives the second PNG.

## Transport and evidence

`build_openclaw_chat_frame` appends an optional `context_image_base64` after the
primary PNG using the existing public `params.attachments[]` envelope:
`type=image`, `mimeType=image/png`, `content=base64`. Empty context or context
without a primary image is rejected. Ordinary one-image requests are unchanged.
The pinned OpenClaw2026.9.3 public chat schema declares attachments as an array;
no SDK/internal module is imported and no runtime version bump is required.

The locked client method hashes both decoded payloads before sending, then returns
the same turn's run trace with `image_attachment_count=2`, `selected_crop_sha256`
and `source_image_sha256`. These bounded metadata fields survive the report audit
whitelist; image bytes and credentials are not copied into the result trace.
The hashes identify local submitted payloads, not independent proof that a model
correctly interpreted either image. Public history/runtime evidence is separate.

GPT-6 Astra supports image input and medium reasoning according to the
[official model documentation](https://developers.openai.com/api/docs/models/gpt-6-astra).
That capability statement does not prove this OpenClaw dual-image integration
works; actual App acceptance must exercise and inspect the new path.

## Verification scope

Offline checks cover attachment order, unchanged PNG envelope, one submission,
atomic payload/run binding, malformed context before send, immutable snapshot
selection rather than a newer live image, preserved low-signal/multi-marker
gates, and history/outcome trace preservation. Source changes are not present in
the previously accepted575bcdc EXE. A fresh actual App/usage/UI replay and a later
rebuild are required; the old sealed runtime must not be restarted or relabeled.

The subsequent [actual source-App replay](../evidence/2026-09/regional-context-desktop-2026-09-29.md)
now verifies three two-image questions, exact Gateway-retained PNG hashes,
separate histories and source invalidation. Updated EXE acceptance and broader
clinical validation remain pending.
