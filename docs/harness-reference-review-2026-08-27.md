# Image-agent harness reference review — 2026-08-27

This note records which public harness patterns were adopted for the DICOM
Overlay Agent and which dependencies were deliberately not added. It is an
engineering review, not evidence of diagnostic performance.

## Primary references

- OpenAI Cookbook, [Image Evals for Image Generation and Editing Use
  Cases](https://github.com/openai/openai-cookbook/blob/main/examples/multimodal/image_evals.ipynb)
- OpenAI Cookbook, [Building resilient prompts using an evaluation
  flywheel](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/Building_resilient_prompts_using_an_evaluation_flywheel.md)
- Promptfoo, [structured evaluation output
  formats](https://github.com/promptfoo/promptfoo/blob/main/site/docs/configuration/outputs.md)
- Promptfoo, [local-runner security and trust
  boundaries](https://github.com/promptfoo/promptfoo/security)

## Patterns adopted

| Public pattern | Repository implementation | Why it matters here |
| --- | --- | --- |
| Start with non-negotiable correctness gates, then add graded quality metrics. | `infrastructure/hooks/output_validator.py` and bbox/transport gates run before `infrastructure/eval_harness.py` computes severity, partial-match, and keyword metrics. | A clinically plausible sentence cannot hide a broken 16-key payload, invalid bbox, or wrong transport route. |
| Separate test cases, runners, graders, and saved artifacts. | Answer-free inference manifests, `scripts/run-meeti-openclaw-experiment.py`, the eval scorer, and per-run artifact directories are separate layers. | A model call can be reproduced and re-scored without silently changing the input set. |
| Use an evaluation flywheel: analyze failures, measure a held-out baseline, make a targeted change, then repeat. | Failure-specific EKG prompt gates are covered by deterministic tests; fresh canaries use a denylist and reveal the gold manifest only after inference. | It reduces prompt tuning against a previously seen ECG and keeps misses visible. |
| Preserve raw outputs plus latency, usage, and assertion-level results. | Each experiment saves raw results, scorecards, transport receipts, protocol fingerprints, logs, and review artifacts. | Accuracy, speed, schema integrity, and subscription routing remain independently auditable. |
| Stream or checkpoint large evaluation sets. | The 10,001-case scale path uses atomic checkpoints, input/config fingerprints, and fail-closed resume validation. | A long run can resume without pretending one fixture is 10,001 independent clinical images. |
| Treat model output, templates, remote content, and custom evaluators as untrusted inputs. | Evaluation stays local, uses the existing public OpenClaw Gateway boundary, validates output before rendering, and does not execute model-produced code. | It avoids expanding the PHI and code-execution trust surface. |

## Dependency decision

No third-party evaluation framework was added to the packaged application.
The useful architectural patterns already fit the repository's Python harness,
while another runtime would increase the zero-install bundle and introduce a
second configuration/template execution boundary. The project therefore keeps
its deterministic gates and artifact schema in-repo and uses public projects as
design references rather than runtime dependencies.

## Evidence limits

MEETI provides useful weak report labels for canary testing, but it is not a
substitute for a cardiologist-reviewed localization and diagnosis benchmark.
Synthetic 10,001-case plumbing proves scale and resume behavior only. Release
claims must continue to separate engineering validity (schema, transport,
geometry, latency, and reproducibility) from clinical validity.
