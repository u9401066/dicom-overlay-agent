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
- Current medium live evidence is pending; no model fallback has been introduced.

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
is still pending and must not be described as completed by the model change.

Clinical UX must emphasize conclusions, priority concerns, evidence/limitations and
useful next review steps, not just terminology or internal trace fields. True
uncertainty from missing leads or poor images must not be replaced with an invented
diagnosis. Diverse vendor/legacy ECG, complete MCP/external-tool binding, the latest
OpenClaw upgrade audit and the PyQt6 distribution-license gate remain open.
