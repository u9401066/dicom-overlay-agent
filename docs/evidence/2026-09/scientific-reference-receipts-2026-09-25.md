# Structured checklist references and private attempt receipts — 2026-09-25

## Reason for the change

The [third actual desktop attempt](native-scientific-startup-2026-09-25.md)
passed QC but stopped at a checklist item containing `"evidence": "o5, o6"`.
That string is not one observation ID. The public history projection also
truncated the long blind response, preventing exact replay after App exit.
The original failed attempt and its receipts remain unchanged.

## Explicit multi-observation contract

The public harness owns the added `ChecklistItem.observation_ids` field and JSON
Schema definition. Scientific prompts now request an array such as `["o5", "o6"]`.
Both canonical semantic validation and the App draft decoder check **every** ID.
Assessable items require at least one reference, each pointing to an assessable
`supported` or `possible` observation. References on unassessable items must also
resolve, but do not assert those observations are assessable.

The legacy single-ID `evidence` representation remains accepted. Two nonempty
representations, repeated or missing IDs, comma-joined lists, and unsupported
observations are rejected. No splitting, dropped references, inference retry or
rewrite of model text is performed. The extension retains the existing schema
version and is identified by the public submodule revision; older validators
cannot consume the added field. The legacy 16-key Gateway parser is unchanged.

## Private local retention

Only explicit `--scientific-review --deidentified-input` App mode enables the
new store under `data/scientific-attempts/<host-run-id>/` in the runtime directory.
The trusted operator's assertion is not automatic PHI removal. Source PNG bytes
and their intake hash are written once. After each successfully collected public
Gateway turn, exact decoded visible model bytes, allowlisted native bbox tool
text/audit artifacts and bounded metadata are saved **before** scientific decoding.
Thus malformed or rejected scientific output can still be examined locally.

Files are exclusively created and flushed to disk; `turn-NNNN/receipt.json` is the
last-written commit marker. Missing marker means an incomplete write. Existing
run directories are never reused or overwritten. Storage errors stop that attempt
without an automatic model retry. This is not a signed, tamper-proof journal.

The store accepts neither credentials nor prompts, arbitrary tool arguments,
hidden reasoning or full Gateway transcripts. It does not reconstruct missing
transport evidence if collection itself fails. Hashes identify bytes; they do not
prove clinical truth, provider usage, billing, or a completed scientific read.

These files inherit local directory permissions and are **not encrypted**. They
are private development evidence, not clinical exports; retain them only on the
authorized workstation, do not publish or package them, and manage deletion under
the operator's local retention policy. `data/` is ignored by Git. Retention is
currently manual; no automatic cleanup or cross-session clinical restore is added.

## Verification status

Before implementation the focused host multi-reference tests had 4 failures and
6 passes. After the contract change, draft/assembly/reconciliation:158 passed.
Public pin `d9798dae0cf4ac3e25578da127801bce6d4391b3`:494 passed in3.82s;
Codex/Copilot compatibility, Ruff and both remote CI runs passed. The staged
14.12KB diff passed secret scanning. Host prompt/documentation follow-up:51 passed
in0.71s after the public prompt update; documentation recheck:12 passed in0.10s.
Receipt/session/actual-main-construction tests:96 passed, including a long UTF-8
body beyond the observed history truncation length, malformed output, unchanged
whitespace, no storage without opt-in, no overwrite, and disk-write failure.
An initial Windows test-ID filename issue was fixed with short synthetic case IDs.

Full host regression: **2410 passed /8 skipped in414.22s**, session48321 terminal0.
The public prompt follow-up was separately checked as noted above. Changed host
modules pass mypy and Ruff; staged33.93KB secret scan clean. A **new** actual App
run remains pending. These
deterministic checks are not live-model or clinical acceptance, and no new EXE
acceptance is claimed. Broader goal requirements remain open.
