# Astra medium transition — September 24, 2026

The user changed the active desktop target from GPT-6 Astra low to **GPT-6 Astra
medium** (GPT-6 Luna xhigh is an allowed alternative, not an automatic fallback).
The Astra preset now stores `thinkingDefault=medium`; model identity remains
`openai/gpt-6-astra`, subscription transport remains `openai-chatgpt-responses`,
and inference ownership remains OpenClaw. No Platform API key or Codex agent
runtime is enabled. Existing settings change only when explicitly saved through
Settings and applied by restarting the App/Gateway.

The [official Astra model page](https://developers.openai.com/api/docs/models/gpt-6-astra)
fetched September 24 lists medium reasoning support. Documentation does not prove
account access or actual runtime effort: each new real GUI turn still needs its
bound model/effort/usage receipt. No new clinical advantage is claimed from a
preset change, and the existing deadlines are not relaxed to hide slow turns.

## Keep evidence separated

- The sealed 121-case failed cohort and all historical low predictions remain
  immutable and low-labeled. They do not count as medium acceptance.
- The clean 128117b package and its 90.980 s hidden-label probe remain low evidence;
  the later heading fix and medium setting need a new verified build/run.
- New medium trials must use the actual App/Viewer open/analyze/export workflow,
  preserve failed attempts, record the same image/ROI and runtime identity, and
  distinguish exposed development cases from new blind clinical acceptance.
- The first medium live checkpoint is below; no model fallback has been introduced.

## Clean frozen package and actual GUI checkpoint

Source `9a27b61d261f451702a3e8d6f5c3cfbf47438f0a` is clean at build time; public
harness pin remains `3c7645ec2c41364e8ae521416ae758ddb81ea7c3`. Python 3.13.12,
PyInstaller 6.19.0 and UPX 5.2.1 produce 18,771 files. All 90 native source paths
are approved. The full package verifier passes, followed by **20 frozen smoke
checks in 101.48 s**. App source regression: **1,594 passed / five explicit skips
in 244.47 s**; Ruff passes. Push/PR CI `35979153574` / `35979159199` and secret
scans `35979153553` / `35979159306` pass for this exact source.

| Layer | Bytes | MiB |
| --- | ---: | ---: |
| Launcher | 4,910,537 | 4.68 |
| App / Python / Qt (includes launcher) | 57,069,166 | 54.43 |
| OpenClaw 2026.9.3 | 272,805,439 | 260.17 |
| Node 24.18.0 | 23,515,464 | 22.43 |
| Full zero-install folder | 353,390,069 | 337.02 |

The total is 226 bytes above the prior 128117b build; no dependencies were added.
Source-tree SHA-256: `0ed3d311e7ac762bfd39899af9611c9b48e67236754c6c746eea19e816fb4291`.
Launcher SHA-256: `d0899e4fa94261e5ad757c06d0c7eabd8c46a22e79e051651fd2886ed5aa430a`.
Payload-tree SHA-256: `a8918f2a91ed4f59de0613c6fe0d616cb1a975aeecc723c97d356d977e6e9f69`.
The private writable live copy matches every payload file; the frozen folder is
unchanged. No public binary release is made.

Actual Settings selected Astra, showed `medium`, saved, and the App was gracefully
quit/restarted. Official pinned OAuth-only migration succeeded, with OpenClaw
agent ownership, no Codex agent runtime, no Platform API key and no fallback models.
The test used the real Viewer QFileDialog and App Analyze/Export buttons, not a
direct inference script. Gateway protocol 4 is retained in the result.

- Exposed development case index 119; deliberately narrow authorized ROI
  `(150,81,1370,708)` contains eight rows with labels hidden. Viewer/source pixel
  comparison MAE is 0.0. Source SHA-256 is
  `cce82cb830055010eed9296e5c4cb7146e9b46ac2658c2e4ccf7603adc6f8e94`, identical
  to the prior low probe, not a new blind case.
- Export `desktop-20260924-092539-313629`; result SHA-256
  `0b7c01e681a7df7d5b0ea80d19b624e7e6925a8078c4016bd1f63faddc833bf1`.
- Analysis **105.468 s**, actual open/analyze/export workflow **113.323 s**.
  Four coarse/refine/refine/final turns, no parse retries; all four runtime and
  public-session bindings verify `gpt-6-astra` / `medium`. Read-only collection
  made zero extra model requests. Public snapshots are not a billing ledger.
- Both initial hypotheses were retracted after crop review; final findings are
  empty, all 16 checklist axes are informational/indeterminate, and the summary
  explicitly cannot establish normal rhythm/conduction/repolarization. All eight
  rows remain unknown/hidden and crop-lead maps remain empty. Result remains
  incomplete and review-required. Retraction does not establish a normal ECG.
- Visually inspected actual summary: the fixed heading correctly says
  `Partial EKG Analysis`, but the severity prefix incorrectly presents `NORMAL`.
  This is a newly observed presentation defect, not an acceptable normal result.
  The original export stays unchanged; a separate correction/verification must
  not be claimed as present in this frozen build.

This single development pair does not establish a speed or accuracy improvement:
medium's 105.468 s is longer than the prior low replay's 90.980 s, and neither has
adjudicated clinical acceptance. Raw results, UI captures and usage remain private.

## Remaining integration and project-organization work

Inspection confirmed that the App parser currently drops public observation /
evidence-ledger fields. The scientific contract requires model-produced atomic
observations and host-owned source, transform, study and workflow bindings. Do not
retroactively invent observations, successful quality gates or verified provenance
to make historical output validate. Strict assembly and the live draft protocol
must be wired together; an unused assembler is not completed integration.

The user's new organization requirement is to separate desktop App, neutral image
harness and OpenClaw plugin responsibilities, and archive documentation by purpose.
Preserve DDD and the public Gateway boundary, update build/test/link consumers for
every moved file, keep current operational guidance separate from dated evidence,
and preserve immutable raw artifacts. Do not add compatibility wrappers. This work
was started after this checkpoint: 22 documentation files are relocated by purpose,
with a central index, component map and local-link regression. Runtime/plugin
source paths remain unchanged; full plugin architecture work is still pending.

Clinical UX must emphasize conclusions, priority concerns, evidence/limitations and
useful next review steps, not just terminology or internal trace fields. True
uncertainty from missing leads or poor images must not be replaced with an invented
diagnosis. Diverse vendor/legacy ECG, complete MCP/external-tool binding, the latest
OpenClaw upgrade audit and the PyQt6 distribution-license gate remain open.
