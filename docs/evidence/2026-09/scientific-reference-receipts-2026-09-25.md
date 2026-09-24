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

Remote20e2690 CI36073119191 exposed an outdated fixed-pin test literal on both
Ubuntu and Windows. The earlier local full run had evaluated that assertion
before the submodule commit changed HEAD, so it did not establish final committed
CI acceptance. Updated the expected pin and current architecture document to
d9798da, preserving the strict pin check. Boundary/documentation31pass1.79s;
fresh full regression is running. No clinical/runtime validation gate was relaxed.

## Fresh confirm-graph replay: second look canceled by total deadline

Private `C:/Users/Ericlab/AppData/Local/Temp/dicom-scientific-desktop-20260925-confirm-graph`
launched source1eb0565 (launcher14196/App5404/Gateway23616, Viewer7832,18796).
Only the pin test and docs changed during startup; production/schema/skill hashes
remained unchanged. Actual Analyze used clean checkpoint7b35d0d and the same
exposed crop/ROI, not an additional independent case. OAuth71.537s and profile
check32.653s remain separate cold-start measurements.

QC, blind, native localization and reconciliation completed. Both retained
findings used confirm without changing their linked observations. The App then
sent the fifth second-look request but canceled it at the existing total180s
analysis SLA. Attempt wall time185.070s includes file/UI overhead. No prepared
review, Qt handoff, displayed report or export was produced.

| Stage | Actual run ID | Turn elapsed ms |
| --- | --- | ---: |
| QC | 99fd829f-bdc0-4135-8000-3520818b52a0 | 12856 |
| Blind | 8d932775-434a-484b-b00e-0328965bbc2e | 47468 |
| Native localization | 337776e4-77ab-4540-a0a3-69b5ddf22bb8 | 12930 |
| Reconcile | a3776781-771d-4a37-a66c-c919f9cddef3 | 55873 |
| Second look, canceled | 66683f95-8d5d-4c36-87ea-d520251f24e5 | no completed receipt |

Gateway log confirms the last run was aborted and `chat.abort` succeeded (54ms).
There was no automatic retry. The private store retains the four returned turns
under host run `41a882aef36c443c925ecb40ecb37c93`; it does not invent a completed
fifth body from partial stream or history. Public read-only query
`public-evidence-20260924-234751` verifies five Astra-medium session identities
against runtime log lines55/194/1597/1676/3116. Literal usage input/output/total:
QC6720/178/6720, blind9169/2658/9169, localization10447/389/9995,
reconcile12754/3110/12754, aborted second look null/null/0. Missing usage is not
zero cost; none of these snapshots is an additive billing ledger.

- Public usage receipt SHA256:
  `c9e84128a8b1240c3a5f46f23701945a6e298713478e2c17a457d768967f8c97`.
- Attempt receipt SHA256:
  `0371cda80dc16b1a9a4ceb8d77c499a72738ccfa9c3fa6787f3b9f49f2403022`.
- Actual Quit stopped App/launcher/Gateway; port18796 listener absent. Viewer
  retained. This fifth isolated runtime is sealed; never restart it.

Two important open issues remain: scientific preparation currently shares the
legacy total180s deadline, and both actual reconciliation drafts kept only
source-frame evidence with empty finding bbox references despite a completed
native localization turn. A valid geometry/tool receipt is not proof of adopted
finding localization. Do not silently attach boxes, extend the SLA and call it a
speed improvement, or claim completed regional QA under this scientific mode.
Next work must address bounded stage budgeting, response efficiency, and explicit
localization acceptance/rejection while retaining actual source and claim checks.

Final current-source local suite1904: **2417 passed /8 skipped in407.03s**.
Both local runs used supported portable Node24. Remote pin-fix CI36074069157/
36074064451 and secret scans36074069175/36074064496 all completed successfully.
Final documentation recheck:12 passed in0.10s. No clinical improvement,
new EXE acceptance or complete five-stage App success is claimed.
