# Documentation / 文件導覽

Current operating guidance, component contracts and dated evidence have different
purposes. Start here; a dated successful smoke run is not current clinical approval.

## Current checkpoint — September 24, 2026

September 25 update: the [120-case real desktop batch](evidence/2026-09/medium-desktop-batch-2026-09-24.md)
is sealed/scored and failed clinical acceptance. An [explicit lead-inventory correction](evidence/2026-09/explicit-lead-inventory-2026-09-25.md)
now passes one actual exposed-case source-App replay, without changing the baseline.
Its [portable-plugin/readiness follow-up](evidence/2026-09/portable-plugin-readiness-2026-09-25.md)
verifies new-path loading, startup/busy shortcut suppression and successful ready-state analysis.

The active desktop target is **GPT-6 Astra medium**, through subscription OAuth
with OpenClaw owning inference. The clean `9a27b61` Windows package passes its
package checks and one actual partial/hidden-label development replay; all four
turns have bound medium usage receipts. This is not new blind clinical acceptance.
The older sealed 121-case Astra-low cohort remains failed and immutable.
See the [medium checkpoint](evidence/2026-09/astra-medium-2026-09-24.md).
The [regional interaction checkpoint](evidence/2026-09/regional-interaction-2026-09-24.md)
separates the corrected blank-ROI Mark hit testing from incomplete live QA/history.
Its [history follow-up](evidence/2026-09/regional-history-2026-09-24.md) records actual
manual two-turn QA, separate AI-region QA, Apply and history-export tests.
The [external-window checkpoint](evidence/2026-09/external-window-selection-2026-09-24.md)
adds explicit session-local selection and cautious report headings. Its
[native browser follow-up](evidence/2026-09/native-browser-selection-2026-09-24.md)
records one exposed Edge capture/inference/manual-QA replay, not broad acceptance.
Further actual App checks cover [Viewer movement](evidence/2026-09/native-regional-projection-2026-09-24.md),
[ROI preview](evidence/2026-09/roi-preview-pixels-2026-09-24.md), and
[mid-analysis image replacement](evidence/2026-09/image-publication-guard-2026-09-24.md).
The [interaction package and promotion follow-up](evidence/2026-09/interaction-package-and-promotion-2026-09-24.md)
distinguishes the rebuilt `bd8f303` executable from subsequent source-only history
handoff and stale-writeback protection. Neither adds clinical cohort acceptance.
The [native promotion follow-up](evidence/2026-09/native-marker-promotion-2026-09-24.md)
now verifies real ADD dismissal, later approval, history migration/reopening and
third-turn follow-up on clean 243f2ef, without claiming a new frozen release.
The [3029dfb package refresh](evidence/2026-09/interaction-package-refresh-2026-09-24.md)
now includes those interaction/source-identity fixes, verifies all 60 bundled App
modules and passes 20 frozen smoke checks. Its byte-verified ZIP is local only;
native acceptance of this new EXE and the license gate remain open.

The isolated [report-note presentation candidate](evidence/2026-09/report-note-presentation-2026-09-24.md)
keeps clinical crop limitations visible and makes original ROI/bbox notes available
in Process. Scaled synthetic rendering is distinct from pending native acceptance.

The candidate runtime remains OpenClaw 2026.9.3 / Node 24.18.0. Adoption of 2026.9.6,
complete canonical evidence-ledger wiring, diverse legacy/vendor ECG acceptance,
clinical accuracy improvement and the PyQt6 binary-distribution license are open.
Source branches/PRs are development checkpoints, not approved medical releases.

## Choose a starting point

| Task | Maintained entry point |
| --- | --- |
| Install, run, choose provider | [English README](../README.md), [繁體中文 README](../README.zh-TW.md) |
| Operate the real desktop and collect evidence | [Real desktop runbook](operations/real-desktop-tests.md) |
| Locate App, neutral harness and plugin owners | [Component map](architecture/components.md), [architecture](architecture/overview.md) |
| Understand product requirements | [Specification](architecture/specification.md), [roadmap](../ROADMAP.md) |
| Work on independent image interpretation | [Direct harness integration](architecture/direct-harness-integration.md) |
| Work on OpenClaw / external evidence | [OpenClaw integration](../openclaw/README.md), [ECGFounder contract](integrations/ecgfounder-tool.md) |
| Maintain clinical YAML and generated SQLite | [Clinical knowledge governance](../clinical_knowledge/README.md) |
| Review the complete ECG reading sequence and its open integration gaps | [EKG human/agent workflow](clinical/ekg-reading-workflow.md) |
| Assemble source-bound scientific drafts (isolated candidate; not desktop-wired) | [Host evidence assembly](architecture/host-evidence-assembly.md) |
| Decode model-led observations without model-owned provenance (inactive protocol) | [Scientific model draft](architecture/scientific-model-draft.md) |
| Bind native bbox receipts to actual source/crop pixels (isolated component) | [Native source evidence](architecture/native-source-evidence.md) |
| Preserve original visible Gateway model/tool text (opt-in; live acceptance pending) | [Gateway evidence capture](architecture/gateway-evidence-capture.md) |
| Record real stage execution, failure and cancellation (isolated component) | [Host execution journal](architecture/execution-journal.md) |
| Execute source intake, quality gate and blind reading (intermediate candidate) | [Scientific image session](architecture/scientific-image-session.md) |
| Interpret dataset metrics | [Cohorts and denominators](evaluation/cohorts.md) |
| Seal and score the completed medium GUI batch without rerunning inference | [Verified desktop batch scoring](evaluation/verified-desktop-batch.md) |
| Audit privacy, licensing and contributors | [Security](../SECURITY.md), [notices](../THIRD_PARTY_NOTICES.md), [contributing](../CONTRIBUTING.md) |

## Archive policy

- `evidence/YYYY-MM/`: dated runs, failures, model transitions and upgrade decisions.
  [September evidence](evidence/2026-09/) and [August evidence](evidence/2026-08/)
  retain their dates, commits, denominators and limitations. Relocation only fixes
  navigation; it does not re-score or relabel historical results.
- `references/YYYY-MM/`: dated reviews of external harness designs and sources.
  [Reference reviews](references/2026-08/) do not prove this App's performance.
- `architecture/`, `operations/`, `evaluation/`, `integrations/`: maintained
  explanations and contracts, with links to the evidence that supports claims.
- `site-design/`: website design artifacts; `../site/` is the deployable Pages site.
- `../memory-bank/`: maintenance history, not the user's primary manual. Raw image,
  model, OAuth and GUI artifacts remain private in ignored artifact directories;
  they are not copied into documentation or public fixtures.

Every move must update relative links, Pages links and executable/help consumers.
Run `uv run pytest tests/smoke/test_documentation_links.py` before committing.
Do not leave redirect stubs or compatibility copies at old file paths.
