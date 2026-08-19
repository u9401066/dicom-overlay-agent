---
name: medical-image-reading
description: Inspect, compare, ground, or evaluate de-identified medical images and ECG renders with a reproducible multi-pass co-reading protocol. Use for CXR, CT brain, EKG/ECG image, localization, uncertainty, or image-harness evaluation; do not use for autonomous diagnosis, patient-specific treatment, PACS writeback, UI automation, or generic non-medical computer vision.
---

# Medical Image Reading (pinned adapter)

This file only makes the public harness discoverable from the private product root.
Before taking any medical-image task action, load and follow the pinned canonical
[medical-image-reading skill][canonical-skill]. Treat that file and its relative
references as the sole source of the scientific method and output contract.

If the canonical file or any required reference cannot be read, stop and report
that the submodule is not initialized. Product-specific OpenClaw, overlay, screen
capture, or plugin behavior must not be added to this adapter.

[canonical-skill]: ../../../third_party/medical-image-agent-harness/.agents/skills/medical-image-reading/SKILL.md
