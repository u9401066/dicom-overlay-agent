# Documentation / 文件導覽

Current operating guidance, component contracts and dated evidence have different
purposes. Start here; a dated successful smoke run is not current clinical approval.

## Current checkpoint — September 24, 2026

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
| Interpret dataset metrics | [Cohorts and denominators](evaluation/cohorts.md) |
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
