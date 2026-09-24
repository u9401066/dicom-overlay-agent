# OpenClaw integration owner

This directory integrates the App with OpenClaw; it is not the provider-neutral
medical image harness. See the [component map](../docs/architecture/components.md)
and [documentation index](../docs/README.md).

- `package.json` / `package-lock.json`: pinned Node dependency graph. The candidate
  uses OpenClaw 2026.9.3, with portable Node 24.18.0. A newer upstream release must
  pass the public-protocol, OAuth migration, plugin, dependency and package gates.
- `workspace/plugins/dicom-overlay-agent-harness/`: public plugin entry point and
  manifests. `dicom_bbox_validate` validates normalized geometry and produces
  source/nonce-bound receipts; it does not decide that a box is clinically correct.
- `workspace/skills/dicom-*-analysis/`: modality prompts and schemas synchronized
  into the writable runtime workspace by the App. Contract changes must update
  validators, skills and tests together.
- ECGFounder is optional external waveform evidence, not an image classifier.
  Its tool is enabled only with the trusted artifact/nonce contract. Never invent
  waveform identifiers or derive image boxes from probability labels. Read the
  [tool contract](../docs/integrations/ecgfounder-tool.md).

The App's `infrastructure/openclaw_client.py` owns the public `connect` + `chat.send`
boundary; `gateway_manager.py` owns lifecycle/workspace synchronization.
`mcp_adapter.py` / `mcp_bridge.py` are host adapters. Plugin registration or a
logged bbox call is not proof that every MCP/external-model workflow works.

Provider selection is a real Settings operation. Subscription authentication uses
the pinned OAuth migration provider; OpenClaw retains inference ownership. It must
not enable the Codex agent runtime or retain a Platform API key. Account state,
generated runtime config and logs stay outside committed source.

The independent [medical-image-agent-harness](../third_party/medical-image-agent-harness/)
is pinned as a submodule. Do not move OpenClaw or desktop code into that repository,
and do not trim OpenClaw's internal runtime chunks as a packaging optimization.
