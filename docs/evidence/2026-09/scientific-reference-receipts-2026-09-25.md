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

## Actual App replay at 20e2690

Fresh private runtime `C:/Users/Ericlab/AppData/Local/Temp/dicom-scientific-desktop-20260925-multiref`:
launcher36668, App26484, Gateway34584, Viewer7832, port18796. Real file dialog and
Analyze opened the same exposed `crop_top_20` input at the authorized ROI
(30,30,1530,894); visible pixels were inspected, file-to-visible MAE0.4756584362.
OAuth import69.852s and profile check34.025s were cold startup, not inference speedup.

QC and blind passed; native localization executed one bbox tool and its independent
audit/source binding passed before reconciliation. The fourth model turn failed
`confirmation_changed_observation`: finding f1 was marked confirm but linked o3
changed anatomy wording and removed a negative clause. No second-look request,
Qt handoff, report publication or export occurred. Attempt wall time134.208s.
This is four actual model turns, not a complete scientific or clinical success.

| Stage | Actual run ID | Turn elapsed ms | Visible bytes |
| --- | --- | ---: | ---: |
| QC | 0d6a5b0f-b9d0-4ba7-b410-06f170fc4603 | 14697 | 798 |
| Blind | acab0dd0-2b0f-47b0-b16e-93233630b7ea | 46357 | 10436 |
| Native localization | 459598e0-bb6e-4f8e-a7fc-1003f061ac28 | 15071 | 266 |
| Reconcile, rejected | f4d8efca-861a-4227-b75c-3ada1b199029 | 53099 | 12932 |

Actual blind checklist arrays include rhythm `["o4","o5","o6"]`, ischemia
`["o1","o3"]` and t_wave `["o1","o7"]`. They survived the new decoder. All four
exact visible responses remain under host run `c9082eaeddc148aeb78e19609adde780`.
Blind SHA256 `d30c4440681739987303f6de1d53d1b37787440da3334c3e3ae404d6a5c6c3da`;
reconcile SHA256 `74af1b7ab71f293035b8b02273c98ba9c349625957045d69e1d55d1b124c49c7`.

Read-only public sessions/history plus matching runtime log session IDs verify
all four as `openai/gpt-6-astra`, `thinking=medium`. Public query added zero model
requests. Literal snapshots (input/output/total) are QC6732/190/6732,
blind9183/2622/9183, localization10683/525/10257, reconcile13253/3049/13253;
these are not additive billing amounts. No external classifier was executed.
Public query directory `public-evidence-20260924-233623` includes private config
and must not be published. Usage receipt SHA256
`bc0f9c4f08340c2c8c79169cefecec3ad592957c1ebb5b08c0f119054a0b3c80`;
attempt receipt SHA256
`76d52c2048c4440001d482a96de01d6bc0739aac1414f621ceeb8acb9c985025`.

Quit was invoked through the actual App UI. Launcher/App/Gateway and18796 listener
were confirmed absent. This runtime is sealed and must never restart.

Follow-up prompt now explicitly covers all linked observation fields and shared
observations for confirm/revise. It permits correction via revise, never automatic
rewriting of an old decision. Validator unchanged. Six synthetic anatomy/text/
question decision cases and a prompt invariant were added; reconciliation/session/
handoff/main:111 passed in6.76s, mypy/Ruff pass. Fresh live verification pending.
