# Read-only scientific desktop usage collection

Use `scripts/collect-scientific-desktop-usage.py` for an actual scientific-review
desktop export. Do not apply the legacy projection-trace collector: the projection
may retain only Gateway negotiation while model turns live in the scientific
attempt store. A zero-turn legacy receipt is not zero usage.

```powershell
uv run --no-sync python scripts/collect-scientific-desktop-usage.py `
  PATH_TO_RUNTIME/data/exports/desktop-TIMESTAMP `
  --live PATH_TO_RUNTIME `
  --output PATH_OUTSIDE_RUNTIME/scientific-usage.json
```

The runtime must be the original App-owned runtime, with retained
`data/scientific-attempts/`, `gateway.log` and public OpenClaw sessions available.
The only CLI operation is read-only `sessions`; there is no `chat.send`, App/Gateway
restart, auth/profile mutation or output repair. The output must not already exist
and must be outside the runtime. Keep old failed receipts unchanged and associate
a supplemental receipt with their original hashes.

The collector:

- Validates `scientific-result.json` with the pinned public contract validator.
- Binds source PNG, projection, canonical source identity and one host run.
- Checks every retained turn's sequence, source hash, exact artifact inventory
  and hashes, including visible tool/geometry artifacts where present.
- Requires the current five-stage workflow, one distinct public session/run per
  stage, fresh nonnegative token counters, and exactly one matching Astra-medium
  runtime observation. Missing/duplicate/unknown state fails closed.
- Rechecks export and retained-turn identity after querying. Records collector,
  export inventory, turn receipt and Gateway log-prefix hashes. Original artifacts
  stay unchanged; output uses create-only writes.

The record proves these local/source/session associations. It does **not** prove
clinical accuracy, patient-level independence, remote inbound-image equality, a
monetary charge, or that a complete cohort has passed. It is not a replacement
for independent batch scoring or a trusted signature. Public session counters are
snapshots. The current command queries the latest512 sessions active in120 minutes;
collect promptly after each case. Missing historical sessions are an error, not
permission to repeat paid inference.

The actual [first scientific paired case](../evidence/2026-09/scientific-paired-cohort-2026-09-29.md)
exercised the five-turn collection after a legacy-collector failure, without
rerunning that case. If workflow stages, model or public session format change,
update the collector and regression tests together; do not silently loosen it.
