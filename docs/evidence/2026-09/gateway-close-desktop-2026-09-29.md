# Source-App shutdown acceptance and retained blind-pass failure — 2026-09-29

Actual Windows source App at `8524c4aa041c5a0a5a6a08a464f5478821d9735c`,
not the previously packaged EXE. This record proves failure-path shutdown after
two real subscription turns, **not successful five-stage publication**.

## Actual operation and retained failure

- Fresh runtime `Ctemp/dicom-close-drain-20260929`; its18,771 copied package files
  matched the pristine36dc3c6 payload before config/auth writes. The copied EXE
  was not launched; source Python App34676/launcher25184 owned Gateway32152.
- Viewer11800/launcher34096 opened the approved, previously exposed `crop_top_20`
  through its actual file dialog. Viewer1500x864 at(30,30),150% DPI; approved ROI
  remained(33,33)-(1527,891),1494x858. No desktop-wide capture or ROI enlargement.
- Real Settings inspection showed Astra subscription/medium. OAuth migration
  took19.102s; profile check45.690s. Initial connection refusal during cold
  Gateway startup recovered without restart; ready at10:47:16UTC.
- Actual Analyze at10:47:45UTC completed QC10459ms and blind pass49264ms, then
  withheld publication with `non_retainable_finding_observation`. The UI returned
  to monitoring. No Export, localization, reconciliation or finalization occurred.
  Driver wall65.691s is a failed attempt, not an analysis speedup.
- Finding `f1` referenced `o5` (present/supported) **and** `o6` (absent/supported).
  Other valid references do not make the absent observation eligible as positive
  finding support. The original response and failure receipt remain unchanged.

Offline audit matched source pixels exactly to the independently captured visible
ROI. Source SHA256:
`e6597a7362285428f0a09db45d0ad1f8bcc10ada57ba051980f32ae218ec69d2`.
Read-only public sessions/history and runtime identities bound both turns to
`openai/gpt-6-astra`, reasoning `medium`. QC public text matches fully; the blind
public response is truncated at8,000 characters and only that prefix matches.
Full blind response SHA256:
`21538621f71f46ab25823effbf26e1c9fa9180f0180c8140a549b7988e510b1e`.
No collector/auditor sent inference, retrieved hidden reasoning or repaired output.

## Actual Quit and closure

Actual Quit invoked10:49:53UTC. The App logged draining10 queued messages,
disconnected without its earlier two-second timeout, and stopped its owned Gateway.
App/launcher/Gateway exit was observed0.954s after beginning the UI invocation;
this includes automation overhead and is not a controlled benchmark. Viewer and
its launcher then closed through the normal window-close request. All five
processes and the18796 listener were absent; no process was force-killed.

Closure receipt SHA256:
`2f82906359bb3b17f9ae8b04d931c5b6fe078716934125523d96a4b85dd45b7d`.
Failed driver receipt SHA256:
`5b9b288fa682f5bca87daf9d8097ce738b4036ffee759050dedf34bb1f545edb`.
Runtime is **SEALED**; never restart it because startup truncates logs. The actual
socket close code was not instrumented; normal1000 on both peers is established
separately by the real-socket regression, not asserted for this desktop log.

## Follow-up change, not retrospective success

The scientific draft prompt now states the existing cross-reference predicate:
every finding-support observation must be assessable, present/uncertain and
supported/possible. A small mixed-positive/negative example explains that absent
observations remain in the ledger/checklist, without changing their polarity,
silently deleting them, or treating them as positive finding support.

Seven synthetic regression cases cover both reference orders for absent,
contradicted and unassessable observations, plus successful preservation of a
negative observation in summary/checklist through canonical assembly. The strict
decoder, public schema, model profile, Gateway boundary, ROI and dependencies
are unchanged. No automatic paid repair/retry was introduced.

Focused draft/publication/localization/shutdown/document-link checks passed154
tests in8.34s; Ruff formatting/checks and targeted mypy passed. The2428pass/10skip
full suite belongs to8524c4a before this later prompt change, not to the new prompt.
Sealed offline audit SHA256:
`e292ef4b6416a3a7655288eeaac86a0777c558aeba0ace90b0ceebb5abe8d532`.

This follows the official guidance to address semantic mistakes with clearer
instructions/examples; schema-shaped output can still contain mistakes.
[OpenAI Structured Outputs guidance](https://developers.openai.com/api/docs/guides/structured-outputs#handling-mistakes).
This application still uses OpenClaw's public Gateway; this citation is **not** a
claim that Gateway enables OpenAI's strict Structured Outputs API mode.

The prompt change has not yet had a fresh actual-App or frozen acceptance run.
No clinical accuracy improvement, new independent case, successful failure
recovery, complete100-case evaluation, or public binary release is claimed.
