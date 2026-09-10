# Bbox receipt canonicalization — 2026-09-11

## Observed failure, not a clinical score

Read-only public Gateway `chat.history` inspection of a failed finalization
confirmed that the model submitted the exact retained draft coordinates to
`dicom_bbox_validate` and copied the accepted coordinates into its final JSON.
The seven accepted boxes still failed the App's exact draft-geometry digest.
The first finalization consumed 70.364 seconds; its retry was aborted after
9.876 seconds by the existing 80-second stage budget. This is one diagnostic
example, not a measured improvement or an estimate of all cohort failures.

The native tool always recomputed width/height as `(origin + extent) - origin`,
including when no clipping occurred. Floating-point cancellation changed a
half-tie before four-decimal canonicalization. A deterministic synthetic example
is `y=0.25, h=0.07475`: the old tool returned `h=0.0747`, while the host's exact
extent canonicalized to `0.0748`. The receipt correctly failed its comparison;
relaxing that comparison would hide the producer defect.

## Narrow correction

Plugin 1.5.9 preserves the submitted extent when that axis was not clipped. It
only subtracts clipped endpoints when clipping actually changed an endpoint.
Image/turn nonce binding, exact multiset digest, retained finding IDs, source
geometry lock, minimum extent and EKG area/width/height gates remain enforced.
There is no tolerance increase, new diagnosis, changed model prompt or ROI
expansion. Independently rounded coordinates that overflow the image are now
explicitly rejected (`rounded_box_out_of_bounds`) rather than accepted outside
the source. The receipt schema stays at version 2.

## Regression evidence and limitations

- Initial synthetic parity test: 23 failures / 13 passes across 36 unclipped
  placements and decimal boundaries, before the correction.
- After correction: 94 native-plugin, canonicalization and Gateway-edge checks
  pass. New cases cover four real clipping edges, broad/disjoint boxes, rounded
  edge overflow, exact final geometry locking and a tampered receipt rejection.
- Full unit/smoke/mock-integration regression: **1,505 passed / five explicit
  opt-in/local-artifact skips (210.59 s)**; Ruff passes.
- Windows CI separately exposed a 20 ms wall-clock scheduling-policy test.
  It now uses the existing injected clock with the same budget proportions and
  verifies the observed-duration 1.25 multiplier exactly. All 139 multi-pass
  checks pass; production SLA and real timeout/cancellation tests are unchanged.

The running 7.1-2 UI cohort, its failed predictions and usage receipts are not
patched or rescored with this correction. A fresh candidate GUI/model run must
establish whether it reduces retries and end-to-end latency. Neither synthetic
parity nor replaying captured tool arguments is clinical validation.

The separately preserved `7abc364` package still contains plugin 1.5.8. Its
static verification and 20 actual frozen smoke checks pass, but those receipts
do not cover this later correction. Distribution and actual clinical acceptance
gates remain open.
